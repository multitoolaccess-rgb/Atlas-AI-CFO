"""UI-10 allowlisted, read-only investment assistant tools."""
from __future__ import annotations

from .assistant_context import (
    AssistantContextRequest,
    InvestmentAssistantToolName,
    InvestmentAssistantToolRequest,
    InvestmentAssistantToolResult,
    resolve_investment_context,
)
from .persistence_repository import InvestmentRepository


class InvestmentAssistantToolError(ValueError):
    """Sanitized tool boundary failure."""


READ_ONLY_INVESTMENT_TOOLS = frozenset({InvestmentAssistantToolName.GET_CONTEXT.value})


def run_investment_tool(*, repository: InvestmentRepository, owner_id: int, request: InvestmentAssistantToolRequest) -> InvestmentAssistantToolResult:
    """Dispatch only the fixed read-only tool; owner scope is server-derived."""
    if request.tool not in READ_ONLY_INVESTMENT_TOOLS:
        raise InvestmentAssistantToolError("investment tool is not permitted")
    context = resolve_investment_context(
        repository=repository,
        owner_id=owner_id,
        request=AssistantContextRequest(selector=request.selector, max_evidence=request.max_evidence),
    )
    return InvestmentAssistantToolResult(tool=request.tool, context=context)


__all__ = ["InvestmentAssistantToolError", "READ_ONLY_INVESTMENT_TOOLS", "run_investment_tool"]
