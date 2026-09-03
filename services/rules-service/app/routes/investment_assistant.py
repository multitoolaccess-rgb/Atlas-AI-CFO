"""UI-10 investment-context API.

This route resolves selectors into server-owned, validated context. It does not
invoke an LLM and cannot mutate investment state.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.routes.shared import get_or_create_local_user
from app.investments.assistant_context import (
    AssistantContextError,
    AssistantContextRequest,
    InvestmentAssistantContext,
    resolve_investment_context,
)
from app.investments.assistant_response import InvestmentAssistantQueryRequest, InvestmentAssistantResponse
from app.investments.persistence_repository import InvestmentRepository
from app.investments.assistant_tools import run_investment_tool
from app.investments.assistant_context import InvestmentAssistantToolRequest, InvestmentAssistantToolResult
from app.investments.assistant_response import AssistantModelOffline, execute_investment_query, offline_response

router = APIRouter(prefix="/api/v1/investments/assistant", tags=["investment-assistant"])


@router.post("/tool", response_model=InvestmentAssistantToolResult)
def run_tool(
    request: InvestmentAssistantToolRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> InvestmentAssistantToolResult:
    """Run the single allowlisted read-only investment tool."""
    local_user = get_or_create_local_user(db, current_user)
    try:
        return run_investment_tool(repository=InvestmentRepository(db), owner_id=local_user.id, request=request)
    except AssistantContextError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/query", response_model=InvestmentAssistantResponse)
async def query_investment_context(
    request: InvestmentAssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> InvestmentAssistantResponse:
    """Answer a contextual investment question through the isolated UI-10 path."""
    local_user = get_or_create_local_user(db, current_user)
    try:
        return await execute_investment_query(
            repository=InvestmentRepository(db), owner_id=local_user.id, request=request,
        )
    except AssistantModelOffline:
        context_request = AssistantContextRequest(selector=request.selector, max_evidence=request.max_evidence)
        context = resolve_investment_context(repository=InvestmentRepository(db), owner_id=local_user.id, request=context_request)
        return offline_response(context)
    except AssistantContextError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/context", response_model=InvestmentAssistantContext)
def resolve_context(
    request: AssistantContextRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(require_user),
) -> InvestmentAssistantContext:
    """Resolve owner-scoped selectors into a bounded trusted context envelope."""
    local_user = get_or_create_local_user(db, current_user)
    try:
        return resolve_investment_context(
            repository=InvestmentRepository(db),
            owner_id=local_user.id,
            request=request,
        )
    except AssistantContextError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["router"]
