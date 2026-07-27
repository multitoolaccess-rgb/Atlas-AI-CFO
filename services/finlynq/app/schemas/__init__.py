"""Finlynq Pydantic schemas -- wire-shape parity with rules-service.

Phase F1 ship target: just enough types for ``StateOut`` so the
``List[dict]`` problem the F1-code-reviewer flagged is not propagated
to the F5 implementation.

Reviewer round-3 hardening: each shape is **wire-parity** with the
matching rules-service response schema -- either a strict superset OR
a deliberate subset with documented rationale (only
``AccountSummary.account_number`` today). Pydantic v2 default is
``extra=ignore`` on response models, so any fields the upstream
SQLAlchemy row carries but Finlynq's shape omits would be silently
dropped on the wire -- defeating the "Finlynq is the canonical store"
contract. Widening (with one deliberate omission) makes the wire
shape aligned with rules-service's emission today.

**Deliberate omissions (today: only ``AccountSummary.account_number``):**

- ``AccountSummary.account_number`` -- a deliberate-subset decision
  rooted in canonical-store discipline, NOT in masking. Verified by
  direct reading of ``services/rules-service/app/routes/users.py``,
  ``services/rules-service/app/schemas/__init__.py``, and
  ``services/rules-service/app/models/account.py``: rules-service
  does NOT mask ``account_number`` at the route layer; the column
  comment is `# masked` but the schema + ORM + route accept and
  emit raw values. The actual rationale here is canonical-store
  hygiene: the Finlynq canonical store is a strict-subset of the
  read-side projection until a Phase F5+ decision introduces a
  dedicated ``account_number_masked`` shape. Re-adding the bare
  field would silently re-widen the wire and is caught by the
  load-bearing test
  ``tests/test_state_endpoint_contract.py::test_account_summary_emits_no_known_pii_columns``.

  If a future phase needs an account-number surface for Finlynq
  consumers, add a NEW DELIBERATE masked-shape field (e.g.
  ``account_number_masked: Optional[str]``) -- do NOT re-add this
  field. Update the deny-list constant ``_KNOWN_DENY`` in the test
  to whitelist the new shape by exact name, then add it to the
  Architecture Decision Record in ``docs/architecture.md``
  cross-service section (TODO: F5+).

**Cross-service consistency** is locked by
``tests/test_cross_service_schema.py`` (added in Phase F5 alongside
the dashboard forwarder):
- The wire-level field set of each shape here matches the
  ``rules-service/app/schemas`` shape with the SAME name (except
  the documented deliberate omissions).
- A rename on either side breaks the integration test immediately.

These shapes are NOT a full lift of ``rules-service/app/schemas``:
the full lift would re-couple the two services at compile-time via
a sibling import cycle. Lift only what's read by ``/state`` +
``/state/summary`` + the F3-F5 forwarders.
"""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# Account provenance enum — mirrors rules-service's AccountSource
# Literal so the cross-service annotation-parity test passes.
AccountSource = Literal["manual", "imported", "plaid"]


class AccountSummary(BaseModel):
    """Account summary returned in ``GET /state``.

    Wire-parity with rules-service's ``AccountResponse`` --
    DELIBERATE SUBSET, omitting ``account_number`` (raw value not
    carried by Finlynq canonical store; see
    ``app/schemas/__init__.py`` module docstring for the rationale).
    Includes ``account_subtype`` and ``last_sync`` so banker's
    mental model is preserved when the agent reasons across accounts
    (e.g. checking vs credit card). The optionality here matters:
    a row with NULL ``last_sync`` (account never imported from) must
    round-trip OK at F5.

    Phase-F7 cross-service parity: the following fields are added
    to match rules-service ``AccountResponse`` so the forwarder
    re-emits the Finlynq shape without 422-ing the FE:
    ``family_member_id``, ``source``, ``description``,
    ``interest_rate``, ``credit_limit``, ``minimum_payment``,
    ``term_months``.
    """
    id: int
    account_name: str
    account_type: str
    account_subtype: Optional[str] = None
    current_balance: float
    is_active: bool
    last_sync: Optional[datetime] = None
    family_member_id: Optional[int] = None
    source: Optional[AccountSource] = None
    description: Optional[str] = None
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    term_months: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionSummary(BaseModel):
    """Transaction summary returned in ``GET /state``.

    Wire-parity (strict superset) with rules-service's
    ``TransactionResponse`` field set, INCLUDING the Phase-11
    joinedload flattening fields
    ``account_name``/``account_type``/``category_name``. Without
    these, the agent's ``finlynq_get_state`` tool receives raw
    ``account_id``/``category_id`` integers with no human-readable
    labels -- defeats the tool's purpose.

    Optionality invariant (Round-5 reviewer hardening): the six
    "label" fields MUST be ``Optional[...]`` AND default to ``None``
    -- a JSON client omitting any of these key gets ``null`` on the
    wire, not a 422 ValidationError. Tightening this to non-Optional
    or to a default other than ``None`` would silently break the
    OpenAPI client contract.

    Phase-F7 cross-service parity: ``debit``, ``credit``,
    ``is_duplicate``, ``duplicate_of_id`` added to match rules-service
    ``TransactionResponse`` (Phase-52 split-bookkeeping + duplicate
    tracking). All Optional with ``= None``/``= False`` defaults so
    Finlynq rows without these columns round-trip safely.
    """
    id: int
    description: str
    amount: float
    transaction_date: datetime
    merchant_name: Optional[str] = None
    is_pending: bool
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    account_type: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    debit: Optional[float] = None
    credit: Optional[float] = None
    is_duplicate: bool = False
    duplicate_of_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class GoalSummary(BaseModel):
    """Goal summary returned in ``GET /state``.

    Wire-parity (strict superset) with rules-service's
    ``GoalResponse`` -- includes ``notes``, ``created_at``,
    ``updated_at``. Optionality invariant (Round-5 reviewer
    hardening): ``target_date`` + ``horizon_years`` are
    ``Optional[...]`` with ``= None`` default for open-ended goals;
    ``notes`` + timestamps are Optional/defensive. Tightening any
    of these to non-Optional OR non-None default would 422 a
    legitimate F5 round-trip for any NULL column.
    """
    id: int
    name: str
    target_amount: float
    target_date: Optional[date] = None
    horizon_years: Optional[int] = None
    priority: int
    is_archived: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Phase-F7 cross-service parity constants.
# ----------------------------------------------------------------------
#
# Pin the Optional[...] -> None fields on each shape by STRICTNESS:
#
# - ``_STRICT_NONE_FIELDS`` -- annotation MUST be ``Optional[...]``
#   AND default MUST be exactly ``None``. A PR flipping any of
#   these to a non-Optional annotation OR removing the ``= None``
#   default is a regression -- the FE would 422 on JSON omission.
#   Round-6 reviewer hardening lives in this strictness class.
#
# - ``_TRANSITIONAL_NONE_FIELDS`` -- annotation MUST be
#   ``Optional[...]`` but a ``default_factory`` (e.g. ``lambda:
#   datetime.now(timezone.utc)`` for ``created_at`` / ``updated_at``)
#   is permitted. Phase-F2/F3 may migrate these fields via
#   ``default_factory`` without breaking the FE JSON contract.
#
# ``last_sync`` is in TRANSITIONAL because it's the canonical
# place a future phase might pre-fill the last import-batch
# timestamp via ``default_factory`` (zero-touch migration).
#
# Load-bearing for ``tests/test_cross_service_schema.py`` -- the
# cross-service parity test would assert a seam in the JSON wire
# contract if the ``= None`` default silently drifted away.
_STRICT_NONE_FIELDS: dict[str, frozenset[str]] = {
    "AccountSummary": frozenset({
        "account_subtype", "family_member_id", "source",
        "description", "interest_rate", "credit_limit",
        "minimum_payment", "term_months",
    }),
    "TransactionSummary": frozenset({
        "merchant_name", "account_id", "account_name",
        "account_type", "category_id", "category_name",
        "duplicate_of_id",
    }),
    "GoalSummary": frozenset({"target_date", "horizon_years", "notes"}),
}

_TRANSITIONAL_NONE_FIELDS: dict[str, frozenset[str]] = {
    "AccountSummary": frozenset({"last_sync"}),
    "TransactionSummary": frozenset(),
    "GoalSummary": frozenset({"created_at", "updated_at"}),
}
