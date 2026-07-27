"""Phase 30a + 30b + 30c + 30d + 30e — Assistant orchestrator.

The orchestrator is the bridge between the user's natural-language
message and deterministic backend "tools". The flow is:

1. Load the system prompt (SOUL.md + STYLE.md + force-admit-uncertainty
   rules).
2. Resolve or create the conversation; load prior message history
   (Phase 30c) so the LLM has multi-turn context.
3. Send the user's message + history to the local Ollama LLM with a
   tool-calling prompt that asks the model to pick a tool + params
   from a fixed whitelist.
4. Dispatch to the selected tool.
5. Feed the tool result back to the LLM for a natural-language answer.
6. Persist the user message + assistant reply to the conversation
   (Phase 30c).
7. Return ``AssistantResponse`` with the reply, tool metadata,
   follow-up suggestions, and conversation id.

If Ollama is unreachable, the orchestrator returns a graceful fallback
response with ``status="offline"`` rather than a 500 — the FE renders
an offline banner and the user can retry.

Locked decisions (see ``docs/phase-30-plan.md``):
- SSE streaming in 30e (``orchestrate_stream`` generator).
- SOUL.md + STYLE.md loaded into the system prompt.
- Force-admit-uncertainty: every numeric answer MUST come from a tool
  call; if no tool covers the question, the model must say "I can't
  answer that yet" rather than guess.
- Phase 30c: conversations auto-pruned to last 50 per user.
- Phase 30d: 11 tools total (5 base + search_history + 5 analysis).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import httpx
from sqlalchemy.orm import Session

from app.models import AssistantConversation, AssistantMessage
from app.services.finance_query import (
    compare_periods,
    compute_investable_surplus,
    compute_savings_rate,
    detect_anomalies,
    get_cash_flow,
    get_category_spend,
    get_merchant_spend,
    get_totals,
    get_trends,
    predict_upcoming_bills,
)
from app.services.llm_client import (
    DEFAULT_MODEL,
    OLLAMA_DEFAULT_BASE_URL,
    post_ollama_chat_async,
)

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# System prompt — loads SOUL.md + STYLE.md from disk.
# ---------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_AGENTS_DIR = _PROJECT_ROOT / "agents" / "finance-copilot"

_FALLBACK_SOUL = (
    "You are a calm, analytical, local-first financial copilot. "
    "No direct trade execution. No leverage by default. Long-term oriented."
)
_FALLBACK_STYLE = "Calm, precise, numeric, non-hype."

_UNCERTAINTY_RULES = """
CRITICAL RULES — violation is a show-stopper:
1. Every numeric answer MUST come from a tool call. If no available
   tool covers the user's question, you MUST reply:
   "I can't answer that yet — I don't have a tool for [topic]."
   Do NOT guess, estimate, or fabricate any number.
2. If a tool returns an error or empty result, say so honestly.
3. If you are uncertain about ANYTHING, say "I'm not sure" rather
   than presenting a confident-sounding guess.
4. Never recommend specific trades, stocks, or leverage.
"""


def _load_agent_file(filename: str, fallback: str) -> str:
    """Load an agent persona file from disk, falling back to an
    inline default if the file is missing."""
    path = _AGENTS_DIR / filename
    try:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return content
    except (FileNotFoundError, OSError) as exc:
        LOG.warning("Could not read %s: %s — using fallback", path, exc)
    return fallback


def build_system_prompt() -> str:
    """Assemble the system prompt from SOUL.md + STYLE.md + uncertainty
    rules + the tool whitelist."""
    soul = _load_agent_file("SOUL.md", _FALLBACK_SOUL)
    style = _load_agent_file("STYLE.md", _FALLBACK_STYLE)
    tool_list = ", ".join(f'"{name}"' for name in TOOLS)
    return (
        f"{soul}\n\n"
        f"Communication style: {style}\n\n"
        f"{_UNCERTAINTY_RULES}\n\n"
        f"Available tools: {tool_list}\n\n"
        "When the user asks a question, respond with a JSON object with "
        "this exact shape (no prose):\n"
        "{\n"
        '  "tool": "<one of the available tools, or "none">,\n'
        '  "params": {<tool-specific parameters>},\n'
        '  "intent": "<short description of what the user wants>"\n'
        "}\n\n"
        "If no tool fits, set \"tool\": \"none\" and \"params\": {}."
    )


# ---------------------------------------------------------------------
# Tools — Phase 30b ships 5 real DB query tools.
# ---------------------------------------------------------------------


def _tool_get_totals(db: Session, params: dict, user_id: int) -> dict:
    """Real: total balance + current-month income + expenses."""
    return get_totals(db, params, user_id)


def _tool_get_category_spend(db: Session, params: dict, user_id: int) -> dict:
    """Real: spend for a named category in a month window."""
    return get_category_spend(db, params, user_id)


def _tool_get_merchant_spend(db: Session, params: dict, user_id: int) -> dict:
    """Real: spend for a merchant substring in a month window."""
    return get_merchant_spend(db, params, user_id)


def _tool_get_cash_flow(db: Session, params: dict, user_id: int) -> dict:
    """Real: income / expenses / net for a month window."""
    return get_cash_flow(db, params, user_id)


def _tool_compute_savings_rate(db: Session, params: dict, user_id: int) -> dict:
    """Real: savings rate percentage for a month window."""
    return compute_savings_rate(db, params, user_id)


# Phase 30c — search_history tool. Lets the user ask "what did I ask
# about earlier?" and get back matching messages from past conversations.
def _tool_search_history(db: Session, params: dict, user_id: int) -> dict:
    """Search past conversation messages for a keyword.

    Params:
    - ``query`` (str, required): the search term.
    - ``limit`` (int, optional, default 10).

    Returns a list of ``{conversation_id, role, content, created_at}``
    dicts matching the query (case-insensitive substring).
    """
    query = (params.get("query") or "").strip()
    if not query:
        return {"error": "Missing required param 'query'."}
    limit = params.get("limit", 10)
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 10
    limit = max(1, min(50, limit))

    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    rows = (
        db.query(AssistantMessage, AssistantConversation.id)
        .join(
            AssistantConversation,
            AssistantConversation.id == AssistantMessage.conversation_id,
        )
        .filter(
            AssistantConversation.user_id == user_id,
            AssistantMessage.content.ilike(pattern),
        )
        .order_by(AssistantMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    results = [
        {
            "conversation_id": conv_id,
            "role": msg.role,
            "content": msg.content[:200],
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg, conv_id in rows
    ]
    return {"query": query, "matches": results, "count": len(results)}


# Phase 30d — 5 additional tools for full coverage.


def _tool_get_trends(db: Session, params: dict, user_id: int) -> dict:
    """Monthly expense trend over the last N months."""
    return get_trends(db, params, user_id)


def _tool_compare_periods(db: Session, params: dict, user_id: int) -> dict:
    """Compare two month windows side-by-side."""
    return compare_periods(db, params, user_id)


def _tool_detect_anomalies(db: Session, params: dict, user_id: int) -> dict:
    """Flag transactions > 2× the 90-day median per merchant."""
    return detect_anomalies(db, params, user_id)


def _tool_predict_upcoming_bills(db: Session, params: dict, user_id: int) -> dict:
    """Detect recurring merchants and predict next due date + amount."""
    return predict_upcoming_bills(db, params, user_id)


def _tool_compute_investable_surplus(db: Session, params: dict, user_id: int) -> dict:
    """Compute investable surplus after expenses + goal contributions."""
    return compute_investable_surplus(db, params, user_id)


# Registry — 30a (get_totals) + 30b (4 real queries) + 30c (search_history)
# + 30d (5 analysis tools).
TOOLS: dict[str, Any] = {
    "get_totals": _tool_get_totals,
    "get_category_spend": _tool_get_category_spend,
    "get_merchant_spend": _tool_get_merchant_spend,
    "get_cash_flow": _tool_get_cash_flow,
    "compute_savings_rate": _tool_compute_savings_rate,
    "search_history": _tool_search_history,
    "get_trends": _tool_get_trends,
    "compare_periods": _tool_compare_periods,
    "detect_anomalies": _tool_detect_anomalies,
    "predict_upcoming_bills": _tool_predict_upcoming_bills,
    "compute_investable_surplus": _tool_compute_investable_surplus,
}


_DEFAULT_FOLLOW_UPS = [
    "What's my savings rate?",
    "How much did I spend on dining?",
    "Show me my cash flow this month.",
]

# Phase 30c — max conversations per user. Older conversations are
# hard-deleted by ``_prune_old_conversations`` after each new
# conversation is created.
MAX_CONVERSATIONS_PER_USER = 50


# ---------------------------------------------------------------------
# Conversation persistence helpers (Phase 30c).
# ---------------------------------------------------------------------


def _get_or_create_conversation(
    db: Session,
    user_id: int,
    conversation_id: Optional[int],
    first_message: str,
) -> AssistantConversation:
    """Resolve an existing conversation by id (user-scoped), or create
    a new one. New conversations get a title derived from the first
    user message (truncated to 80 chars)."""
    if conversation_id is not None:
        conv = (
            db.query(AssistantConversation)
            .filter(
                AssistantConversation.id == conversation_id,
                AssistantConversation.user_id == user_id,
            )
            .first()
        )
        if conv is not None:
            return conv
        # Fall through to create if the id doesn't belong to this user.
        LOG.warning(
            "Conversation %d not found for user %d — creating new",
            conversation_id, user_id,
        )

    title = (first_message[:80] + "...") if len(first_message) > 80 else first_message
    conv = AssistantConversation(
        user_id=user_id,
        title=title or "New conversation",
    )
    db.add(conv)
    db.flush()  # get the id without a full commit
    return conv


def _load_conversation_history(
    db: Session,
    conversation_id: int,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Load prior messages for a conversation as LLM-ready dicts.

    Returns ``[{"role": "user"|"assistant", "content": "..."}, ...]``
    ordered by id ascending, capped at ``limit`` most recent turns so
    the prompt doesn't blow up on long conversations.
    """
    rows = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conversation_id)
        .order_by(AssistantMessage.id.desc())
        .limit(limit)
        .all()
    )
    # Reverse to chronological order (oldest first).
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


def _persist_user_message(
    db: Session,
    conversation_id: int,
    content: str,
) -> AssistantMessage:
    """Insert a user message row."""
    msg = AssistantMessage(
        conversation_id=conversation_id,
        role="user",
        content=content,
        status="ok",
    )
    db.add(msg)
    db.flush()
    return msg


def _persist_assistant_message(
    db: Session,
    conversation_id: int,
    reply: str,
    tool_used: Optional[str],
    tool_result: Optional[dict],
    follow_ups: list[str],
    status: str,
) -> AssistantMessage:
    """Insert an assistant message row with tool metadata."""
    msg = AssistantMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=reply,
        tool_used=tool_used,
        tool_result=json.dumps(tool_result) if tool_result is not None else None,
        follow_ups=json.dumps(follow_ups) if follow_ups else None,
        status=status,
    )
    db.add(msg)
    db.flush()
    return msg


def _prune_old_conversations(db: Session, user_id: int) -> int:
    """Hard-delete conversations beyond the last ``MAX_CONVERSATIONS_PER_USER``
    for the user. Returns the count deleted.

    The CASCADE on ``assistant_messages.conversation_id`` ensures
    deleting a conversation removes all its messages in one round-trip.
    """
    # Find the ids of conversations to keep (the most recent N).
    keep_ids = [
        row[0]
        for row in (
            db.query(AssistantConversation.id)
            .filter(AssistantConversation.user_id == user_id)
            .order_by(AssistantConversation.updated_at.desc())
            .limit(MAX_CONVERSATIONS_PER_USER)
            .all()
        )
    ]
    if not keep_ids:
        return 0
    # Delete everything NOT in the keep set.
    deleted = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.user_id == user_id,
            ~AssistantConversation.id.in_(keep_ids),
        )
        .delete(synchronize_session="fetch")
    )
    if deleted > 0:
        db.flush()
        LOG.info("Pruned %d old conversations for user %d", deleted, user_id)
    return deleted


def _bump_updated_at(db: Session, conversation_id: int) -> None:
    """Explicitly update the conversation's ``updated_at`` so the
    sidebar sorts by last-active (``onupdate`` only fires on row
    UPDATE, not on related INSERT — we must touch the row).
    """
    conv_row = (
        db.query(AssistantConversation)
        .filter(AssistantConversation.id == conversation_id)
        .first()
    )
    if conv_row is not None:
        conv_row.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Orchestrator entry point.
# ---------------------------------------------------------------------


async def orchestrate(
    message: str,
    db: Session,
    user_sub: str,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Process a user message and return an assistant response dict.

    The response shape matches ``AssistantResponse``:
    {
        "reply": str,
        "tool_used": str | None,
        "tool_result": dict | None,
        "follow_ups": list[str],
        "status": "ok" | "offline" | "error",
        "conversation_id": int | None,
        "conversation_title": str | None,
    }

    Phase 30c — resolves or creates a conversation, loads prior history
    into the LLM prompt, persists the user + assistant messages, and
    prunes old conversations.

    If Ollama is unreachable, returns ``status="offline"`` with a
    graceful fallback reply (no 500). The user + assistant messages
    are still persisted so the conversation history is intact.
    """
    base_url = base_url or OLLAMA_DEFAULT_BASE_URL
    model = model or DEFAULT_MODEL

    system_prompt = build_system_prompt()

    # --- Phase 30c: resolve / create conversation ---
    conv_title: Optional[str] = None
    history: list[dict[str, str]] = []
    if user_id is not None:
        conv = _get_or_create_conversation(db, user_id, conversation_id, message)
        conversation_id = conv.id
        conv_title = conv.title
        # Load prior history (exclude the current message which hasn't
        # been persisted yet).
        history = _load_conversation_history(db, conv.id)
        # Persist the user's message NOW so it's available even if
        # Ollama is offline.
        _persist_user_message(db, conv.id, message)
    else:
        conversation_id = None

    # --- Build the LLM messages list with history ---
    # The system prompt + history + the current user message.
    llm_messages_for_tool: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": message},
    ]

    # Step 1: Ask the LLM which tool to call.
    try:
        tool_decision = await post_ollama_chat_async(
            llm_messages_for_tool,
            base_url=base_url,
            model=model,
        )
    except httpx.TransportError as exc:
        LOG.warning("Assistant: Ollama unreachable (%s)", type(exc).__name__)
        fallback_reply = (
            "I couldn't reach the local AI helper (Ollama). "
            "Please make sure it's running on localhost:11434 and "
            "try again."
        )
        if user_id is not None and conversation_id is not None:
            _persist_assistant_message(
                db, conversation_id, fallback_reply,
                None, None, [], "offline",
            )
            _bump_updated_at(db, conversation_id)
            db.flush()
            _prune_old_conversations(db, user_id)
            db.commit()
        return {
            "reply": fallback_reply,
            "tool_used": None,
            "tool_result": None,
            "follow_ups": [],
            "status": "offline",
            "conversation_id": conversation_id,
            "conversation_title": conv_title,
        }
    except (ValueError, KeyError, TypeError) as exc:
        LOG.warning("Assistant: LLM response parse error: %s", exc)
        fallback_reply = (
            "I had trouble understanding the AI's response. "
            "Please try rephrasing your question."
        )
        if user_id is not None and conversation_id is not None:
            _persist_assistant_message(
                db, conversation_id, fallback_reply,
                None, None, [], "error",
            )
            _bump_updated_at(db, conversation_id)
            db.flush()
            _prune_old_conversations(db, user_id)
            db.commit()
        return {
            "reply": fallback_reply,
            "tool_used": None,
            "tool_result": None,
            "follow_ups": [],
            "status": "error",
            "conversation_id": conversation_id,
            "conversation_title": conv_title,
        }

    # Step 2: Dispatch to the selected tool.
    tool_name = tool_decision.get("tool", "none")
    params = tool_decision.get("params") or {}

    tool_result: Optional[dict] = None
    tool_used: Optional[str] = None

    if tool_name and tool_name != "none" and tool_name in TOOLS:
        try:
            if user_id is None:
                tool_result = {"error": "User not resolved for this query."}
            else:
                tool_result = TOOLS[tool_name](db, params, user_id)
            tool_used = tool_name
        except Exception as exc:
            LOG.warning("Assistant: tool %s failed: %s", tool_name, exc)
            tool_result = {"error": str(exc)}
            tool_used = tool_name
    elif tool_name and tool_name != "none":
        LOG.warning("Assistant: LLM picked unknown tool %r", tool_name)

    # Step 3: Feed the tool result back to the LLM for a natural-
    # language answer.
    if tool_result is not None:
        nl_messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message},
            {
                "role": "assistant",
                "content": (
                    f'I called tool "{tool_used}" and got this result: '
                    f"{tool_result}. Now explain it to the user in a "
                    "calm, precise, numeric style. Respond with a JSON "
                    'object: {"reply": "<your explanation>"}'
                ),
            },
        ]
    else:
        nl_messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message},
            {
                "role": "assistant",
                "content": (
                    "No tool was called. Respond to the user directly. "
                    'If the question needs a number you don\'t have, say '
                    '"I can\'t answer that yet." Respond with a JSON '
                    'object: {"reply": "<your response>"}'
                ),
            },
        ]

    try:
        nl_response = await post_ollama_chat_async(
            nl_messages,
            base_url=base_url,
            model=model,
        )
        reply = nl_response.get("reply", "")
        if not isinstance(reply, str) or not reply.strip():
            reply = "I couldn't generate a response. Please try again."
    except (httpx.TransportError, ValueError, KeyError, TypeError) as exc:
        LOG.warning("Assistant: NL generation failed: %s", exc)
        if tool_result is not None and "error" not in tool_result:
            reply = (
                f"Here's what I found: {tool_result}. "
                "(The AI helper went offline while generating this "
                "response, so the summary is minimal.)"
            )
        else:
            reply = "I couldn't generate a response. Please try again."

    # --- Phase 30c: persist the assistant message ---
    if user_id is not None and conversation_id is not None:
        _persist_assistant_message(
            db, conversation_id, reply,
            tool_used, tool_result, _DEFAULT_FOLLOW_UPS, "ok",
        )
        # Bump the conversation's updated_at so the sidebar sorts
        # by last-active (onupdate only fires on row UPDATE, not on
        # related INSERT — we must touch the row explicitly).
        _bump_updated_at(db, conversation_id)
        # Flush the updated_at bump BEFORE pruning so the prune's
        # SELECT sees the latest timestamp (the current conversation
        # must be in the "keep" set). Without this flush, the pending
        # UPDATE + the bulk DELETE can produce a StaleDataError on
        # commit (the session tries to UPDATE a row the DELETE already
        # removed from the identity map).
        db.flush()
        # Prune old conversations after the new exchange is persisted.
        _prune_old_conversations(db, user_id)
        db.commit()

    return {
        "reply": reply,
        "tool_used": tool_used,
        "tool_result": tool_result,
        "follow_ups": _DEFAULT_FOLLOW_UPS,
        "status": "ok",
        "conversation_id": conversation_id,
        "conversation_title": conv_title,
    }


# ---------------------------------------------------------------------
# Phase 30e — SSE streaming orchestrator.
# ---------------------------------------------------------------------
#
# ``orchestrate_stream`` is an async generator that yields SSE event
# dicts so the route can serialise them as ``text/event-stream``. The
# event types are:
#
#   {"event": "thinking", "data": {}}
#     — emitted once at the start so the FE can render a "thinking…"
#       indicator.
#
#   {"event": "conversation", "data": {"conversation_id": int,
#       "conversation_title": str}}
#     — emitted once after the conversation is resolved/created so the
#       FE can update the sidebar immediately.
#
#   {"event": "tool_call", "data": {"tool": str, "params": dict}}
#     — emitted when the LLM picks a tool, BEFORE the tool runs. The
#       FE can render a "Looking up your data…" card.
#
#   {"event": "tool_result", "data": {"tool": str, "result": dict}}
#     — emitted after the tool returns. The FE renders the inline
#       ToolCard from this payload.
#
#   {"event": "reply_chunk", "data": {"chunk": str}}
#     — emitted for each chunk of the natural-language reply. The FE
#       appends to the assistant bubble incrementally (typewriter).
#
#   {"event": "done", "data": {"reply": str, "tool_used": str|null,
#       "tool_result": dict|null, "follow_ups": list[str],
#       "status": "ok"|"offline"|"error",
#       "conversation_id": int|null,
#       "conversation_title": str|null}}
#     — emitted once at the end with the full response so the FE can
#       finalize state + persist follow-ups.
#
# If Ollama is unreachable, the stream yields a single ``done`` event
# with ``status="offline"``.


async def orchestrate_stream(
    message: str,
    db: Session,
    user_sub: str,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """SSE streaming variant of :func:`orchestrate`.

    Yields event dicts (see module docstring for the event taxonomy).
    The persistence + prune logic is identical to the blocking path;
    the only difference is that events are yielded as they happen so
    the FE can render incremental progress.
    """
    base_url = base_url or OLLAMA_DEFAULT_BASE_URL
    model = model or DEFAULT_MODEL
    system_prompt = build_system_prompt()

    # --- Phase 30c: resolve / create conversation ---
    conv_title: Optional[str] = None
    history: list[dict[str, str]] = []
    if user_id is not None:
        conv = _get_or_create_conversation(db, user_id, conversation_id, message)
        conversation_id = conv.id
        conv_title = conv.title
        history = _load_conversation_history(db, conv.id)
        _persist_user_message(db, conv.id, message)
    else:
        conversation_id = None

    # Emit the conversation event immediately.
    yield {
        "event": "conversation",
        "data": {
            "conversation_id": conversation_id,
            "conversation_title": conv_title,
        },
    }

    # Emit thinking.
    yield {"event": "thinking", "data": {}}

    llm_messages_for_tool: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": message},
    ]

    # Step 1: Ask the LLM which tool to call.
    try:
        tool_decision = await post_ollama_chat_async(
            llm_messages_for_tool,
            base_url=base_url,
            model=model,
        )
    except httpx.TransportError:
        fallback_reply = (
            "I couldn't reach the local AI helper (Ollama). "
            "Please make sure it's running on localhost:11434 and "
            "try again."
        )
        if user_id is not None and conversation_id is not None:
            _persist_assistant_message(
                db, conversation_id, fallback_reply,
                None, None, [], "offline",
            )
            _bump_updated_at(db, conversation_id)
            db.flush()
            _prune_old_conversations(db, user_id)
            db.commit()
        yield {
            "event": "done",
            "data": {
                "reply": fallback_reply,
                "tool_used": None,
                "tool_result": None,
                "follow_ups": [],
                "status": "offline",
                "conversation_id": conversation_id,
                "conversation_title": conv_title,
            },
        }
        return
    except (ValueError, KeyError, TypeError):
        fallback_reply = (
            "I had trouble understanding the AI's response. "
            "Please try rephrasing your question."
        )
        if user_id is not None and conversation_id is not None:
            _persist_assistant_message(
                db, conversation_id, fallback_reply,
                None, None, [], "error",
            )
            _bump_updated_at(db, conversation_id)
            db.flush()
            _prune_old_conversations(db, user_id)
            db.commit()
        yield {
            "event": "done",
            "data": {
                "reply": fallback_reply,
                "tool_used": None,
                "tool_result": None,
                "follow_ups": [],
                "status": "error",
                "conversation_id": conversation_id,
                "conversation_title": conv_title,
            },
        }
        return

    # Step 2: Dispatch to the selected tool.
    tool_name = tool_decision.get("tool", "none")
    params = tool_decision.get("params") or {}

    # Emit tool_call event.
    yield {
        "event": "tool_call",
        "data": {"tool": tool_name, "params": params},
    }

    tool_result: Optional[dict] = None
    tool_used: Optional[str] = None

    if tool_name and tool_name != "none" and tool_name in TOOLS:
        try:
            if user_id is None:
                tool_result = {"error": "User not resolved for this query."}
            else:
                tool_result = TOOLS[tool_name](db, params, user_id)
            tool_used = tool_name
        except Exception as exc:
            LOG.warning("Assistant: tool %s failed: %s", tool_name, exc)
            tool_result = {"error": str(exc)}
            tool_used = tool_name
    elif tool_name and tool_name != "none":
        LOG.warning("Assistant: LLM picked unknown tool %r", tool_name)

    # Emit tool_result event.
    yield {
        "event": "tool_result",
        "data": {"tool": tool_used or "none", "result": tool_result},
    }

    # Step 3: Feed the tool result back to the LLM for NL answer.
    if tool_result is not None:
        nl_messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message},
            {
                "role": "assistant",
                "content": (
                    f'I called tool "{tool_used}" and got this result: '
                    f"{tool_result}. Now explain it to the user in a "
                    "calm, precise, numeric style. Respond with a JSON "
                    'object: {"reply": "<your explanation>"}'
                ),
            },
        ]
    else:
        nl_messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message},
            {
                "role": "assistant",
                "content": (
                    "No tool was called. Respond to the user directly. "
                    'If the question needs a number you don\'t have, say '
                    '"I can\'t answer that yet." Respond with a JSON '
                    'object: {"reply": "<your response>"}'
                ),
            },
        ]

    try:
        nl_response = await post_ollama_chat_async(
            nl_messages,
            base_url=base_url,
            model=model,
        )
        reply = nl_response.get("reply", "")
        if not isinstance(reply, str) or not reply.strip():
            reply = "I couldn't generate a response. Please try again."
    except (httpx.TransportError, ValueError, KeyError, TypeError):
        if tool_result is not None and "error" not in tool_result:
            reply = (
                f"Here's what I found: {tool_result}. "
                "(The AI helper went offline while generating this "
                "response, so the summary is minimal.)"
            )
        else:
            reply = "I couldn't generate a response. Please try again."

    # Emit reply in chunks (word-by-word for a typewriter effect).
    words = reply.split(" ")
    for i, word in enumerate(words):
        yield {"event": "reply_chunk", "data": {"chunk": word + (" " if i < len(words) - 1 else "")}}

    # Persist the assistant message.
    if user_id is not None and conversation_id is not None:
        _persist_assistant_message(
            db, conversation_id, reply,
            tool_used, tool_result, _DEFAULT_FOLLOW_UPS, "ok",
        )
        _bump_updated_at(db, conversation_id)
        db.flush()
        _prune_old_conversations(db, user_id)
        db.commit()

    # Emit the final done event.
    yield {
        "event": "done",
        "data": {
            "reply": reply,
            "tool_used": tool_used,
            "tool_result": tool_result,
            "follow_ups": _DEFAULT_FOLLOW_UPS,
            "status": "ok",
            "conversation_id": conversation_id,
            "conversation_title": conv_title,
        },
    }
