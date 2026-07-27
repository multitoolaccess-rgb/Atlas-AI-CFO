"""Phase 30a + 30c + 30e — Assistant chat + conversation + streaming routes.

POST /api/assistant/chat — auth-enforced endpoint that accepts a
user message, dispatches to the assistant orchestrator, and returns
the LLM's reply + tool metadata + follow-up suggestions + conversation
metadata (Phase 30c).

POST /api/assistant/chat/stream — SSE streaming variant. Yields
``thinking``, ``conversation``, ``tool_call``, ``tool_result``,
``reply_chunk``, and ``done`` events so the FE can render incremental
progress + inline tool cards (Phase 30e).

GET  /api/assistant/conversations — list the user's conversations
(newest first).

GET  /api/assistant/conversations/{id} — fetch a single conversation
with all its messages.
"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import AssistantConversation, AssistantMessage
from app.routes.shared import get_or_create_local_user
from app.schemas import (
    AssistantChatRequest,
    AssistantConversationResponse,
    AssistantMessageResponse,
    AssistantResponse,
)
from app.services.assistant_orchestrator import orchestrate, orchestrate_stream

LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _message_to_response(msg: AssistantMessage) -> AssistantMessageResponse:
    """Convert an AssistantMessage ORM row to a Pydantic response."""
    follow_ups: list[str] = []
    if msg.follow_ups:
        try:
            follow_ups = json.loads(msg.follow_ups)
        except (json.JSONDecodeError, TypeError):
            follow_ups = []

    tool_result: dict | None = None
    if msg.tool_result:
        try:
            tool_result = json.loads(msg.tool_result)
        except (json.JSONDecodeError, TypeError):
            tool_result = None

    return AssistantMessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        tool_used=msg.tool_used,
        tool_result=tool_result,
        follow_ups=follow_ups,
        status=msg.status,
        created_at=msg.created_at,
    )


@router.post("/chat", response_model=AssistantResponse)
async def chat(
    payload: AssistantChatRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> AssistantResponse:
    """Process a user message and return a tool-backed assistant reply.

    The orchestrator loads SOUL.md + STYLE.md into the system prompt,
    asks the local Ollama LLM to pick a tool, dispatches to the tool
    registry, then feeds the result back to the LLM for a natural-
    language answer. If Ollama is unreachable, returns ``status=
    "offline"`` with a graceful fallback reply (no 500).

    Phase 30c — if ``conversation_id`` is provided, the message is
    appended to that conversation's history for multi-turn context.
    If omitted, a new conversation is created and its id is returned.
    """
    local_user = get_or_create_local_user(db, _current_user)

    result = await orchestrate(
        message=payload.message,
        db=db,
        user_sub=local_user.local_user_sub,
        user_id=local_user.id,
        conversation_id=payload.conversation_id,
    )

    return AssistantResponse(**result)


@router.post("/chat/stream")
async def chat_stream(
    payload: AssistantChatRequest,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> StreamingResponse:
    """SSE streaming variant of ``POST /api/assistant/chat``.

    Yields Server-Sent Events with the following event types:
    - ``conversation`` — conversation id + title (emitted first).
    - ``thinking`` — the orchestrator is processing.
    - ``tool_call`` — the LLM picked a tool; params included.
    - ``tool_result`` — the tool returned; result included.
    - ``reply_chunk`` — a chunk of the natural-language reply.
    - ``done`` — the full response (final state).

    The FE uses ``fetch`` + ``ReadableStream`` to consume the stream
    (EventSource doesn't support POST bodies). Each event is a
    ``data: {json}\n\n`` line per the SSE spec.
    """
    local_user = get_or_create_local_user(db, _current_user)

    async def _event_generator():
        async for event in orchestrate_stream(
            message=payload.message,
            db=db,
            user_sub=local_user.local_user_sub,
            user_id=local_user.id,
            conversation_id=payload.conversation_id,
        ):
            event_type = event.get("event", "message")
            event_data = json.dumps(event.get("data", {}))
            yield f"event: {event_type}\ndata: {event_data}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/conversations", response_model=List[AssistantConversationResponse])
async def list_conversations(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> List[AssistantConversationResponse]:
    """List the user's conversations, newest first.

    Returns conversations WITHOUT messages (the FE sidebar only needs
    the title + timestamps; messages are loaded on-demand when the
    user clicks a conversation via the GET /{id} endpoint).
    """
    local_user = get_or_create_local_user(db, _current_user)
    convs = (
        db.query(AssistantConversation)
        .filter(AssistantConversation.user_id == local_user.id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(50)
        .all()
    )
    return [
        AssistantConversationResponse(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            messages=[],
        )
        for c in convs
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=AssistantConversationResponse,
)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
) -> AssistantConversationResponse:
    """Fetch a single conversation with all its messages.

    The messages are ordered by id ascending (chronological) so the
    FE can render them in the correct order.
    """
    local_user = get_or_create_local_user(db, _current_user)
    conv = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == local_user.id,
        )
        .first()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    messages = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.id.asc())
        .all()
    )

    return AssistantConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_message_to_response(m) for m in messages],
    )
