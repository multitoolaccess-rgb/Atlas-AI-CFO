"""Phase-F7 cross-service schema parity test.

Compare Finlynq's wire-shape Pydantic models (AccountSummary /
TransactionSummary / GoalSummary) against rules-service's response
models (AccountResponse / TransactionResponse / GoalResponse) at the
class+field level. Catches drift early: a field rename on either
side breaks the cross-service contract the rules-service 5-line
httpx forwarder at ``POST /api/imports/upload`` depends on.

Two hard invariants:

1. **Field-name parity**: every Finlynq field (minus the documented
   ``AccountSummary.account_number`` omission) must have a matching
   field name in the corresponding rules-service schema. AND every
   rules-service schema field must have a matching Finlynq field (no
   silent additions on either side).

2. **Annotation parity**: the underlying type of each shared field
   must match (after stripping ``Optional[...]``/``Union[X, None]``
   wrappers). Partial mismatches would 422 the FE on a serialised
   row.

Plus a phase-F7 inverse-problem lock on PII-shaped field names.

The rules-service schemas are loaded via :mod:`importlib` with an
isolated module-name to avoid clobbering Finlynq's ``app.schemas``
in :data:`sys.modules` (Finlynq's pytest discovery has its own
``app`` package; the cross-service test therefore side-loads
rules-service's schemas into a private module).
"""
import importlib.util
import sys
from pathlib import Path
from typing import Optional, Union, get_args, get_origin

import pytest

REPO = Path(__file__).resolve().parents[3]
_RS_DIR = REPO / "services" / "rules-service"
_RS_SCHEMAS_PATH = _RS_DIR / "app" / "schemas" / "__init__.py"

# rules-service's schemas/__init__.py imports `app.account_types` which
# only exists on rules-service's directory. Since Finlynq's `app` is
# already in sys.modules, Python would resolve `app.account_types`
# against Finlynq's package (which doesn't have it). Fix: pre-load
# `app.account_types` from rules-service's path into sys.modules so
# the schemas module finds it.
_rs_dir_str = str(_RS_DIR)
_account_types_path = _RS_DIR / "app" / "account_types.py"
_added_rs_to_path = False
if _rs_dir_str not in sys.path:
    sys.path.insert(0, _rs_dir_str)
    _added_rs_to_path = True

# Pre-load app.account_types from rules-service so the schemas import
# resolves without hitting Finlynq's app package.
if _account_types_path.is_file() and "app.account_types" not in sys.modules:
    _at_spec = importlib.util.spec_from_file_location(
        "app.account_types", str(_account_types_path)
    )
    _at_mod = importlib.util.module_from_spec(_at_spec)
    sys.modules["app.account_types"] = _at_mod
    _at_spec.loader.exec_module(_at_mod)

# Load rules-service's schemas as an isolated module (NOT overriding
# Finlynq's `app.schemas` in sys.modules).
_spec = importlib.util.spec_from_file_location("_rules_service_schemas", str(_RS_SCHEMAS_PATH))
_rs_schemas = importlib.util.module_from_spec(_spec)
sys.modules["_rules_service_schemas"] = _rs_schemas
_spec.loader.exec_module(_rs_schemas)

# Clean up: remove the temporary sys.path entry and the injected
# module so they don't leak into other tests in the same process.
if _added_rs_to_path:
    sys.path.remove(_rs_dir_str)
sys.modules.pop("app.account_types", None)

AccountResponse = _rs_schemas.AccountResponse
TransactionResponse = _rs_schemas.TransactionResponse
GoalResponse = _rs_schemas.GoalResponse

# Finlynq's local schemas (current process's `app.schemas`).
from app.schemas import (  # noqa: E402
    AccountSummary,
    GoalSummary,
    TransactionSummary,
    _STRICT_NONE_FIELDS,
    _TRANSITIONAL_NONE_FIELDS,
)


# --- Documented asymmetries ---

# Documented field-name asymmetries between Finlynq and rules-service.
# A pair (cls, field) here is exempt from BOTH the field-name parity
# lock AND the PII-suffix regex inverse test, because Finlynq canonical-
# store hygiene deliberately drops account_number from its summary
# while rules-service's AccountResponse continues to surface the value
# (it's the per-row projection the FE used before Finlynq landed).
#
# Adding ``(AccountResponse, account_number)`` to the set lets the
# PII-suffix test stay focused on NEW additions without flagging the
# pre-F7 grandfathered field on the rules-service side.
#
# See ``services/finlynq/app/schemas/__init__.py`` module docstring for
# the canonical-store rationale.
DOCUMENTED_OMISSIONS: frozenset[tuple[str, str]] = frozenset({
    ("AccountSummary", "account_number"),
    ("AccountResponse", "account_number"),
})


# --- PII-suffix regex for the inverse-problem lock ---

# A field name whose suffix matches any of the canonical PII patterns
# is presumed to violate the privacy policy. The inverse-problem
# framing: enumerate FORBIDDEN field-name patterns instead of
# enumerating ALLOWED ones; any future accidental addition (e.g. a
# backfill column named ``routing_number_seen_by_crm``) trips this
# without requiring the maintainer to add it to an allow-list.
import re
_PII_SUFFIX_RE = re.compile(
    r"(account_number|routing_number|iban|ssn|ssn_last_4|tax_id)(\b|$)",
    re.IGNORECASE,
)


# --- Schema pairs ---

# Maps Finlynq schema -> rules-service schema.
_SCHEMA_PAIRS = [
    (AccountSummary, AccountResponse),
    (TransactionSummary, TransactionResponse),
    (GoalSummary, GoalResponse),
]


# --- Helpers ---


def _unwrap_optional(annotation):
    """If ``annotation`` is ``Optional[X]`` (== ``Union[X, None]``), return X.

    Used by the annotation-parity assertion to compare the underlying
    type (the ``None`` arm shouldn't break parity).
    """
    if get_origin(annotation) is Union and type(None) in get_args(annotation):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _is_optional(annotation) -> bool:
    return get_origin(annotation) is Union and type(None) in get_args(annotation)


# --- Tests ---


@pytest.mark.parametrize("finlynq_cls,rules_cls", _SCHEMA_PAIRS, ids=lambda c: c.__name__)
def test_field_name_parity_minus_documented_omissions(finlynq_cls, rules_cls):
    """Names of Finlynq fields must be a subset of rules-service
    fields, minus the documented ``AccountSummary.account_number``
    omission. Reverse direction: rules-service must NOT have a field
    that Finlynq silently drops (it'd round-trip a 422 because the
    forwarder re-emits the Finlynq response verbatim — rules-service
    has no opportunity to add the missing field).
    """
    finlynq_keys = set(finlynq_cls.model_fields.keys())
    rules_keys = set(rules_cls.model_fields.keys())

    # Finlynq ⊆ rules_service minus documented omissions.
    extra_in_finlynq = (
        finlynq_keys - rules_keys - {f for cls, f in DOCUMENTED_OMISSIONS if cls == finlynq_cls.__name__}
    )
    assert not extra_in_finlynq, (
        f"{finlynq_cls.__name__} has fields not present in "
        f"{rules_cls.__name__} (besides documented omissions): "
        f"{sorted(extra_in_finlynq)!r}. Update the cross-service contract "
        f"or add to DOCUMENTED_OMISSIONS."
    )

    # The reverse: every rules-service field MUST appear in Finlynq
    # (or be a documented omission). Catches FINLYNQ dropping a field
    # the FE consumes today (e.g. GoalResponse's `notes` field).
    missing_in_finlynq = (
        rules_keys - finlynq_keys - {f for cls, f in DOCUMENTED_OMISSIONS if cls == finlynq_cls.__name__}
    )
    assert not missing_in_finlynq, (
        f"{rules_cls.__name__} has fields not present in "
        f"{finlynq_cls.__name__}: {sorted(missing_in_finlynq)!r}. "
        f"Finlynq must mirror rules-service's emission today so the FE "
        f"seamlessly transitions when rules-service becomes a Finlynq "
        f"forwarder in a later phase."
    )


@pytest.mark.parametrize("finlynq_cls,rules_cls", _SCHEMA_PAIRS, ids=lambda c: c.__name__)
def test_annotation_parity(finlynq_cls, rules_cls):
    """The underlying annotation type of each shared field must match
    (Optional[...] vs Optional[...] is fine; X vs Y is not).
    """
    finlynq_fields = finlynq_cls.model_fields
    for field_name, finlynq_info in finlynq_fields.items():
        if (finlynq_cls.__name__, field_name) in DOCUMENTED_OMISSIONS:
            continue
        rules_info = rules_cls.model_fields.get(field_name)
        assert rules_info is not None, (
            f"Upstream drift: {finlynq_cls.__name__}.{field_name} has "
            f"no counterpart in {rules_cls.__name__}. Should have been "
            f"caught by test_field_name_parity_minus_documented_omissions."
        )
        ft = _unwrap_optional(finlynq_info.annotation)
        rt = _unwrap_optional(rules_info.annotation)
        assert ft == rt, (
            f"{finlynq_cls.__name__}.{field_name} annotation {ft!r} "
            f"!= {rules_cls.__name__}.{field_name} annotation {rt!r}. "
            f"Cross-service wire-shape mismatch — would 422 the FE "
            f"on a serialised row from rules-service's read paths."
        )


@pytest.mark.parametrize("finlynq_cls,rules_cls", _SCHEMA_PAIRS, ids=lambda c: c.__name__)
def test_strict_none_fields_have_optional_annotation_and_none_default(finlynq_cls, rules_cls):
    """Phase-F7 STRICT lock: every field in ``_STRICT_NONE_FIELDS[cls]``
    MUST be ``Optional[...]`` AND its default MUST be exactly
    ``None``. Mirrors the round-6 widening-pin from
    ``tests/test_state_endpoint_contract.py``.
    """
    strict_set = _STRICT_NONE_FIELDS.get(finlynq_cls.__name__, frozenset())
    for field_name in strict_set:
        assert field_name in finlynq_cls.model_fields, (
            f"{finlynq_cls.__name__}.{field_name} is registered as "
            f"STRICT but does not exist on the schema. Remove from "
            f"_STRICT_NONE_FIELDS or re-add the field."
        )
        info = finlynq_cls.model_fields[field_name]
        assert _is_optional(info.annotation), (
            f"{finlynq_cls.__name__}.{field_name} annotation MUST "
            f"be Optional[...] (got {info.annotation!r}). Tightening to "
            f"non-Optional would 422 the FE wire serialization for any "
            f"row with NULL in this column."
        )
        assert info.default is None, (
            f"{finlynq_cls.__name__}.{field_name} default MUST be "
            f"exactly None (got {info.default!r}). A PR removing the "
            f"``= None`` default would make the field 'required' at "
            f"the JSON wire -- any POST/PUT body omitting the key "
            f"would 422."
        )


@pytest.mark.parametrize("finlynq_cls,rules_cls", _SCHEMA_PAIRS, ids=lambda c: c.__name__)
def test_transitional_none_fields_have_optional_annotation(finlynq_cls, rules_cls):
    """Phase-F7 TRANSITIONAL lock: every field in
    ``_TRANSITIONAL_NONE_FIELDS[cls]`` MUST be ``Optional[...]``
    BUT the default MAY be a ``default_factory`` (rather than
    strictly ``None``). Time-stamp fields like ``created_at`` /
    ``updated_at`` / ``last_sync`` are likely candidates for a
    future ``default_factory=lambda: datetime.now(timezone.utc)``
    migration.
    """
    transitional_set = _TRANSITIONAL_NONE_FIELDS.get(finlynq_cls.__name__, frozenset())
    for field_name in transitional_set:
        assert field_name in finlynq_cls.model_fields, (
            f"{finlynq_cls.__name__}.{field_name} is registered as "
            f"TRANSITIONAL but does not exist on the schema."
        )
        info = finlynq_cls.model_fields[field_name]
        assert _is_optional(info.annotation), (
            f"{finlynq_cls.__name__}.{field_name} annotation MUST "
            f"be Optional[...] (got {info.annotation!r}). Even "
            f"TRANSITIONAL fields can't drift to non-Optional -- the "
            f"FE expects nullable."
        )
        # Note: do NOT assert default is None here. ``default_factory``
        # is permitted for TRANSITIONAL fields.
        if info.default is not None and info.default_factory is None:
            pytest.fail(
                f"{finlynq_cls.__name__}.{field_name} has a non-None "
                f"default ({info.default!r}) and no default_factory. "
                f"Either pass — explicitly via default_factory (transitional "
                f"intent) or via None."
            )


@pytest.mark.parametrize("finlynq_cls,rules_cls", _SCHEMA_PAIRS, ids=lambda c: c.__name__)
def test_no_pii_suffix_field_name_on_either_schema(finlynq_cls, rules_cls):
    """Phase-F7 inverse-problem lock: enumerate FORBIDDEN
    PII-suffix patterns; assert NEITHER schema carries a field whose
    name matches. Existing ``AccountSummary.account_number`` AND
    ``AccountResponse.account_number`` are documented exceptions
    (Finlynq canonical store deliberate subset decision; rules-service
    continues to surface the value the FE used before Finlynq landed —
    the privacy policy is enforced at Finlynq's wire shape, not at
    rules-service's pre-F7 read projection).

    Adding a future field whose suffix matches the regex trips the
    inverse test before the PR lands; the existing grandfathered
    account_number stays exempt.
    """
    for field_name in finlynq_cls.model_fields.keys():
        if _PII_SUFFIX_RE.search(field_name):
            if (finlynq_cls.__name__, field_name) in DOCUMENTED_OMISSIONS:
                continue
            pytest.fail(
                f"PII-suffix pattern matched Finlynq schema: "
                f"{finlynq_cls.__name__}.{field_name}. Update "
                f"_KNOWN_PII_DENY_LIST or add a masked-shape variant "
                f"(e.g. ``account_number_masked``); do NOT re-add the "
                f"raw PII field."
            )
    for field_name in rules_cls.model_fields.keys():
        if _PII_SUFFIX_RE.search(field_name):
            if (rules_cls.__name__, field_name) in DOCUMENTED_OMISSIONS:
                continue
            pytest.fail(
                f"PII-suffix pattern matched rules-service schema: "
                f"{rules_cls.__name__}.{field_name}. Privacy policy "
                f"violation on a NEW addition — the grandfathered "
                f"account_number is exempt via DOCUMENTED_OMISSIONS."
            )
