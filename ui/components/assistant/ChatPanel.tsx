'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Loader2, Bot, User, Plus, MessageSquare, ChevronLeft, Wrench, Cpu } from 'lucide-react';
import { rulesService, type AssistantConversation } from '@/lib/api';
import Select from '@/components/ui/Select';
import { getAssistantModel, setAssistantModel } from '@/lib/assistantModelPrefs';
import ToolCard from './ToolCard';

/**
 * Phase 30a + 30c + 30e — ChatPanel component.
 *
 * Renders a chat interface: a scrollable message list (user + assistant
 * bubbles), a text input + send button, follow-up suggestion chips,
 * a conversation sidebar (Phase 30c), AND SSE streaming with inline
 * tool cards (Phase 30e).
 *
 * The component uses ``rulesService.assistantChatStream`` (an async
 * generator) to consume SSE events from ``POST /api/assistant/chat/stream``.
 * Events are rendered incrementally:
 *   - ``conversation`` → update sidebar state
 *   - ``thinking`` → show a "thinking…" indicator
 *   - ``tool_call`` → show a "looking up…" card placeholder
 *   - ``tool_result`` → render the inline ToolCard
 *   - ``reply_chunk`` → append to the assistant bubble (typewriter)
 *   - ``done`` → finalize state + follow-ups
 *
 * If the stream fails, falls back to the blocking ``assistantChat``
 * method so the user still gets a response.
 *
 * data-testid surface (locked for e2e):
 * - ``chat-panel`` — root container
 * - ``chat-input`` — textarea
 * - ``chat-send`` — send button
 * - ``chat-message-{n}`` — each message bubble (0-indexed)
 * - ``chat-followup-{n}`` — each follow-up chip
 * - ``chat-offline-banner`` — offline warning (only when status=offline)
 * - ``chat-loading`` — in-flight spinner (only while loading)
 * - ``chat-new-conversation`` — new conversation button
 * - ``chat-conversation-list`` — sidebar conversation list container
 * - ``chat-conversation-{id}`` — each conversation item in the sidebar
 * - ``chat-sidebar-toggle`` — toggle sidebar visibility (mobile)
 * - ``chat-thinking`` — thinking indicator (30e)
 * - ``chat-tool-card-{n}`` — inline tool card on an assistant message
 * - ``chat-stream-status`` — streaming status indicator (30e)
 */

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  /** Set on assistant messages when the BE returned status='offline'. */
  offline?: boolean;
  /** Tool metadata for inline card rendering (30e). */
  toolUsed?: string | null;
  toolResult?: Record<string, unknown> | null;
  /** Streaming state — true while the reply is being chunked in. */
  streaming?: boolean;
}

interface ChatPanelProps {
  /**
   * Optional pre-filled query to auto-submit on mount or when changed.
   * Used by the CopilotDock quick-query chips: the dock sets this when
   * the user taps a chip, ChatPanel fires the send, then the dock
   * clears the value via the React key prop on ChatPanel's parent.
   */
  pendingQuery?: string | null
}

export default function ChatPanel({ pendingQuery }: ChatPanelProps = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        "Hi! I'm Scout, your finance copilot. Ask me about your totals, " +
        "spending, or savings — I'll look it up and explain it clearly.",
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Phase 30c — conversation state.
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [conversations, setConversations] = useState<AssistantConversation[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [loadingConversations, setLoadingConversations] = useState(false);

  // Phase 30e — streaming state.
  const [streamStatus, setStreamStatus] = useState<string | null>(null);

  // Phase 30f — Scout model picker. Lets the user choose which local
  // Ollama model drives the assistant instead of silently defaulting.
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelWarming, setModelWarming] = useState(false);
  const [modelStatus, setModelStatus] = useState<'warmed' | 'offline' | null>(null);

  // Load the installed model list on mount + restore the user's pick.
  // Also auto-warm the initial model once (fire-and-forget in the
  // background) so the first message after opening Scout doesn't stall
  // on a cold load — the model is already resident by the time the user
  // types. Guarded by a ref so it only warms the initial default, not
  // on every picker change (those go through handleModelChange).
  const autoWarmedRef = useRef<string | null>(null);
  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const data = await rulesService.listAssistantModels();
      setModels(data.models ?? []);
      // Restore the saved pick if it's still installed; otherwise fall
      // back to the service default (null = use default).
      const saved = getAssistantModel();
      const initial =
        saved && (data.models ?? []).includes(saved)
          ? saved
          : (data.default ?? null);
      setSelectedModel(initial);
      if (initial && autoWarmedRef.current !== initial) {
        autoWarmedRef.current = initial;
        void rulesService.warmAssistantModel(initial).catch(() => {
          // Silent: an offline Ollama means the default just stays
          // cold; the stream's model_loading event still covers that.
        });
      }
    } catch {
      // Model discovery is a convenience — a failure just leaves the
      // picker empty and Scout keeps using the service default.
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  // When the user picks a model, persist it and warm it so the first
  // chat after a switch doesn't stall on a cold load.
  const handleModelChange = async (next: string) => {
    setSelectedModel(next);
    setAssistantModel(next);
    setModelStatus(null);
    setModelWarming(true);
    try {
      const result = await rulesService.warmAssistantModel(next);
      setModelStatus(result.status);
    } catch {
      setModelStatus('offline');
    } finally {
      setModelWarming(false);
    }
  };

  // Load conversation list on mount.
  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const list = await rulesService.listAssistantConversations();
      setConversations(list);
    } catch {
      // Silently fail — the sidebar is a convenience, not a blocker.
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Phase 4 — auto-submit a pre-filled query from CopilotDock.
  // Guarded by a ref so each remount (driven by the dock's `key`
  // prop on ChatPanel) gets exactly one auto-send even if useEffect
  // re-fires for other reasons.
  const autoSubmittedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!pendingQuery || autoSubmittedRef.current === pendingQuery) return
    autoSubmittedRef.current = pendingQuery
    void handleSend(pendingQuery)
    // handleSend is stable thanks to its useCallback; pendingQuery
    // is the only trigger we want.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuery])

  // Auto-scroll to the latest message when the list grows.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading, streamStatus]);

  const handleNewConversation = () => {
    setConversationId(null);
    setConversationTitle(null);
    setMessages([
      {
        role: 'assistant',
        content:
          "Hi! I'm Scout, your finance copilot. Ask me about your totals, " +
          "spending, or savings — I'll look it up and explain it clearly.",
      },
    ]);
    setFollowUps([]);
    setOffline(false);
    setStreamStatus(null);
  };

  const handleSelectConversation = async (convId: number) => {
    try {
      const conv = await rulesService.getAssistantConversation(convId);
      setConversationId(conv.id);
      setConversationTitle(conv.title);
      // Rebuild the message list from the persisted messages.
      const restored: ChatMessage[] = (conv.messages ?? []).map((m) => ({
        role: m.role,
        content: m.content,
        offline: m.status === 'offline',
        toolUsed: m.tool_used,
        toolResult: m.tool_result,
      }));
      // If the conversation has messages, use them; otherwise show the greeting.
      if (restored.length > 0) {
        setMessages(restored);
      } else {
        setMessages([
          {
            role: 'assistant',
            content: "Hi! I'm Scout, your finance copilot. Ask me anything.",
          },
        ]);
      }
      // Set the last follow-ups if the last assistant message had them.
      const lastAssistant = [...(conv.messages ?? [])].reverse().find((m) => m.role === 'assistant');
      setFollowUps(lastAssistant?.follow_ups ?? []);
      setOffline(false);
      setStreamStatus(null);
    } catch {
      // If the conversation fails to load, stay on the current one.
    }
  };

  const handleSend = async (messageText?: string) => {
    const text = (messageText ?? input).trim();
    if (!text || loading) return;

    // Append the user's message immediately (optimistic).
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);
    setOffline(false);
    setStreamStatus('thinking');

    // Add a placeholder assistant message that we'll update as chunks arrive.
    const assistantIndex = messages.length + 1; // +1 for the user msg just added
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', streaming: true },
    ]);

    try {
      // Phase 30e — use SSE streaming.
      let accumulatedReply = '';
      let toolUsed: string | null = null;
      let toolResult: Record<string, unknown> | null = null;
      let resultConversationId: number | null = conversationId;
      let resultConversationTitle: string | null = conversationTitle;
      let resultStatus: 'ok' | 'offline' | 'error' = 'ok';
      let resultFollowUps: string[] = [];

      try {
        for await (const evt of rulesService.assistantChatStream(text, conversationId, selectedModel)) {
          switch (evt.event) {
            case 'model_loading': {
              // Cold start: Ollama is loading the chosen model into
              // memory. Surface a distinct status so the user sees
              // "Loading model…" instead of an apparently-stuck
              // "thinking" spinner (the BE uses a longer timeout for
              // this first round so it won't 504 mid-load).
              setStreamStatus('model_loading');
              break;
            }
            case 'conversation': {
              const cid = evt.data.conversation_id as number | null;
              const ctitle = evt.data.conversation_title as string | null;
              if (cid !== null) {
                resultConversationId = cid;
                resultConversationTitle = ctitle;
                const isNew = conversationId === null;
                setConversationId(cid);
                if (ctitle) setConversationTitle(ctitle);
                if (isNew) loadConversations();
              }
              break;
            }
            case 'thinking':
              setStreamStatus('thinking');
              break;
            case 'tool_call': {
              setStreamStatus('tool');
              toolUsed = (evt.data.tool as string) || null;
              // Update the assistant message to show the tool is running.
              setMessages((prev) => {
                const copy = [...prev];
                if (copy[assistantIndex]) {
                  copy[assistantIndex] = {
                    ...copy[assistantIndex],
                    toolUsed,
                    content: `Looking up ${toolUsed}...`,
                  };
                }
                return copy;
              });
              break;
            }
            case 'tool_result': {
              setStreamStatus('tool_result');
              toolUsed = (evt.data.tool as string) || toolUsed;
              toolResult = (evt.data.result as Record<string, unknown>) || null;
              // Update the assistant message with the tool result.
              setMessages((prev) => {
                const copy = [...prev];
                if (copy[assistantIndex]) {
                  copy[assistantIndex] = {
                    ...copy[assistantIndex],
                    toolUsed,
                    toolResult,
                    content: '', // clear the "looking up" text
                  };
                }
                return copy;
              });
              break;
            }
            case 'reply_chunk': {
              setStreamStatus('replying');
              const chunk = (evt.data.chunk as string) || '';
              accumulatedReply += chunk;
              // Update the assistant message incrementally.
              setMessages((prev) => {
                const copy = [...prev];
                if (copy[assistantIndex]) {
                  copy[assistantIndex] = {
                    ...copy[assistantIndex],
                    content: accumulatedReply,
                    streaming: true,
                  };
                }
                return copy;
              });
              break;
            }
            case 'done': {
              const doneData = evt.data;
              accumulatedReply = (doneData.reply as string) || accumulatedReply;
              toolUsed = (doneData.tool_used as string | null) ?? toolUsed;
              toolResult = (doneData.tool_result as Record<string, unknown> | null) ?? toolResult;
              resultFollowUps = (doneData.follow_ups as string[]) || [];
              resultStatus = (doneData.status as 'ok' | 'offline' | 'error') || 'ok';
              const doneCid = doneData.conversation_id as number | null;
              const doneCtitle = doneData.conversation_title as string | null;
              if (doneCid !== null && doneCid !== undefined) {
                resultConversationId = doneCid;
                resultConversationTitle = doneCtitle;
              }
              break;
            }
          }
        }

        // Finalize the assistant message.
        setMessages((prev) => {
          const copy = [...prev];
          if (copy[assistantIndex]) {
            copy[assistantIndex] = {
              ...copy[assistantIndex],
              content: accumulatedReply,
              toolUsed,
              toolResult,
              streaming: false,
              offline: resultStatus === 'offline',
            };
          }
          return copy;
        });
        setOffline(resultStatus === 'offline');
        setFollowUps(resultFollowUps);

        // Update conversation state if a new conversation was created.
        if (resultConversationId !== null && resultConversationId !== conversationId) {
          setConversationId(resultConversationId);
          if (resultConversationTitle) setConversationTitle(resultConversationTitle);
          void loadConversations();
        }
      } catch {
        // Stream failed — fall back to the blocking API.
        // Use resultConversationId (which may have been updated by the
        // stream's conversation event before the failure) instead of the
        // stale closure conversationId, so we append to the same
        // conversation the stream created rather than creating a duplicate.
        setStreamStatus('fallback');
        // Remove the placeholder assistant message.
        setMessages((prev) => prev.slice(0, assistantIndex));

        const result = await rulesService.assistantChat(text, resultConversationId, selectedModel);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: result.reply,
            offline: result.status === 'offline',
            toolUsed: result.tool_used,
            toolResult: result.tool_result,
          },
        ]);
        setOffline(result.status === 'offline');
        setFollowUps(result.follow_ups || []);

        if (result.conversation_id !== null) {
          const isNew = conversationId === null;
          setConversationId(result.conversation_id);
          if (result.conversation_title) {
            setConversationTitle(result.conversation_title);
          }
          if (isNew) loadConversations();
        }
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Something went wrong.';
      // Remove the placeholder and show the error.
      setMessages((prev) => {
        const copy = prev.slice(0, assistantIndex);
        return [
          ...copy,
          {
            role: 'assistant',
            content: `I couldn't process that request: ${msg}`,
          },
        ];
      });
    } finally {
      setLoading(false);
      setStreamStatus(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className="flex h-full max-h-[calc(100vh-8rem)] gap-0 card p-0 overflow-hidden"
      data-testid="chat-panel"
    >
      {/* Conversation sidebar (Phase 30c) */}
      {sidebarOpen && (
        <div
          className="w-64 flex-shrink-0 border-r border-outline-variant/30 flex flex-col bg-surface-container-low"
          data-testid="chat-conversation-list"
        >
          <div className="p-3 border-b border-outline-variant/20">
            <button
              type="button"
              onClick={handleNewConversation}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg
                         bg-primary text-on-primary text-sm font-medium
                         hover:opacity-90 active:scale-[0.98]
                         transition-all duration-150"
              data-testid="chat-new-conversation"
            >
              <Plus className="w-4 h-4" aria-hidden="true" />
              New conversation
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loadingConversations && (
              <p className="text-xs text-tertiary px-2 py-1">Loading…</p>
            )}
            {!loadingConversations && conversations.length === 0 && (
              <p className="text-xs text-tertiary px-2 py-1">
                No conversations yet. Start by asking a question.
              </p>
            )}
            {conversations.map((conv) => (
              <button
                key={conv.id}
                type="button"
                onClick={() => handleSelectConversation(conv.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm
                            transition-colors duration-150
                            flex items-center gap-2
                            ${
                              conversationId === conv.id
                                ? 'bg-surface-container-high text-primary font-medium'
                                : 'text-secondary hover:bg-surface-container'
                            }`}
                data-testid={`chat-conversation-${conv.id}`}
              >
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" aria-hidden="true" />
                <span className="truncate">{conv.title}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header with title + sidebar toggle */}
        <div className="flex items-center gap-2 p-3 border-b border-outline-variant/30">
          <button
            type="button"
            onClick={() => setSidebarOpen((v) => !v)}
            className="flex-shrink-0 p-1.5 rounded-lg text-tertiary hover:text-primary hover:bg-surface-container
                       transition-colors duration-150"
            data-testid="chat-sidebar-toggle"
            aria-label="Toggle conversation sidebar"
          >
            <ChevronLeft
              className={`w-4 h-4 transition-transform duration-200 ${sidebarOpen ? '' : 'rotate-180'}`}
              aria-hidden="true"
            />
          </button>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-primary truncate">
              {conversationTitle || 'New conversation'}
            </h2>
          </div>
          {/* Phase 30f — Scout model picker. Lets the user choose which
              local Ollama model drives the assistant instead of silently
              defaulting. Disabled while models are loading or when Ollama
              is offline (empty list). */}
          <div className="flex-shrink-0 flex items-center gap-1.5" data-testid="chat-model-picker">
            {modelWarming ? (
              <span
                className="flex items-center gap-1.5 text-xs text-tertiary px-2 py-1 rounded-full bg-surface-container"
                data-testid="chat-model-warming"
              >
                <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
                <span>Loading model…</span>
              </span>
            ) : modelStatus === 'offline' ? (
              <span
                className="flex items-center gap-1.5 text-xs text-[var(--warning-700)] px-2 py-1 rounded-full bg-[var(--warning-50)] border border-[var(--warning-200)]"
                data-testid="chat-model-offline"
                title="Ollama is offline — Scout will use the default model when it's back up."
              >
                <Cpu className="w-3 h-3" aria-hidden="true" />
                <span>Ollama offline</span>
              </span>
            ) : (
              <div className="flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-tertiary" aria-hidden="true" />
                <Select
                  aria-label="Scout model"
                  size="sm"
                  value={selectedModel ?? ''}
                  disabled={modelsLoading || models.length === 0}
                  onChange={(e) => void handleModelChange(e.target.value)}
                  options={
                    models.length > 0
                      ? models.map((m) => ({ value: m, label: m }))
                      : [{ value: '', label: modelsLoading ? 'Loading…' : 'No models found' }]
                  }
                  data-testid="chat-model-select"
                  containerClassName="w-auto"
                  className="max-w-[220px]"
                />
              </div>
            )}
          </div>
          {/* Phase 30e — streaming status indicator */}
          {streamStatus && (
            <div
              className="flex items-center gap-1.5 text-xs text-tertiary px-2 py-1 rounded-full bg-surface-container"
              data-testid="chat-stream-status"
            >
              <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
              <span className="capitalize">
                {streamStatus === 'model_loading' ? 'Loading model…' : streamStatus}
              </span>
            </div>
          )}
        </div>

        {/* Message list */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-4 space-y-4"
        >
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-3 ${
                msg.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
              data-testid={`chat-message-${i}`}
            >
              {msg.role === 'assistant' && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center">
                  <Bot className="w-4 h-4 text-primary" aria-hidden="true" />
                </div>
              )}
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-primary text-on-primary rounded-br-sm'
                    : msg.offline
                      ? 'bg-[var(--warning-50)] text-[var(--warning-700)] border border-[var(--warning-200)] rounded-bl-sm'
                      : 'bg-surface-container text-on-surface rounded-bl-sm'
                }`}
              >
                {/* Phase 30e — inline tool card */}
                {msg.role === 'assistant' && msg.toolResult && msg.toolUsed && (
                  <div className="mb-2" data-testid={`chat-tool-card-${i}`}>
                    <ToolCard tool={msg.toolUsed} result={msg.toolResult} />
                  </div>
                )}
                {/* Phase 30e — content area: thinking, tool running, or text */}
                {msg.role === 'assistant' && msg.streaming && !msg.content && !msg.toolResult ? (
                  <div className="flex items-center gap-2 text-tertiary" data-testid={`chat-thinking-${i}`}>
                    <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
                    <span className="text-xs">Thinking…</span>
                  </div>
                ) : msg.role === 'assistant' && msg.streaming && msg.toolUsed && !msg.toolResult && msg.content && msg.content.startsWith('Looking up') ? (
                  <div className="flex items-center gap-2 text-tertiary" data-testid={`chat-tool-running-${i}`}>
                    <Wrench className="w-3 h-3 animate-pulse" aria-hidden="true" />
                    <span className="text-xs">{msg.content}</span>
                  </div>
                ) : (
                  <>
                    <span>{msg.content}</span>
                    {msg.role === 'assistant' && msg.streaming && msg.content && !msg.content.startsWith('Looking up') && (
                      <span className="inline-block w-1.5 h-4 ml-0.5 bg-primary/60 animate-pulse align-text-bottom rounded-sm" />
                    )}
                  </>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                  <User className="w-4 h-4 text-on-primary" aria-hidden="true" />
                </div>
              )}
            </div>
          ))}

          {loading && !streamStatus && (
            <div
              className="flex gap-3 justify-start"
              data-testid="chat-loading"
            >
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center">
                <Bot className="w-4 h-4 text-primary" aria-hidden="true" />
              </div>
              <div className="bg-surface-container rounded-2xl rounded-bl-sm px-4 py-3">
                <Loader2
                  className="w-4 h-4 text-secondary animate-spin"
                  aria-hidden="true"
                />
              </div>
            </div>
          )}

          {offline && (
            <div
              className="flex items-center gap-2 p-3 rounded-lg bg-[var(--warning-50)] border border-[var(--warning-200)] text-[var(--warning-700)] text-sm"
              data-testid="chat-offline-banner"
              role="alert"
            >
              <span>
                ⚠ The local AI helper (Ollama) is offline. Start it on
                <code className="mx-1 px-1 py-0.5 bg-[var(--warning-100)] rounded text-xs">
                  localhost:11434
                </code>
                and try again.
              </span>
            </div>
          )}
        </div>

        {/* Follow-up suggestions */}
        {followUps.length > 0 && !loading && (
          <div className="px-4 pb-2 flex flex-wrap gap-2">
            {followUps.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={() => handleSend(s)}
                className="px-3 py-1.5 rounded-full text-xs font-medium
                           bg-surface-container text-secondary
                           hover:bg-surface-container-high
                           border border-outline-variant/30
                           transition-colors duration-150"
                data-testid={`chat-followup-${i}`}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input area */}
        <div className="border-t border-outline-variant/30 p-4 flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your finances..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-outline-variant/40
                       bg-surface px-4 py-2.5 text-sm text-primary
                       placeholder:text-tertiary
                       focus:outline-none focus:ring-2 focus:ring-primary/30
                       max-h-32 overflow-y-auto"
            data-testid="chat-input"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
            className="flex-shrink-0 w-10 h-10 rounded-xl
                       bg-primary text-on-primary
                       hover:opacity-90 active:scale-95
                       disabled:opacity-40 disabled:cursor-not-allowed
                       flex items-center justify-center
                       transition-all duration-150"
            data-testid="chat-send"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
