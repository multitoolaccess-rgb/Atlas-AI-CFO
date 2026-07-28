"""Trusted, bounded canonical financial-state contract for Phase 1.

Rules Service receives canonical financial state only through the narrow
``FinlynqProjectionStateAdapter`` protocol.  This module deliberately has no
database imports, HTTP clients, route registration, or persistence behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROJECTION_STATE_SCHEMA_VERSION = "atlas-projection-state/v1"
CANONICAL_JSON_VERSION = "atlas-canonical-json/v1"
HASH_SCHEMA_VERSION = "atlas-input-state-hash/v1"
HASH_ALGORITHM = "sha256"
MAX_ABSOLUTE_MONEY = Decimal("1E+24")
MAX_COMPONENTS = 32
MAX_PROVENANCE_REFERENCES = 32
MAX_MISSING_DATA_CODES = 16
MAX_IDENTIFIER_LENGTH = 128
MAX_IDEMPOTENCY_KEY_LENGTH = 255
MAX_GOAL_ID = 9_223_372_036_854_775_807
MAX_DECIMAL_TOTAL_DIGITS = 38
MAX_DECIMAL_SCALE = 18
MAX_DECIMAL_ENCODED_LENGTH = 40

_CANONICAL_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9._:-]*$")
_SHA256 = re.compile(r"[0-9a-f]{64}$")
_UTC_RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
_CollectionItem = TypeVar("_CollectionItem")


class CanonicalStateValidationError(ValueError):
    """Raised when server-owned canonical-state contract data is invalid."""


def canonical_decimal_string(value: Decimal | str) -> str:
    """Return the sole unrounded string form accepted by canonical snapshots."""

    if isinstance(value, bool):
        raise CanonicalStateValidationError("decimal values must be strings or Decimal")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CanonicalStateValidationError("value must be a finite Decimal") from exc
    if not decimal_value.is_finite():
        raise CanonicalStateValidationError("value must be a finite Decimal")
    sign, digits, exponent = decimal_value.as_tuple()
    if not any(digits):
        return "0"
    coefficient = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        integral = coefficient + ("0" * exponent)
        fractional = ""
    else:
        decimal_point = len(coefficient) + exponent
        if decimal_point > 0:
            integral = coefficient[:decimal_point]
            fractional = coefficient[decimal_point:]
        else:
            integral = "0"
            fractional = ("0" * -decimal_point) + coefficient
    integral = integral.lstrip("0") or "0"
    fractional = fractional.rstrip("0")
    result = integral if not fractional else f"{integral}.{fractional}"
    return f"-{result}" if sign else result


def _validate_canonical_decimal(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_DECIMAL_ENCODED_LENGTH
        or not _CANONICAL_DECIMAL.fullmatch(value)
    ):
        raise ValueError("must be a canonical unrounded decimal string")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:  # defensive; the pattern already excludes it
        raise ValueError("must be a canonical unrounded decimal string") from exc
    if not decimal_value.is_finite() or abs(decimal_value) > MAX_ABSOLUTE_MONEY:
        raise ValueError("must be a finite decimal within the financial input bound")
    unsigned = value.removeprefix("-")
    integral, separator, fractional = unsigned.partition(".")
    if (
        len(integral) + len(fractional) > MAX_DECIMAL_TOTAL_DIGITS
        or (separator and len(fractional) > MAX_DECIMAL_SCALE)
    ):
        raise ValueError(
            "must not exceed v1 decimal total-digit or fractional-scale bounds"
        )
    if canonical_decimal_string(decimal_value) != value:
        raise ValueError("must not include insignificant decimal zeros")
    return value


def _validate_identifier(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_IDENTIFIER_LENGTH
        or not _IDENTIFIER.fullmatch(value)
    ):
        raise ValueError("must be a bounded lowercase stable identifier")
    return value


def _validate_utc_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not _UTC_RFC3339.fullmatch(value):
        raise ValueError("must be a canonical UTC RFC 3339 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("must be a valid UTC RFC 3339 timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError("must be a UTC RFC 3339 timestamp")
    return value


def _canonicalize_collection(
    items: tuple[_CollectionItem, ...],
    *,
    name: str,
    identity: Callable[[_CollectionItem], tuple[str, ...]],
) -> tuple[_CollectionItem, ...]:
    identities = [identity(item) for item in items]
    if len(set(identities)) != len(identities):
        raise ValueError(f"{name} must not contain duplicate stable identities")
    return tuple(sorted(items, key=identity))


def _coerce_json_array_to_tuple(value: Any) -> Any:
    """Accept JSON arrays while preserving immutable validated model state."""

    return tuple(value) if isinstance(value, list) else value


class _StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CanonicalizationMetadata(_StrictContractModel):
    canonical_json_version: Literal[CANONICAL_JSON_VERSION]
    hash_schema_version: Literal[HASH_SCHEMA_VERSION]
    hash_algorithm: Literal[HASH_ALGORITHM]


class CurrentValueComponent(_StrictContractModel):
    kind: Literal["cash", "investment", "debt", "other_asset"]
    amount: str
    source_reference: str
    observed_at: str

    _amount = field_validator("amount")(_validate_canonical_decimal)
    _source_reference = field_validator("source_reference")(_validate_identifier)
    _observed_at = field_validator("observed_at")(_validate_utc_timestamp)


class ContributionInput(_StrictContractModel):
    kind: Literal["monthly_investable_cash_flow"]
    amount: str
    source_reference: str
    observed_at: str

    _amount = field_validator("amount")(_validate_canonical_decimal)
    _source_reference = field_validator("source_reference")(_validate_identifier)
    _observed_at = field_validator("observed_at")(_validate_utc_timestamp)


class FreshnessMetadata(_StrictContractModel):
    max_data_age_days: int = Field(ge=0, le=366)
    observed_age_days: int = Field(ge=0, le=366)
    source_updated_at: str

    _source_updated_at = field_validator("source_updated_at")(_validate_utc_timestamp)

    @field_validator("observed_age_days")
    @classmethod
    def observed_age_must_fit_policy(cls, value: int, info: Any) -> int:
        maximum = info.data.get("max_data_age_days")
        if maximum is not None and value > maximum:
            raise ValueError("must not exceed max_data_age_days")
        return value


class ProvenanceReference(_StrictContractModel):
    source_system: str
    reference_id: str
    observed_at: str
    record_count: int = Field(ge=0, le=1_000_000)
    source_state_hash: str

    _source_system = field_validator("source_system")(_validate_identifier)
    _reference_id = field_validator("reference_id")(_validate_identifier)
    _observed_at = field_validator("observed_at")(_validate_utc_timestamp)

    @field_validator("source_state_hash")
    @classmethod
    def source_hash_must_be_sha256(cls, value: str) -> str:
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 digest")
        return value


class CanonicalProjectionState(_StrictContractModel):
    """Versioned, privacy-minimized input envelope created by the trusted adapter."""

    schema_version: Literal[PROJECTION_STATE_SCHEMA_VERSION]
    canonicalization: CanonicalizationMetadata
    user_id: str
    goal_id: int = Field(gt=0, le=MAX_GOAL_ID)
    as_of_timestamp: str
    currency: Literal["USD"]
    current_value_components: tuple[CurrentValueComponent, ...] = Field(
        min_length=1, max_length=MAX_COMPONENTS
    )
    contribution_inputs: tuple[ContributionInput, ...] = Field(
        min_length=1, max_length=MAX_COMPONENTS
    )
    freshness: FreshnessMetadata
    provenance: tuple[ProvenanceReference, ...] = Field(
        min_length=1, max_length=MAX_PROVENANCE_REFERENCES
    )
    missing_data_codes: tuple[str, ...] = Field(max_length=MAX_MISSING_DATA_CODES)
    reconciliation_state: Literal["reconciled", "partial", "unavailable"]

    _user_id = field_validator("user_id")(_validate_identifier)
    _as_of_timestamp = field_validator("as_of_timestamp")(_validate_utc_timestamp)
    _current_value_components_json = field_validator(
        "current_value_components", mode="before"
    )(_coerce_json_array_to_tuple)
    _contribution_inputs_json = field_validator(
        "contribution_inputs", mode="before"
    )(_coerce_json_array_to_tuple)
    _provenance_json = field_validator("provenance", mode="before")(
        _coerce_json_array_to_tuple
    )
    _missing_data_codes_json = field_validator("missing_data_codes", mode="before")(
        _coerce_json_array_to_tuple
    )

    @field_validator("current_value_components")
    @classmethod
    def canonicalize_current_value_components(
        cls, value: tuple[CurrentValueComponent, ...]
    ) -> tuple[CurrentValueComponent, ...]:
        return _canonicalize_collection(
            value,
            name="current_value_components",
            identity=lambda item: (item.kind, item.source_reference, item.observed_at),
        )

    @field_validator("contribution_inputs")
    @classmethod
    def canonicalize_contribution_inputs(
        cls, value: tuple[ContributionInput, ...]
    ) -> tuple[ContributionInput, ...]:
        return _canonicalize_collection(
            value,
            name="contribution_inputs",
            identity=lambda item: (item.kind, item.source_reference, item.observed_at),
        )

    @field_validator("provenance")
    @classmethod
    def canonicalize_provenance(
        cls, value: tuple[ProvenanceReference, ...]
    ) -> tuple[ProvenanceReference, ...]:
        return _canonicalize_collection(
            value,
            name="provenance",
            identity=lambda item: (
                item.source_system,
                item.reference_id,
                item.observed_at,
            ),
        )

    @field_validator("missing_data_codes")
    @classmethod
    def missing_data_codes_must_be_bounded_identifiers(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicate codes")
        return tuple(sorted(_validate_identifier(code) for code in value))

    def hash_payload(self) -> dict[str, Any]:
        """Return the exact normalized adapter envelope used by v1 input hashing."""

        return self.model_dump(mode="python")


class GenerationControlBody(_StrictContractModel):
    """Empty body contract; generation controls are bounded request headers only."""


class FinlynqProjectionStateAdapter(Protocol):
    """Sanctioned server-side boundary; implementations own Finlynq access."""

    def load_projection_state(
        self, *, user_id: str, goal_id: int
    ) -> CanonicalProjectionState:
        """Load canonical state for an already authenticated and authorized goal."""


def parse_generation_control_body(payload: Mapping[str, Any]) -> GenerationControlBody:
    """Reject every client-supplied body field before adapter or state access."""

    return GenerationControlBody.model_validate(payload)


def validate_idempotency_key(value: str) -> str:
    """Validate the bounded client control header without persisting its plaintext."""

    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_IDEMPOTENCY_KEY_LENGTH
        or any(ord(character) < 33 or ord(character) > 126 for character in value)
    ):
        raise CanonicalStateValidationError(
            "Idempotency-Key must be 1-255 visible ASCII characters"
        )
    return value


def load_authoritative_projection_state(
    *,
    adapter: FinlynqProjectionStateAdapter,
    server_user_id: str,
    server_goal_id: int,
) -> CanonicalProjectionState:
    """Invoke the adapter once and bind its output to server-authorized scope."""

    state = adapter.load_projection_state(
        user_id=server_user_id,
        goal_id=server_goal_id,
    )
    if not isinstance(state, CanonicalProjectionState):
        raise CanonicalStateValidationError(
            "trusted adapter must return CanonicalProjectionState"
        )
    if state.user_id != server_user_id:
        raise CanonicalStateValidationError(
            "trusted adapter state does not match the authorized user"
        )
    if state.goal_id != server_goal_id:
        raise CanonicalStateValidationError(
            "trusted adapter state does not match the authorized goal"
        )
    return state


def _canonicalize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        raise CanonicalStateValidationError(
            "binary floating-point is not canonical JSON input"
        )
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, datetime):
        if value.tzinfo != timezone.utc:
            raise CanonicalStateValidationError("timestamps must be timezone-aware UTC")
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalStateValidationError(
                    "canonical JSON object keys must be strings"
                )
            normalized[key] = _canonicalize_json_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_canonicalize_json_value(item) for item in value]
    raise CanonicalStateValidationError("unsupported canonical JSON value")


def canonical_json(value: Any) -> str:
    """Serialize a normalized value with stable UTF-8 JSON v1 rules."""

    return json.dumps(
        _canonicalize_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def hash_input_state(state: CanonicalProjectionState) -> str:
    """Return the lowercase SHA-256 digest of the v1 canonical envelope."""

    if state.canonicalization.hash_schema_version != HASH_SCHEMA_VERSION:
        raise CanonicalStateValidationError("unsupported input-state hash schema")
    digest = hashlib.sha256(canonical_json(state.hash_payload()).encode("utf-8"))
    return digest.hexdigest()


def canonicalize_legacy_float_target(value: float) -> dict[str, Any]:
    """Document a lossy legacy Goal Float conversion without claiming recovery."""

    if (
        isinstance(value, bool)
        or not isinstance(value, float)
        or not math.isfinite(value)
    ):
        raise CanonicalStateValidationError("legacy goal target must be a finite float")
    amount = canonical_decimal_string(Decimal(str(value)))
    try:
        _validate_canonical_decimal(amount)
    except ValueError as exc:
        raise CanonicalStateValidationError(
            "legacy goal target exceeds v1 decimal bounds"
        ) from exc
    return {
        "amount": amount,
        "source_representation": "float",
        "conversion": "Decimal(str(value))",
        "precision_restored": False,
    }
