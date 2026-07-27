"""Phase 24 + Phase 27 — Merchant Rules CRUD (``/api/merchant-rules/*``).

DB-backed categorizer substring rules. Pre-Phase-24 the rules lived
as a Python module-level dict; the user was forced to redeploy the
BE to add/remove keywords. Phase 24 moves the source of truth into
the ``merchant_rules`` table so this route set is the user-facing
affordance from ``/settings``.

All routes require a valid JWT cookie (the standard
``Depends(require_user)`` gate). The ``Category`` table is shared
worldwide (the project's single-user local-first contract), so no
``user_id`` scoping is required here.

Phase 27 — provenance tracking + CSV import/export. Each rule row
carries an immutable ``source`` field (``system`` / ``manual`` /
``tag-rule`` / ``llm`` / ``imported``) so the Settings UI can render
a badge distinguishing "this came from the seed" (``fizzy``) from
"This came from a Tag Rule" from "I'll never know where that came
from, must have been imported". Source is immutable past creation
(``MerchantRuleUpdate`` does NOT declare it; clients cannot rewrite
history via PUT).

CSV format (locked header):

    category_name,keyword,priority,is_archived,source

Export writes the LIVE source value (so the user can audit their
table); Import OVERRIDES source to ``'imported'`` on every row it
inserts (the act of importing is itself the provenance event).
``is_archived`` is exported/imported as ``'true'`` / ``'false'``
case-insensitive so the file opens cleanly in Excel.

Endpoints:

- ``GET    /api/merchant-rules/``            — list (filter by category_id, source, include_archived).
- ``POST   /api/merchant-rules/``            — create (auth). Source defaults to 'manual'; rejects 'system'.
- ``PUT    /api/merchant-rules/{id}``        — partial update (auth). Source is NOT updatable.
- ``DELETE /api/merchant-rules/{id}``        — soft-delete via ``is_archived=True`` (auth).
- ``POST   /api/merchant-rules/reload``      — diagnostic re-SELECT returning live row counts.
- ``GET    /api/merchant-rules/export``      — CSV download of all rules (Phase 27).
- ``POST   /api/merchant-rules/import``      — CSV upload with INSERT-IF-NOT-EXISTS semantics (Phase 27).
"""
import csv
import io
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Category, MerchantRule

# Phase 29 — duplicate detection aliases so the route handlers stay
# readable. ``find_substring_duplicates`` is defined in the categorizer
# service (next to ``_DEFAULT_MERCHANT_RULES_SEED``) because the
# substring logic is a categorizer-domain concern. The route's job is
# to expose the helper behind auth + a stable JSON contract.
from app.schemas import (
    MerchantDuplicateApplyRequest,
    MerchantDuplicateApplyResult,
    MerchantDuplicateGroup,
    MerchantDuplicateGroupList,
    MerchantRuleCreate,
    MerchantRuleImportError,
    MerchantRuleImportResult,
    MerchantRuleResponse,
    MerchantRuleSource,
    MerchantRuleUpdate,
)
from app.services.categorizer import (
    consolidate_duplicate_groups,
    find_substring_duplicates,
)
from app.services.llm_categorizer import (
    find_semantic_duplicates_async,
)

router = APIRouter(prefix="/api/merchant-rules", tags=["merchant-rules"])

LOG = logging.getLogger(__name__)

# Phase 27 CSV contract. Header order is LOCKED — the import endpoint
# reads via NAMED columns via ``csv.DictReader`` so field order in
# the FILE doesn't matter, but the export serializer writes in this
# exact order. Tests assert on this exact header list via
# ``tests/test_routes_merchant_rules.py`` so a future reorder MUST
# be paired with a test update.
_CSV_HEADER: tuple[str, ...] = (
    "category_name",
    "keyword",
    "priority",
    "is_archived",
    "source",
)

# Required CSV columns for import. ``source`` is OPTIONAL (defaults
# to ``'imported'`` anyway on every row OR a CSV-empty value); the
# other 4 are required.
_CSV_REQUIRED_COLS: frozenset[str] = frozenset({
    "category_name",
    "keyword",
})

# Phase 27 — string form for ``is_archived`` in CSV. Export writes
# ``'true'`` / ``'false'``; import accepts both plus ``'1'`` / ``'0'``
# for Excel-typed-cell friendliness. Anything else is a row error.
_VALID_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes"})
_VALID_FALSE_STRINGS: frozenset[str] = frozenset({"false", "0", "no", ""})


def _row_to_response(
    db: Session, rule: MerchantRule, cat_lookup: dict[int, str]
) -> MerchantRuleResponse:
    """Build a deterministic :class:`MerchantRuleResponse` from an ORM row.

    The ``category_name`` is denormalised on the read path so the FE
    never needs an N+1 follow-up. ``cat_lookup`` is passed in by the
    caller so a list endpoint issues ONE category-name SELECT per
    call instead of one per row.
    """
    return MerchantRuleResponse(
        id=rule.id,
        category_id=rule.category_id,
        category_name=cat_lookup.get(rule.category_id),
        keyword=rule.keyword,
        priority=rule.priority,
        is_archived=rule.is_archived,
        # Phase 27 — surface provenance on every response so the FE can
        # render a Source chip without an extra round-trip.
        source=rule.source,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/", response_model=List[MerchantRuleResponse])
async def list_merchant_rules(
    category_id: Optional[int] = Query(
        None,
        description="Filter to a single category (auth-scoped by JWT).",
    ),
    source: Optional[MerchantRuleSource] = Query(
        None,
        description=(
            "Phase 27 — filter to rules from a single provenance "
            "('system', 'manual', 'tag-rule', 'llm', 'imported'). "
            "Combined with category_id + include_archived via AND."
        ),
    ),
    include_archived: bool = Query(
        False,
        description="When True, soft-deleted rules (is_archived=True) are "
                    "included in the response. Defaults to False so the "
                    "Settings UI's primary list shows only live rules.",
    ),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List merchant rules ordered by priority ASC, then id ASC.

    The Settings UI uses this output as the source-of-truth rendering
    of the user's Merchant Rules card. ``include_archived=True`` is
    used by the FE's "show archive" affordance (the Settings page
    exposes this as a small toggle near the list header).

    Phase 27 — ``?source=...`` Query param filters to one provenance
    value; combines with ``category_id`` + ``include_archived`` via
    AND. Precedence is irrelevant for correctness — every filter is
    additive; the response builder does the final denormalisation.
    """
    query = db.query(MerchantRule)
    if not include_archived:
        query = query.filter(MerchantRule.is_archived.is_(False))
    if category_id is not None:
        query = query.filter(MerchantRule.category_id == category_id)
    if source is not None:
        query = query.filter(MerchantRule.source == source)
    rules = query.order_by(MerchantRule.priority.asc(), MerchantRule.id.asc()).all()

    # ONE category-name SELECT (not N+1). ``categories`` is small
    # (<50 rows in canonical local-first) so a full lookup is cheap.
    cat_names = {
        row.id: row.name
        for row in db.query(Category).all()
    }
    return [_row_to_response(db, r, cat_names) for r in rules]


@router.post("/", response_model=MerchantRuleResponse, status_code=201)
async def create_merchant_rule(
    payload: MerchantRuleCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create a new merchant rule.

    - ``category_id`` must reference an existing Category row (the
      FK constraint enforces this; we surface a friendlier 400
      instead of letting the SQLAlchemy IntegrityError bubble up
      and the FE's classifier map it to a generic 409).
    - ``keyword`` is uppercased + stripped server-side; the
      categorizer's per-row scan skips a per-call upper this way.
    - ``priority`` defaults to 100 (LAST per category) so a
      user-added rule does NOT silently re-order system rules.
    - ``source`` (Phase 27) defaults to ``'manual'`` if omitted.
      ``'system'`` is REJECTED with 400 — the boot-time seed
      (``app.services.categorizer.seed_default_merchant_rules``)
      is the only writer that may stamp that value.
    - ``UNIQUE(category_id, keyword)`` enforces 409 on duplicates;
      the FE surfaces the upstream detail verbatim so the user
      sees "this keyword already exists for that category".
    """
    cat = db.query(Category).filter(Category.id == payload.category_id).first()
    if cat is None:
        raise HTTPException(
            status_code=400,
            detail=f"Category id {payload.category_id} does not exist.",
        )
    keyword = payload.keyword.strip().upper()
    if not keyword:
        raise HTTPException(
            status_code=400,
            detail="keyword must be a non-empty string when present.",
        )
    # Phase 27 — explicit 'system' rejection. Pydantic accepts it via
    # the shared ``MerchantRuleSource`` literal, but only the
    # boot-time seed (``categorizer.seed_default_merchant_rules``)
    # may stamp it; a free-form POST with that value is a logic bug
    # OR an attempt to lie about provenance. Reject both loudly.
    source_value: MerchantRuleSource = payload.source or "manual"
    if source_value == "system":
        raise HTTPException(
            status_code=400,
            detail=(
                "source='system' is reserved for boot-time seed rules "
                "and cannot be set via POST. Omit source (defaults to "
                "'manual') or use a non-system value."
            ),
        )
    # Phase 28 — auto-increment priority on omitted input. The
    # schema's ``priority: Optional[int] = None`` lets us distinguish
    # "client didn't send priority" (this common case) from "client
    # sent a specific priority" (CSV import path, future bulk-insert
    # admin tools). The previous Pydantic default of 100 silently
    # collided with the last existing rule in the same category
    # (the user reported "when I add a new rule it uses the same
    # priority as the rule in the category I have") so a
    # same-priority sort could swap rows. We compute
    # ``MAX(priority) + 10`` so the new rule slots in below the
    # last existing rule with a deterministic +10 gap, and fall
    # back to 100 when the category is empty (mirroring the schema
    # default so the very first user-added rule still has a
    # sensible order). The single SELECT is cheap because the
    # ``ix_merchant_rules_archived_priority`` composite index
    # already covers ``WHERE category_id = ? AND is_archived = false
    # ORDER BY priority`` paths.
    if payload.priority is None:
        max_priority = (
            db.query(func.max(MerchantRule.priority))
            .filter(
                MerchantRule.category_id == payload.category_id,
                MerchantRule.is_archived.is_(False),
            )
            .scalar()
        )
        priority = 100 if max_priority is None else int(max_priority) + 10
    else:
        priority = payload.priority
    rule = MerchantRule(
        category_id=payload.category_id,
        keyword=keyword,
        priority=priority,
        is_archived=False,
        source=source_value,
    )
    # Pre-check for an existing rule with the same (category_id,
    # keyword) pair — including archived rows the FE's filter may
    # hide. The UNIQUE constraint spans ALL rows, so a conflict
    # with an archived rule produces a cryptic "already exists"
    # error the user can't diagnose (they can't see the archived
    # row). This explicit SELECT gives us a chance to surface the
    # archived status in the error detail.
    existing = (
        db.query(MerchantRule)
        .filter(
            MerchantRule.category_id == payload.category_id,
            MerchantRule.keyword == keyword,
        )
        .first()
    )
    if existing is not None:
        extra = (
            " (currently archived — switch the filter to \"Archived only\" "
            "or \"All rules\" to see it, then restore or delete it first)"
            if existing.is_archived
            else ""
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"A merchant rule with keyword {keyword!r} already "
                f"exists for category {cat.name!r}.{extra}"
            ),
        )

    db.add(rule)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"A merchant rule with keyword {keyword!r} already "
                f"exists for category {cat.name!r}."
            ),
        )
    db.refresh(rule)
    return _row_to_response(
        db, rule, {cat.id: cat.name for cat in db.query(Category).all()}
    )


@router.put("/{rule_id}", response_model=MerchantRuleResponse)
async def update_merchant_rule(
    rule_id: int,
    payload: MerchantRuleUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update of a merchant rule.

    Whitelist-driven — only fields declared on
    :class:`MerchantRuleUpdate` are applied. Identity column
    (``id``, ``created_at``, ``source``) is intentionally NOT
    declared so a client cannot escalate ownership, rewrite
    history, OR lie about provenance via PUT. ``category_id``
    resolution mirrors ``create_merchant_rule``: 400 if the
    referenced category row does not exist.

    Keyword rename triggers the same uppercase normalisation as
    ``POST``. A name change combined with an EXISTING duplicate
    in the target category 409s (the ``UNIQUE(category_id, keyword)``
    constraint kicks in).

    Setting ``is_archived=True`` is the canonical "delete" path
    (see :func:`delete_merchant_rule`); setting
    ``is_archived=False`` UN-archives a previously soft-deleted
    row.
    """
    rule = db.query(MerchantRule).filter(MerchantRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Merchant rule not found")

    patch = {k: v for k, v in payload.model_dump().items() if v is not None}

    if "category_id" in patch:
        new_cat_id = int(patch["category_id"])
        cat = db.query(Category).filter(Category.id == new_cat_id).first()
        if cat is None:
            raise HTTPException(
                status_code=400,
                detail=f"Category id {new_cat_id} does not exist.",
            )
        patch["category_id"] = new_cat_id

    if "keyword" in patch:
        kw = (patch["keyword"] or "").strip().upper()
        if not kw:
            raise HTTPException(
                status_code=400,
                detail="keyword must be a non-empty string when present.",
            )
        patch["keyword"] = kw

    # Phase 27 — defensively reject ``source`` even though
    # ``MerchantRuleUpdate`` does NOT declare it; ``model_dump()``
    # already drops unknown fields, but a hand-crafted client
    # could still smuggle one. The whitelist block below also
    # guards against a future schema-add that accidentally
    # re-introduces the field.
    if "source" in patch:
        patch.pop("source")

    for field, value in patch.items():
        if hasattr(rule, field):
            setattr(rule, field, value)
    rule.updated_at = _now_utc()

    # Pre-check for an existing OTHER rule with the same (category_id,
    # keyword) pair — the UNIQUE constraint spans ALL rows including
    # archived ones the FE's filter may hide. We exclude the current
    # rule (editing keyword to the SAME value it already has is a
    # no-op, not a conflict). When the conflicting row is archived,
    # the error detail tells the user how to surface it.
    resolved_category_id = rule.category_id
    resolved_keyword = rule.keyword
    conflicting = (
        db.query(MerchantRule)
        .filter(
            MerchantRule.id != rule_id,
            MerchantRule.category_id == resolved_category_id,
            MerchantRule.keyword == resolved_keyword,
        )
        .first()
    )
    if conflicting is not None:
        extra = (
            " (currently archived — switch the filter to \"Archived only\" "
            "or \"All rules\" to see it, then restore or delete it first)"
            if conflicting.is_archived
            else ""
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"A merchant rule with keyword {resolved_keyword!r} already "
                f"exists in the target category.{extra}"
            ),
        )

    db.add(rule)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"A merchant rule with the updated keyword "
                f"{patch.get('keyword', rule.keyword)!r} already "
                f"exists in the target category."
            ),
        )
    db.refresh(rule)
    return _row_to_response(
        db, rule, {c.id: c.name for c in db.query(Category).all()}
    )


@router.delete("/{rule_id}", status_code=204)
async def delete_merchant_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Soft-delete a merchant rule (sets ``is_archived=True``).

    Idempotent: a second DELETE on an already-archived row still
    returns 204. Un-archiving is via
    ``PUT /api/merchant-rules/{id} {"is_archived": false}``.

    The ROW STAYS in the ``merchant_rules`` table so the boot-time
    seed helper can SKIP it on subsequent cold starts (a hard
    delete would let the seed re-insert the system keyword,
    silently undoing the user's delete).
    """
    rule = db.query(MerchantRule).filter(MerchantRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Merchant rule not found")
    if not rule.is_archived:
        rule.is_archived = True
        rule.updated_at = _now_utc()
        db.add(rule)
        db.commit()
        db.refresh(rule)
    return None


@router.post("/reload", response_model=dict)
async def reload_rules(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Diagnostic endpoint — returns the live rule counts.

    The categorizer's :func:`build_merchant_rules` is called
    inline every bulk run, so the BE has no module-level cache
    to bust today. This endpoint exists so a future TTL cache
    layer can be wired in without breaking the FE contract.

    Returns ``{"active": int, "archived": int, "by_source": dict}``
    — the ``by_source`` partition (Phase 27) lets the FE assert on
    the breakdown without an N+1 cross the list endpoint.
    """
    active = (
        db.query(MerchantRule)
        .filter(MerchantRule.is_archived.is_(False))
        .count()
    )
    archived = (
        db.query(MerchantRule)
        .filter(MerchantRule.is_archived.is_(True))
        .count()
    )
    # Phase 27 — breakdown-by-source diagnostic. Single GROUP BY query.
    # Computes COUNT(id) per (source, is_archived) tuple so a
    # 117-system-row setup returns ``{ system: { active: ~117,
    # archived: 1 } }`` — NOT (a regression we already shipped
    # once) ``{ system: { active: 1, archived: 1 } }`` from a
    # GROUP BY without an aggregated column. ``func.count`` is
    # the canonical SQLAlchemy 2.x idiom; checking
    # ``MerchantRule.id`` keeps the GROUP BY column REFERENCES
    # explicit so PG / SQLite query planners can use the PK index.
    by_source_rows = (
        db.query(
            MerchantRule.source,
            MerchantRule.is_archived,
            func.count(MerchantRule.id),
        )
        .group_by(MerchantRule.source, MerchantRule.is_archived)
        .all()
    )
    by_source: dict[str, dict[str, int]] = {}
    for src, is_archived, count in by_source_rows:
        bucket = by_source.setdefault(src, {"active": 0, "archived": 0})
        if is_archived:
            bucket["archived"] += count
        else:
            bucket["active"] += count
    return {"active": active, "archived": archived, "by_source": by_source}


# ---------------------------------------------------------------------
# Phase 27 — CSV export / import.
# ---------------------------------------------------------------------


def _csv_serialize_rows(
    db: Session,
    rules: list[MerchantRule],
    cat_lookup: dict[int, str],
) -> str:
    """Build the CSV body for the export endpoint.

    Columns (LOCKED): ``category_name,keyword,priority,is_archived,source``.
    Sorted by priority ASC, id ASC (matches the list endpoint so a
    user who exports then re-imports on an EMPTY DB sees identical
    behaviour to import-after-add). ``is_archived`` is rendered as
    ``'true'`` / ``'false'`` for Excel readability. ``source`` is the
    live DB value (a future "import preserving original source" mode
    could change this; today import OVERRIDES to ``'imported'`` so a
    faithful round-trip can never lie about the import event).
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_CSV_HEADER), lineterminator="\n")
    writer.writeheader()
    for rule in rules:
        writer.writerow({
            "category_name": cat_lookup.get(rule.category_id, ""),
            "keyword": rule.keyword,
            "priority": rule.priority,
            "is_archived": "true" if rule.is_archived else "false",
            "source": rule.source,
        })
    return buf.getvalue()


@router.get("/export", response_class=StreamingResponse)
async def export_merchant_rules(
    include_archived: bool = Query(
        True,
        description=(
            "Phase 27 — when True (default) the export includes "
            "soft-deleted rules so a re-import can restore them. "
            "When False, only live rules are exported."
        ),
    ),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 27 — CSV download of every merchant rule.

    Returns ``text/csv`` with the file as an attachment named
    ``merchant-rules.csv`` so a save dialog handles the content
    type. Sorted by priority ASC, id ASC to match the list
    endpoint. The ``source`` column exposes the LIVE provenance;
    a re-import OVERRIDES that value to ``'imported'`` on every
    inserted row (audit-trail correctness; see the import route's
    docstring for the rationale).

    Test fixtures (``tests/fixtures/sample-merchant-rules.csv``)
    lock the header order and the row serialization so a round-
    trip test (export → parse → import → re-export) reproduces
    the same body modulo the ``source`` column override.
    """
    query = db.query(MerchantRule)
    if not include_archived:
        query = query.filter(MerchantRule.is_archived.is_(False))
    rules = query.order_by(
        MerchantRule.priority.asc(), MerchantRule.id.asc()
    ).all()
    cat_lookup = {row.id: row.name for row in db.query(Category).all()}
    body = _csv_serialize_rows(db, rules, cat_lookup)
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="merchant-rules.csv"'
            ),
        },
    )


def _parse_csv_value_for_import(
    raw: dict[str, str],
    cat_lookup: dict[str, int],
    *,
    row_number: int,
) -> tuple[Optional[MerchantRule], list[MerchantRuleImportError]]:
    """Convert one CSV row dict to an unsaved ``MerchantRule`` (or errors).

    Returns ``(rule, errors)``:
      - If ``errors`` is empty: ``rule`` is a NEW ``MerchantRule``
        keyword + category_id resolved, ``source='imported'``,
        ``priority`` parsed (default 100), and ``is_archived``
        parsed (default False). The caller decides whether to
        commit (UNIQUE-collision skip path).
      - If ``errors`` is non-empty: ``rule`` is ``None`` and the
        row is dropped from the batch.

    Designed to NEVER raise: every per-row failure surfaces as a
    structured ``MerchantRuleImportError`` so a single row with
    a typo doesn't blow up the import of a 200-row CSV.
    """
    def err(reason: str) -> list[MerchantRuleImportError]:
        return [MerchantRuleImportError(row=row_number, reason=reason)]

    category_name = (raw.get("category_name") or "").strip()
    # Phase 27 — keyword processing is ``.upper()`` ONLY (no
    # ``.strip()``). The categorizer's bootstrap seed dict uses
    # trailing-space substrings as deliberate word-boundary markers
    # (``"TAXI "``, ``"BP "``, ``"76 "``, etc.); the seed path
    # preserves them via ``.upper()`` (no strip), and the export
    # serializer writes them verbatim. Stripping on import would
    # collapse those keys' identity into the un-stripped form,
    # breaking the round-trip on the canonical ~117 system rows.
    # User-added keywords from the POST path still strip (via the
    # standalone `create_merchant_rule` route) so user rules
    # normalise fine; only the import path preserves whitespace
    # so the inverse stays byte-identical to the export.
    keyword = (raw.get("keyword") or "").upper()
    if not category_name:
        return None, err("category_name is empty")
    if not keyword:
        return None, err("keyword is empty")

    cat_id = cat_lookup.get(category_name)
    if cat_id is None:
        return None, err(
            f"category_name {category_name!r} does not exist (run "
            f"GET /api/categories/ to list valid names)."
        )

    priority_raw = (raw.get("priority") or "").strip()
    try:
        # ``int(float(...))`` so a user-typed ``100.0`` from Excel
        # doesn't error. Fractional results (e.g. ``10.5``) collapse
        # to ``10`` without complaint — the categoriser's range
        # accepts anything; the float is rejected ONLY if non-numeric.
        priority = int(float(priority_raw)) if priority_raw else 100
    except ValueError:
        return None, err(
            f"priority {priority_raw!r} is not a valid integer"
        )

    archived_raw = (raw.get("is_archived") or "").strip().lower()
    if archived_raw in _VALID_TRUE_STRINGS:
        is_archived = True
    elif archived_raw in _VALID_FALSE_STRINGS:
        is_archived = False
    else:
        return None, err(
            f"is_archived {archived_raw!r} is not 'true' or 'false'"
        )

    # The CSV's ``source`` column is IGNORED — the import event is
    # the provenance. Audit-trail correctness beats round-trip
    # fidelity; a user re-importing a system rule does NOT get to
    # re-claim ``'system'`` provenance via a hand-edited CSV.
    return MerchantRule(
        category_id=cat_id,
        keyword=keyword,
        priority=priority,
        is_archived=is_archived,
        source="imported",
    ), []


@router.post("/import", response_model=MerchantRuleImportResult)
async def import_merchant_rules(
    file: UploadFile = File(
        ...,
        description=(
            "Phase 27 — multipart CSV upload. Header MUST include "
            "'category_name' + 'keyword'; 'priority', 'is_archived', "
            "and 'source' are optional (source is overridden to "
            "'imported' on every row anyway)."
        ),
    ),
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Phase 27 — bulk CSV import with INSERT-IF-NOT-EXISTS semantics.

    Behavior contract (the user-facing default — tune via Query
    params in a follow-up if needed):

    - **Success / partial success** → HTTP 200 with
      ``MerchantRuleImportResult`` payload.
    - **Structural failure** → HTTP 400 (missing required headers,
      empty payload, unreadable bytes).
    - **Per-row data errors** → recorded in ``errors`` array with
      the row number + reason; the row is DROPPED from the batch.
    - **Duplicate (category_id, keyword)** → increment
      ``skipped_existing`` and skip (existing row is NOT updated —
      the user's current state is preserved). No error logged.

    Each successfully-inserted row has ``source='imported'`` (Phase
    27 audit-trail contract, OVERRIDING anything in the CSV).
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded CSV is empty.",
        )
    # ``utf-8-sig`` strips BOM bytes that Excel prepends by default;
    # reading as plain ``utf-8`` would put a ``\ufeff`` in the first
    # header column name and break ``DictReader`` lookups.
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded CSV is not valid UTF-8: {exc.reason}",
        )

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(
            status_code=400,
            detail="CSV is missing a header row.",
        )
    missing_required = [
        col for col in _CSV_REQUIRED_COLS if col not in reader.fieldnames
    ]
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV header is missing required column(s): "
                f"{', '.join(missing_required)}."
            ),
        )

    cat_lookup = {
        row.name: row.id for row in db.query(Category).all()
    }
    inserted = 0
    skipped_existing = 0
    errors: list[MerchantRuleImportError] = []

    # Use a single ``commit()`` at the BOTTOM so a real syntax error
    # in row 17 doesn't 500 the entire import for rows 1-16 which
    # are valid. Per-row IntegrityError from UNIQUE(category_id,
    # keyword) is caught separately so duplicates increment
    # skipped_existing without aborting the batch.
    for row_number, raw in enumerate(reader, start=2):  # start=2 = line 1 is header
        if raw is None:
            continue
        rule, row_errors = _parse_csv_value_for_import(
            raw, cat_lookup, row_number=row_number
        )
        if row_errors or rule is None:
            errors.extend(row_errors)
            continue
        # Duplicate check via the UNIQUE(category_id, keyword)
        # constraint. We SELECT first (cheap on the indexed UNIQUE)
        # rather than letting the IntegrityError bubble — the latter
        # would require a session rollback that nukes any prior
        # in-flight INSERTs in the same commit.
        existing = (
            db.query(MerchantRule)
            .filter(
                MerchantRule.category_id == rule.category_id,
                MerchantRule.keyword == rule.keyword,
            )
            .first()
        )
        if existing is not None:
            skipped_existing += 1
            continue
        db.add(rule)
        try:
            db.flush()  # surface FK / NOT-NULL violations per-row
        except Exception as flush_exc:  # noqa: BLE001
            db.rollback()  # discard this row only
            errors.append(
                MerchantRuleImportError(
                    row=row_number,
                    reason=f"flush failed: {type(flush_exc).__name__}",
                )
            )
            continue
        inserted += 1

    # Final commit covers all inserted rows + the explicit per-row
    # flushes above. If THIS commit fails (extremely rare after
    # per-row flushes have already validated each row) the 500
    # handler in ``app.main`` returns a JSON detail with CORS.
    try:
        db.commit()
    except Exception as commit_exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                f"Import batch commit failed after {inserted} inserts: "
                f"{type(commit_exc).__name__}"
            ),
        )

    return MerchantRuleImportResult(
        inserted=inserted,
        skipped_existing=skipped_existing,
        errors=errors,
    )


def _now_utc():
    """ISO timestamp helper — local import avoids an extra top-level
    dependency on ``datetime`` in the route's public symbols.

    Phase 24 ALL timestamp writes go through this helper so a
    future monotonically-increasing-clock choice (e.g.
    ``datetime.now(timezone.utc).isoformat()``) is a single-line
    edit.
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Phase 29 — duplicate detection (Settings → "Clean up duplicates").
# ---------------------------------------------------------------------
# Three endpoints, exposed under ``/api/merchant-rules/duplicates/*``:
#
# 1. ``GET  /duplicates``           — L1 (substring) only. Deterministic,
#                                     offline, fast. The Settings page's
#                                     "Find duplicates" button's default
#                                     affordance.
# 2. ``POST /duplicates/llm``       — L1 + L2 (semantic) combined.
#                                     Opt-in: a user without Ollama
#                                     running can still get a working
#                                     L1-only dedup wizard; the L2 pass
#                                     adds same-merchant pairs that
#                                     substring cannot relate
#                                     ("WALMART" vs "WAL-MART", etc.).
# 3. ``POST /duplicates/apply``     — soft-delete (is_archived=True) a
#                                     list of candidate ids. The
#                                     canonical is NEVER touched.
#                                     Idempotent — re-clicking Apply on
#                                     an already-archived row is a no-op.
#
# Soft-delete contract: the "merged" rule is ``is_archived=True`` (NOT
# hard delete) so the boot-time seed never resurrects it on the next
# cold start. The ``seed_default_merchant_rules`` SKIP-on-archived
# check is the canonical way to keep user intent across restarts.


@router.get(
    "/duplicates",
    response_model=MerchantDuplicateGroupList,
    response_model_by_alias=False,
)
async def find_duplicate_merchant_rules(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> MerchantDuplicateGroupList:
    """L1-only — return every same-category rule pair where one
    keyword is a substring of the other.

    Same-contract endpoint as ``POST /duplicates/llm`` minus the L2
    pass: the response shape and the dedup group consolidation are
    identical so the FE's wizard can render the same row layout
    regardless of which endpoint the user triggered. The FE's
    "Find duplicates" button calls THIS endpoint first; the user
    can opt into the L2 pass via a "Also check semantically" toggle
    that fires ``POST /duplicates/llm`` and re-renders.

    Pure read-side: no rows are mutated, no cache writes (the L1
    helper is a deterministic one-pass SQL scan + in-Python
    consolidation). Fast on a ~200-row table.

    ``l2_status`` is always ``"skipped"`` on this endpoint — the
    L1-only path never attempts the L2 pass. The field is
    included so the FE's banner logic can rely on its presence
    in every response shape (no Optional dance).
    """
    pairs = find_substring_duplicates(db)
    groups = consolidate_duplicate_groups(pairs)
    return MerchantDuplicateGroupList(
        groups=[
            MerchantDuplicateGroup(**g) for g in groups
        ],
        l1_count=len(pairs),
        l2_count=0,
        l2_status="skipped",
    )


@router.post(
    "/duplicates/llm",
    response_model=MerchantDuplicateGroupList,
    response_model_by_alias=False,
)
async def find_duplicate_merchant_rules_with_llm(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> MerchantDuplicateGroupList:
    """L1 + L2 combined — L1 (substring) merged with L2 (LLM semantic).

    The Settings UI's wizard fires this when the user toggles "Also
    check semantically" so a user without Ollama running can still
    get a working L1-only dedup wizard via GET /duplicates. Both
    endpoints return the same response shape so the wizard renders
    identically.

    L2 contract: sends ONE Ollama prompt PER CATEGORY (never across
    categories) so the LLM cannot merge two same-keyword rules in
    different categories. 7-day in-process cache (mirrors the Pass 4
    contract) means a second click within the week is free.

    Failure modes:

    - **httpx.ConnectError / TimeoutException** (Ollama offline):
      surfaces as HTTP 503 via the global handler. The FE renders
      "Pass 4 is offline; showing L1 results only" rather than
      failing the whole wizard.
    - **ValueError** (Ollama returned malformed JSON): HTTP 502. The
      FE renders a retry banner.
    - **Generic 500** (anything else): HTTP 500 with a stable
      ``{"detail": "Internal server error: ..."}`` payload.

    The L1 results are ALWAYS returned alongside the L2 error path:
    a user with a flaky Ollama still gets a usable wizard. To keep
    that promise, this endpoint's body catches the L2 transport /
    validation exceptions and returns the L1-only payload plus the
    ``l2_status`` field set to ``"offline"`` (transport) or
    ``"malformed"`` (parse). The FE can then render an HONEST
    partial-success banner — without ``l2_status`` the FE couldn't
    tell "L2 returned 0 pairs" apart from "L2 never ran", which
    was the silent-failure gap surfaced by the Phase 29 review.
    """
    l1_pairs = find_substring_duplicates(db)
    l1_groups = consolidate_duplicate_groups(l1_pairs)
    try:
        l2_pairs = await find_semantic_duplicates_async(db)
    except httpx.TransportError as exc:
        # ``httpx.TransportError`` is the BASE class for all
        # network-level failures (ConnectError, TimeoutException,
        # ReadError, WriteError, ConnectTimeout, ReadTimeout,
        # etc.). Catching the broad base ensures a DNS failure /
        # SSL error / proxy error / connection reset all degrade
        # to the L1-only payload with ``l2_status='offline'``
        # rather than a 500. The specific subclass name is logged
        # for operator triage.
        LOG.warning(
            "L2 semantic dedup: Ollama unreachable (%s: %s); "
            "returning L1-only payload with l2_status='offline'.",
            type(exc).__name__, exc,
        )
        return MerchantDuplicateGroupList(
            groups=[
                MerchantDuplicateGroup(**g) for g in l1_groups
            ],
            l1_count=len(l1_pairs),
            l2_count=0,
            l2_status="offline",
        )
    except ValueError as exc:
        LOG.warning(
            "L2 semantic dedup: Ollama returned malformed body (%s); "
            "returning L1-only payload with l2_status='malformed'.",
            exc,
        )
        return MerchantDuplicateGroupList(
            groups=[
                MerchantDuplicateGroup(**g) for g in l1_groups
            ],
            l1_count=len(l1_pairs),
            l2_count=0,
            l2_status="malformed",
        )
    # Consolidate L1 + L2 by union of pairs. consolidate_duplicate_groups
    # groups by canonical_id and keeps the highest-confidence signal
    # per (canonical, candidate) pair, so feeding the combined list
    # in yields a single group per canonical with the strongest
    # confidence from either source.
    merged_groups = consolidate_duplicate_groups(l1_pairs + l2_pairs)
    return MerchantDuplicateGroupList(
        groups=[
            MerchantDuplicateGroup(**g) for g in merged_groups
        ],
        l1_count=len(l1_pairs),
        l2_count=len(l2_pairs),
        l2_status="ok",
    )


@router.post(
    "/duplicates/apply",
    response_model=MerchantDuplicateApplyResult,
    response_model_by_alias=False,
)
async def apply_duplicate_deletions(
    payload: MerchantDuplicateApplyRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> MerchantDuplicateApplyResult:
    """Soft-delete (is_archived=True) a list of candidate rule ids.

    The route is the apply-side of the dedup wizard: the FE POSTs
    the user's accepted candidates and the route archives them. The
    canonical is NEVER touched (the wizard never sends canonical
    ids in the candidate_ids list — see the FE's
    ``deduplicateWizardModal`` apply handler for the client-side
    invariant; the BE enforces it defensively below).

    Idempotent: a re-fire of Apply on an already-archived row is a
    no-op (increments ``skipped`` instead of ``archived``) so the
    wizard can re-fire on flaky network without double-archiving.

    Defensive cross-checks:

    - Empty ``candidate_ids`` → returns ``(archived=0, skipped=0)``
      with HTTP 200 (a 422 would force the FE to render an error
      banner for a perfectly valid "Apply nothing" click that the
      wizard might issue during a state-sync round-trip).
    - Unknown id → counted in ``skipped`` (404-vs-200 trade-off:
      a 404 forces the FE to refetch the list before re-trying;
      a 200 with a structured counter keeps the wizard
      non-blocking).
    - id that is the canonical of any active group → REJECTED with
      HTTP 400 ("Cannot archive the canonical of an active dedup
      group"). Defensive: a buggy client that mixes canonical +
      candidate ids would otherwise nuke the dedup target.

    Each successful archive updates ``updated_at`` so the FE's
    optimistic-UI tickers stay in sync.
    """
    if not payload.candidate_ids:
        return MerchantDuplicateApplyResult(archived=0, skipped=0)

    # Find the canonical ids of every dedup group so the route can
    # REJECT any candidate_ids entry that is also a canonical. The
    # check runs BEFORE the archive so a buggy client that mixes
    # canonical + candidate ids fails loudly (400) rather than
    # silently nuking a dedup target.
    canonical_ids: set[int] = set()
    for pair in find_substring_duplicates(db):
        canonical_ids.add(int(pair["canonical_id"]))
    # Pull the candidate rules in one SELECT so we can archive
    # them in a single round-trip.
    candidate_ids_set = {int(x) for x in payload.candidate_ids}
    conflicting = candidate_ids_set & canonical_ids
    if conflicting:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot archive a rule that is the canonical of an "
                "active dedup group (ids: "
                f"{sorted(conflicting)}). The dedup wizard should "
                "send candidates only, not canonicals."
            ),
        )

    rows = (
        db.query(MerchantRule)
        .filter(MerchantRule.id.in_(candidate_ids_set))
        .all()
    )
    found_ids = {r.id for r in rows}
    archived = 0
    skipped = len(candidate_ids_set - found_ids)
    for rule in rows:
        if rule.is_archived:
            skipped += 1
            continue
        rule.is_archived = True
        rule.updated_at = _now_utc()
        db.add(rule)
        archived += 1
    if archived > 0:
        db.commit()
    return MerchantDuplicateApplyResult(
        archived=archived, skipped=skipped
    )
