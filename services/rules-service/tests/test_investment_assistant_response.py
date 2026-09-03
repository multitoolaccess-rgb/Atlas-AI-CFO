import pytest

from app.investments.assistant_context import InvestmentAssistantContext, AssistantContextState
from app.investments.assistant_response import AssistantResponseValidationError, validate_investment_response


def _context() -> InvestmentAssistantContext:
    return InvestmentAssistantContext(
        context_id="investment-context:test",
        owner_id=1,
        state=AssistantContextState.READY,
        resolved_at="2026-01-01T00:00:00Z",
        context_as_of="2025-12-31T00:00:00Z",
        source_hashes=("a" * 64,),
    )


def test_fact_requires_resolved_citation():
    result = validate_investment_response(
        context=_context(),
        payload={"sections": [{"kind": "fact", "text": "Observed", "citations": [{"citation_id": "c1", "source_hash": "a" * 64, "source_type": "evidence"}]}]},
    )
    assert result.status == "ok"
    assert result.sections[0].citations[0].trust == "atlas_validated"


def test_fact_without_citation_fails_closed():
    with pytest.raises(AssistantResponseValidationError):
        validate_investment_response(context=_context(), payload={"sections": [{"kind": "fact", "text": "Invented"}]})


def test_unknown_citation_fails_closed():
    with pytest.raises(AssistantResponseValidationError):
        validate_investment_response(
            context=_context(),
            payload={"sections": [{"kind": "fact", "text": "Unknown", "citations": [{"citation_id": "c1", "source_hash": "b" * 64, "source_type": "evidence"}]}]},
        )
