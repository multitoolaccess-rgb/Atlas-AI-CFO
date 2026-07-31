"""Bounded Pydantic schemas for the Phase 1 versioned forecast API.

Single rewrite boundary for every wire shape the rules-service ships
under ``/api/v1/forecasts*``.  Slice D's routes compose these
``BaseModel`` RO classes directly without re-declaring fields.

Phase-1 invariants enforced here:

- Decimal money is STRICTLY canonical string form (no float, no
  exponent, no insignificant zeros) validated via
  ``canonical_state.canonical_decimal_string``.
- Timestamps are timezone-aware UTC RFC 3339 with a ``Z`` suffix.
- Currency is the literal ``"USD"`` — Phase 1 rejects any other code.
- Snapshots mirror ``app.forecasts.snapshots`` exactly.
- Error envelopes are sanitized: NO rejected input values, NO echo
  of client field names beyond the bounded location list.
- Every model uses ``extra="forbid"`` so a future leak of a
  financial field via a new attribute is blocked at the schema layer.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.forecasts.canonical_state import (
    HASH_SCHEMA_VERSION,
    MAX_IDENTIFIER_LENGTH,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    PROJECTION_STATE_SCHEMA_VERSION,
    canonical_decimal_string,
    validate_idempotency_key,
)
from app.forecasts.snapshots import (
    ASSUMPTION_SCHEMA_VERSION,
    CALCULATION_DECIMAL_SCHEMA_VERSION,
    TARGET_DECISION_SCHEMA_VERSION,
)


# ============================================================
# Base config helpers
# ============================================================

def _phase1_response_config() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        frozen=True,
        strict=False,
        hide_input_in_errors=True,
    )


def _phase1_request_config() -> ConfigDict:
    return ConfigDict(
        extra="forbid",
        frozen=False,
        strict=False,
        hide_input_in_errors=True,
    )


# ============================================================
# Atom validators (used by every field_validator below)
# ============================================================

_UTC_RFC3339_Z = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
_SHA256_HEX = re.compile(r"[0-9a-f]{64}$")
_BOUNDED_IDENTIFIER = re.compile(r"[a-z][a-z0-9._:-]*$")
_UUID_LOWER = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _check_canonical_decimal(v: Any) -> str:
    canonical_decimal_string(v)
    return v if isinstance(v, str) else canonical_decimal_string(Decimal(str(v)))


def _check_utc_rfc3339_z(v: Any) -> str:
    if not isinstance(v, str) or not _UTC_RFC3339_Z.fullmatch(v):
        raise ValueError("must be canonical UTC RFC 3339 timestamp ending in Z")
    parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise ValueError("must be UTC RFC 3339 timestamp")
    return v


def _check_sha256_hex(v: Any) -> str:
    if not isinstance(v, str) or not _SHA256_HEX.fullmatch(v):
        raise ValueError("must be lowercase SHA-256 digest")
    return v


def _check_bounded_identifier(v: Any) -> str:
    if (
        not isinstance(v, str)
        or not 1 <= len(v) <= MAX_IDENTIFIER_LENGTH
        or not _BOUNDED_IDENTIFIER.fullmatch(v)
    ):
        raise ValueError("must be bounded lowercase identifier")
    return v


def _check_uuid_lower(v: Any) -> str:
    if not isinstance(v, str) or not _UUID_LOWER.fullmatch(v):
        raise ValueError("must be lowercase canonical UUID")
    return v


# ============================================================
# Stable error code constants
# ============================================================

ERROR_CODE_FORECAST_GENERATION_UNAVAILABLE: Final[str] = "forecast_generation_unavailable"
ERROR_CODE_FORECAST_VERSION_CONFLICT: Final[str] = "forecast_version_conflict"
ERROR_CODE_IDEMPOTENCY_CONFLICT: Final[str] = "idempotency_conflict"
ERROR_CODE_GOAL_NOT_FOUND: Final[str] = "goal_not_found"
ERROR_CODE_FORECAST_NOT_FOUND: Final[str] = "forecast_not_found"
ERROR_CODE_FORECAST_VALIDATION: Final[str] = "forecast_validation_error"
ERROR_CODE_READ_API_DISABLED: Final[str] = "forecast_read_api_unavailable"
ERROR_CODE_PRECONDITION_FAILED: Final[str] = "precondition_failed"
ERROR_CODE_BAD_REQUEST: Final[str] = "bad_request"


# ============================================================
# Sanitized validation error envelope (400/422)
# ============================================================

class ValidationErrorEntry(BaseModel):
    """Bounded location + stable Pydantic category; NO rejected input value."""

    model_config = _phase1_response_config()

    loc: tuple[str | int, ...] = Field(
        ...,
        min_length=1,
        max_length=8,
        description=(
            "Bounded path to the offending value. The fixed "
            "``<extra-field>`` token replaces unknown client JSON keys; "
            "the ``<truncated-location>`` token replaces paths deeper "
            "than the bounded depth."
        ),
    )
    type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Stable Pydantic error category; client-safe.",
    )


class ValidationErrorEnvelope(BaseModel):
    """400/422 envelope emitted by every forecast endpoint."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_FORECAST_VALIDATION] = ERROR_CODE_FORECAST_VALIDATION
    message: Literal["Invalid forecast request."] = "Invalid forecast request."
    errors: tuple[ValidationErrorEntry, ...] = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Ordered, deduplicated sanitized validation findings.",
    )

    @field_validator("errors")
    @classmethod
    def _errors_unique_loc(
        cls, value: tuple[ValidationErrorEntry, ...]
    ) -> tuple[ValidationErrorEntry, ...]:
        seen: set[tuple[tuple[str, ...], str]] = set()
        for entry in value:
            key = (tuple(str(p) for p in entry.loc), entry.type)
            if key in seen:
                raise ValueError("duplicate sanitized error location")
            seen.add(key)
        return value


# ============================================================
# Stable 4xx / 5xx envelope models
# ============================================================

class GoalNotFoundEnvelope(BaseModel):
    """404 envelope returned BEFORE adapter invocation (non-disclosing)."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_GOAL_NOT_FOUND] = ERROR_CODE_GOAL_NOT_FOUND
    message: Literal["Goal not found."] = "Goal not found."


class ForecastNotFoundEnvelope(BaseModel):
    """404 envelope when a forecast (or version) is missing for the caller."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_FORECAST_NOT_FOUND] = ERROR_CODE_FORECAST_NOT_FOUND
    message: Literal["Forecast not found."] = "Forecast not found."


class ForecastVersionConflictEnvelope(BaseModel):
    """409 envelope returned when ``If-Match`` is stale."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_FORECAST_VERSION_CONFLICT] = ERROR_CODE_FORECAST_VERSION_CONFLICT
    message: Literal["Forecast version conflict."] = "Forecast version conflict."
    current_etag: str = Field(
        ...,
        min_length=1,
        max_length=96,
        description="Bare server-derived ETag for the current latest version (JSON path is unquoted).",
    )
    latest_version_number: int = Field(
        ...,
        ge=1,
        le=9_999_999_999,
        description="Current latest immutable version number.",
    )


class IdempotencyConflictEnvelope(BaseModel):
    """409 envelope returned when an idempotency key collides with a different state."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_IDEMPOTENCY_CONFLICT] = ERROR_CODE_IDEMPOTENCY_CONFLICT
    message: Literal["Idempotency-Key conflict."] = "Idempotency-Key conflict."


class PreconditionFailedEnvelope(BaseModel):
    """412 envelope returned when ``If-None-Match: *`` collides with existing state
    or when ``If-Match`` references a version that does not exist yet."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_PRECONDITION_FAILED] = ERROR_CODE_PRECONDITION_FAILED
    message: Literal["Forecast precondition failed."] = "Forecast precondition failed."


class BadRequestEnvelope(BaseModel):
    """400 envelope returned when the request is structurally invalid (e.g., mutually
    contradictory conditional headers).  No rejected input value is echoed."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_BAD_REQUEST] = ERROR_CODE_BAD_REQUEST
    message: Literal["Invalid forecast request."] = "Invalid forecast request."
    errors: tuple[ValidationErrorEntry, ...] = Field(
        default_factory=tuple,
        max_length=64,
        description="Ordered, deduplicated sanitized findings; same shape as ValidationErrorEnvelope.",
    )

    @field_validator("errors")
    @classmethod
    def _errors_unique_loc(
        cls, value: tuple[ValidationErrorEntry, ...]
    ) -> tuple[ValidationErrorEntry, ...]:
        seen: set[tuple[tuple[str, ...], str]] = set()
        for entry in value:
            key = (tuple(str(p) for p in entry.loc), entry.type)
            if key in seen:
                raise ValueError("duplicate sanitized error location")
            seen.add(key)
        return value


class ForecastGenerationDisabledEnvelope(BaseModel):
    """503 envelope returned when ``ATLAS_FORECAST_PERSISTENCE_ENABLED`` is off."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_FORECAST_GENERATION_UNAVAILABLE] = ERROR_CODE_FORECAST_GENERATION_UNAVAILABLE
    message: Literal[
        "Forecast persistence is currently unavailable."
    ] = "Forecast persistence is currently unavailable."


class ReadApiDisabledEnvelope(BaseModel):
    """503 envelope returned when ``ATLAS_FORECAST_READ_API_ENABLED`` is off."""

    model_config = _phase1_response_config()

    code: Literal[ERROR_CODE_READ_API_DISABLED] = ERROR_CODE_READ_API_DISABLED
    message: Literal["Forecast read API is currently unavailable."] = (
        "Forecast read API is currently unavailable."
    )


# ============================================================
# Header validation models
# ============================================================

class IdempotencyKeyHeader(BaseModel):
    """Validated Phase-1 ``Idempotency-Key`` header value."""

    model_config = _phase1_request_config()

    value: str = Field(
        ...,
        min_length=1,
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
        description="Bounded 1-255 visible-ASCII client request token.",
    )

    @field_validator("value")
    @classmethod
    def _must_be_visible_ascii(cls, v: Any) -> str:
        return validate_idempotency_key(v)

    def sha256_hex(self) -> str:
        """Return the SHA-256 digest of the validated key.  Never log the plaintext."""
        return hashlib.sha256(self.value.encode("ascii")).hexdigest()


class _EtagOrWildcardMixin(BaseModel):
    """Shared validator for ``If-Match`` and ``If-None-Match`` header values."""

    value: str = Field(
        ...,
        min_length=1,
        max_length=96,
        description="Quoted ETag or '*'.",
    )

    @field_validator("value")
    @classmethod
    def _must_be_quoted_etag_or_wildcard(cls, v: Any) -> str:
        from app.forecasts.api_codecs import parse_forecast_etag_header
        try:
            parse_forecast_etag_header(v)
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        return v


class IfMatchHeader(_EtagOrWildcardMixin):
    """Validated ``If-Match`` header value."""

    model_config = _phase1_request_config()


class IfNoneMatchHeader(_EtagOrWildcardMixin):
    """Validated ``If-None-Match`` header value."""

    model_config = _phase1_request_config()


class GenerationRequestEnvelope(BaseModel):
    """Strict empty body for ``POST /api/v1/goals/{goal_id}/forecasts``."""

    model_config = _phase1_request_config()


# ============================================================
# Bounded ETag validator (used by response models)
# ============================================================

_ETAG_BARE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-v[1-9][0-9]{0,9}$"
)


def _check_bare_etag(v: Any) -> str:
    if not isinstance(v, str) or not _ETAG_BARE.fullmatch(v) or len(v) > 96:
        raise ValueError("must be the bare server-derived ETag (uuid-v-n)")
    return v


# ============================================================
# Snapshot sub-models (Phase 1 wire shape)
# ============================================================

class AssumptionSnapshotSchema(BaseModel):
    """Mirror of ``app.forecasts.snapshots`` assumption envelope."""

    model_config = _phase1_response_config()

    assumption_schema_version: Literal[ASSUMPTION_SCHEMA_VERSION] = ASSUMPTION_SCHEMA_VERSION
    assumption_profile: str = Field(..., min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    annual_return_rates: tuple[tuple[str, str], ...] = Field(..., min_length=1, max_length=8)
    annual_inflation_rate: str
    contribution_timing: Literal["beginning", "end"]
    period: Literal["monthly"]
    rounding_rule: Literal["ROUND_HALF_EVEN"]
    money_precision: Literal["0.01"]
    goal_inputs: tuple[tuple[str, str], ...] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="Bounded goal-target sub-object (target_amount / horizon / target_date).",
    )

    @field_validator("annual_return_rates")
    @classmethod
    def _rates_are_canonical_decimals(cls, v: Any) -> Any:
        keys = {"conservative", "base", "optimistic"}
        seen: set[str] = set()
        for pair in v:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("annual_return_rates entries must be (name, decimal)")
            name, decimal = pair
            if name not in keys:
                raise ValueError("annual_return_rates name must be conservative/base/optimistic")
            _check_canonical_decimal(decimal)
            if name in seen:
                raise ValueError("duplicate scenario in annual_return_rates")
            seen.add(name)
        return v

    @field_validator("annual_inflation_rate")
    @classmethod
    def _inflation_is_canonical(cls, v: Any) -> str:
        return _check_canonical_decimal(v)

    @field_validator("goal_inputs")
    @classmethod
    def _goal_inputs_bounded(cls, v: Any) -> Any:
        for pair in v:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("goal_inputs entries must be (name, value)")
            name, value = pair
            if name not in {"target_amount", "horizon_years", "target_date"}:
                raise ValueError("goal_inputs key must be target_amount/horizon_years/target_date")
        return v


class TargetDecisionV2Schema(BaseModel):
    """``atlas-target-decision/v2`` decision envelope."""

    model_config = _phase1_response_config()

    decision_schema_version: Literal[TARGET_DECISION_SCHEMA_VERSION] = TARGET_DECISION_SCHEMA_VERSION
    scenario: Literal["base"]
    comparison: Literal["greater_than_or_equal"]
    decision_basis: Literal["currency_rounded"]
    rounding_rule: Literal["ROUND_HALF_EVEN"]
    money_precision: Literal["0.01"]
    unrounded_ending_balance: str
    unrounded_target_amount: str
    rounded_ending_balance: str
    rounded_target_amount: str
    target_status: bool

    @field_validator("unrounded_ending_balance", "unrounded_target_amount",
                     "rounded_ending_balance", "rounded_target_amount")
    @classmethod
    def _money_is_canonical(cls, v: Any) -> str:
        return _check_canonical_decimal(v)

    @model_validator(mode="after")
    def _rounded_quantizes_to_unrounded(self) -> "TargetDecisionV2Schema":
        from decimal import ROUND_HALF_EVEN
        for unrounded_name, rounded_name in (
            ("unrounded_ending_balance", "rounded_ending_balance"),
            ("unrounded_target_amount", "rounded_target_amount"),
        ):
            unrounded = Decimal(getattr(self, unrounded_name))
            rounded = Decimal(getattr(self, rounded_name))
            if unrounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN) != rounded:
                raise ValueError(
                    f"{rounded_name} must equal {unrounded_name} quantized to 0.01 ROUND_HALF_EVEN"
                )
        return self

    @model_validator(mode="after")
    def _target_status_consistent(self) -> "TargetDecisionV2Schema":
        rounded_ending = Decimal(self.rounded_ending_balance)
        rounded_target = Decimal(self.rounded_target_amount)
        expected = rounded_ending >= rounded_target
        if self.target_status != expected:
            raise ValueError("target_status must equal rounded_ending_balance >= rounded_target_amount")
        return self


class ScenarioSnapshotSchema(BaseModel):
    model_config = _phase1_response_config()

    annual_return_rate: str
    monthly_real_rate: str
    ending_balance: str
    investment_growth: str
    target_gap: str | None
    reaches_target: bool

    @field_validator("annual_return_rate", "ending_balance", "investment_growth")
    @classmethod
    def _money_is_canonical(cls, v: Any) -> str:
        return _check_canonical_decimal(v)

    @field_validator("monthly_real_rate")
    @classmethod
    def _rate_is_canonical(cls, v: Any) -> str:
        # Calculation-decimal (atlas-calculation-decimal/v1) shape: canonical form
        # validated by ``canonical_decimal_string`` (the same validator).
        return _check_canonical_decimal(v)

    @field_validator("target_gap")
    @classmethod
    def _optional_money_is_canonical_or_none(cls, v: Any) -> Any:
        if v is None:
            return None
        return _check_canonical_decimal(v)


class DriversSnapshotSchema(BaseModel):
    model_config = _phase1_response_config()

    current_balance: str
    monthly_contribution: str
    total_contributions: str
    target_amount: str | None
    horizon_months: int = Field(..., ge=1, le=720)
    data_as_of: str
    data_age_days: int = Field(..., ge=0, le=366)

    @field_validator("current_balance", "monthly_contribution", "total_contributions")
    @classmethod
    def _money_is_canonical(cls, v: Any) -> str:
        return _check_canonical_decimal(v)

    @field_validator("target_amount")
    @classmethod
    def _optional_money_or_none(cls, v: Any) -> Any:
        if v is None:
            return None
        return _check_canonical_decimal(v)

    @field_validator("data_as_of")
    @classmethod
    def _timestamp_is_utc_z(cls, v: Any) -> str:
        return _check_utc_rfc3339_z(v)


class OutputSnapshotSchema(BaseModel):
    model_config = _phase1_response_config()

    calculation_decimal_schema_version: Literal[CALCULATION_DECIMAL_SCHEMA_VERSION] = (
        CALCULATION_DECIMAL_SCHEMA_VERSION
    )
    target_status: bool
    target_decision: TargetDecisionV2Schema
    drivers: DriversSnapshotSchema
    scenarios: tuple[tuple[str, ScenarioSnapshotSchema], ...] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="Ordered scenario snapshots keyed by conservative/base/optimistic.",
    )

    @field_validator("scenarios")
    @classmethod
    def _scenarios_match_phase1_set(cls, v: Any) -> Any:
        keys = {"conservative", "base", "optimistic"}
        seen: set[str] = set()
        for pair in v:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("scenarios entries must be (name, snapshot)")
            name, _ = pair
            if name not in keys:
                raise ValueError("scenarios key must be conservative/base/optimistic")
            if name in seen:
                raise ValueError("duplicate scenario in scenarios")
            seen.add(name)
        return v

    @model_validator(mode="after")
    def _base_target_status_matches(self) -> "OutputSnapshotSchema":
        base = next(value for key, value in self.scenarios if key == "base")
        if base.reaches_target != self.target_status:
            raise ValueError("output_snapshot.target_status must equal base.reaches_target")
        return self


class ProvenanceSnapshotSchema(BaseModel):
    model_config = _phase1_response_config()

    provenance: tuple[dict[str, Any], ...] = Field(..., min_length=1, max_length=32)
    freshness: dict[str, Any] = Field(..., min_length=1, max_length=MAX_IDENTIFIER_LENGTH)


# ============================================================
# Forecast + Version response models
# ============================================================

class ForecastLink(BaseModel):
    """HATEOAS-ish link object — bounded rel names."""

    model_config = _phase1_response_config()

    rel: str = Field(..., min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    href: str = Field(..., min_length=1, max_length=512)


class SnapshotMetaSchema(BaseModel):
    """Snapshot / hash / model / calculation version labels for a version envelope."""

    model_config = _phase1_response_config()

    snapshot_schema_version: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Bounded wire-format version (no whitespace).",
    )
    hash_schema_version: Literal[HASH_SCHEMA_VERSION] = HASH_SCHEMA_VERSION
    model_version: str = Field(..., min_length=1, max_length=128)
    calculation_version: str = Field(..., min_length=1, max_length=128)

    @field_validator("snapshot_schema_version", "model_version", "calculation_version")
    @classmethod
    def _no_whitespace(cls, v: Any) -> str:
        if isinstance(v, str) and 1 <= len(v) <= 128 and not any(c.isspace() for c in v):
            return v
        raise ValueError("must be bounded printable-ASCII identifier with no whitespace")


class ForecastResponse(BaseModel):
    """Single ``GET /api/v1/forecasts/{forecast_id}`` envelope."""

    model_config = _phase1_response_config()

    forecast_id: str
    goal_id: int = Field(..., ge=1, le=9_223_372_036_854_775_807)
    forecast_kind: Literal["goal_projection"]
    currency: Literal["USD"]
    lifecycle_state: Literal["active"]
    latest_version_number: int = Field(..., ge=1, le=9_999_999_999)
    etag: str = Field(..., min_length=1, max_length=96)
    latest_version_id: str | None = None
    created_at: str
    updated_at: str
    versions_schema_version: Literal[PROJECTION_STATE_SCHEMA_VERSION] = (
        PROJECTION_STATE_SCHEMA_VERSION
    )
    links: tuple[ForecastLink, ...] = Field(default_factory=tuple, max_length=8)

    @field_validator("forecast_id", "latest_version_id")
    @classmethod
    def _is_uuid_lower(cls, v: Any) -> Any:
        if v is None:
            return None
        return _check_uuid_lower(v)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _is_utc_z(cls, v: Any) -> str:
        return _check_utc_rfc3339_z(v)

    @field_validator("etag")
    @classmethod
    def _is_bare_etag(cls, v: Any) -> str:
        return _check_bare_etag(v)


class ForecastVersionResponse(BaseModel):
    """Single immutable version envelope (returned by all versioned read endpoints)."""

    model_config = _phase1_response_config()

    forecast_id: str
    version_id: str
    version_number: int = Field(..., ge=1, le=9_999_999_999)
    etag: str = Field(..., min_length=1, max_length=96)
    input_state_hash: str
    idempotency_key_hash: str
    snapshot: SnapshotMetaSchema
    currency: Literal["USD"]
    calculated_at: str
    data_as_of: str
    max_data_age_days: int = Field(..., ge=0, le=366)
    data_age_days: int = Field(..., ge=0, le=366)
    created_at: str
    ending_balance: str
    target_gap: str
    target_status: bool
    target_decision: TargetDecisionV2Schema
    drivers: DriversSnapshotSchema
    scenarios: OutputSnapshotSchema
    assumption_snapshot: AssumptionSnapshotSchema
    provenance_snapshot: ProvenanceSnapshotSchema
    input_snapshot: dict[str, Any] = Field(default_factory=dict, max_length=MAX_IDENTIFIER_LENGTH)
    links: tuple[ForecastLink, ...] = Field(default_factory=tuple, max_length=8)

    @field_validator("forecast_id", "version_id")
    @classmethod
    def _is_uuid_lower(cls, v: Any) -> str:
        return _check_uuid_lower(v)

    @field_validator("input_state_hash", "idempotency_key_hash")
    @classmethod
    def _is_sha256(cls, v: Any) -> str:
        return _check_sha256_hex(v)

    @field_validator("calculated_at", "data_as_of", "created_at")
    @classmethod
    def _is_utc_z(cls, v: Any) -> str:
        return _check_utc_rfc3339_z(v)

    @field_validator("ending_balance", "target_gap")
    @classmethod
    def _money_is_canonical(cls, v: Any) -> str:
        return _check_canonical_decimal(v)

    @field_validator("etag")
    @classmethod
    def _is_bare_etag(cls, v: Any) -> str:
        return _check_bare_etag(v)

    @model_validator(mode="after")
    def _top_level_target_status_matches(self) -> "ForecastVersionResponse":
        if self.target_status != self.target_decision.target_status:
            raise ValueError("target_status must mirror target_decision.target_status")
        if self.target_status != self.scenarios.target_status:
            raise ValueError("target_status must mirror scenarios.target_status")
        return self


class ForecastListResponse(BaseModel):
    """Cursor-paged ``GET /api/v1/forecasts`` envelope."""

    model_config = _phase1_response_config()

    items: tuple[ForecastResponse, ...] = Field(..., min_length=0, max_length=64)
    next_cursor: str | None = Field(default=None, max_length=256)

    @field_validator("next_cursor")
    @classmethod
    def _cursor_is_well_formed(cls, v: Any) -> Any:
        if v is None:
            return None
        from app.forecasts.api_codecs import decode_forecast_cursor
        decode_forecast_cursor(v)
        return v


class ForecastVersionListResponse(BaseModel):
    """Cursor-paged ``GET /api/v1/forecasts/{forecast_id}/versions`` envelope."""

    model_config = _phase1_response_config()

    items: tuple[ForecastVersionResponse, ...] = Field(..., min_length=0, max_length=64)
    next_cursor: str | None = Field(default=None, max_length=256)

    @field_validator("next_cursor")
    @classmethod
    def _cursor_is_well_formed(cls, v: Any) -> Any:
        if v is None:
            return None
        from app.forecasts.api_codecs import decode_forecast_cursor
        decode_forecast_cursor(v)
        return v
