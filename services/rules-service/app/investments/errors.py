"""Sanitized failure classes for the Investment Intelligence boundary."""
from enum import StrEnum


class InvestmentFailure(StrEnum):
    """Stable user-safe categories; provider details never cross the API boundary."""

    DISABLED = "disabled"
    UNAUTHORIZED = "unauthorized"
    INVALID_CONTEXT = "invalid_context"
    UNKNOWN_SECURITY = "unknown_security"
    STALE_DATA = "stale_data"
    AMBIGUOUS_CURRENCY = "ambiguous_currency"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_OUTPUT_INVALID = "model_output_invalid"
