"""Ownership and read-only context helpers for INV-01."""
from .contracts import InvestmentContext, ReadOnlyInvestmentRequest
from .errors import InvestmentFailure


def validate_owner_scope(context: InvestmentContext, owner_id: int) -> InvestmentContext:
    """Reject cross-owner context before any context is exposed or used."""
    if context.owner_id != owner_id:
        raise ValueError(InvestmentFailure.UNAUTHORIZED.value)
    return context


def build_read_only_request(
    *, owner_id: int, account_ids: tuple[int, ...], question: str
) -> ReadOnlyInvestmentRequest:
    """Build a request containing scope and intent only, never financial facts."""
    return ReadOnlyInvestmentRequest(
        owner_id=owner_id,
        account_ids=account_ids,
        question=question,
    )
