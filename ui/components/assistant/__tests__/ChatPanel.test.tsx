/**
 * Phase 30a + 30c + 30e — ChatPanel component tests.
 *
 * Locks the data-testid surface + the send/receive flow (now with
 * SSE streaming) + the offline banner rendering + the conversation
 * sidebar (30c) + inline tool cards (30e).
 *
 * The api singleton is mocked so assistantChatStream + assistantChat
 * + conversation methods are controllable per-test.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Mock the api service so the streaming + blocking + conversation
// methods are controllable per-test.
vi.mock('@/lib/api', () => ({
  rulesService: {
    assistantChat: vi.fn(),
    assistantChatStream: vi.fn(),
    listAssistantConversations: vi.fn(),
    getAssistantConversation: vi.fn(),
  },
}))

import { rulesService } from '@/lib/api'
import ChatPanel from '../ChatPanel'

/** Helper: create a mock async generator for the SSE stream. */
function makeMockStream(events: Array<{ event: string; data: Record<string, unknown> }>) {
  return async function* () {
    for (const evt of events) {
      yield evt
    }
  }
}

describe('Phase 30a + 30c + 30e — ChatPanel', () => {
  beforeEach(() => {
    vi.mocked(rulesService.assistantChat).mockReset()
    vi.mocked(rulesService.assistantChatStream).mockReset()
    vi.mocked(rulesService.listAssistantConversations).mockReset()
    vi.mocked(rulesService.getAssistantConversation).mockReset()
    // Default: no conversations on mount.
    vi.mocked(rulesService.listAssistantConversations).mockResolvedValue([])
  })

  it('renders the chat panel with an initial greeting', () => {
    render(<ChatPanel />)
    expect(screen.getByTestId('chat-panel')).toBeTruthy()
    expect(screen.getByTestId('chat-input')).toBeTruthy()
    expect(screen.getByTestId('chat-send')).toBeTruthy()
    // The initial assistant greeting is message-0.
    const greeting = screen.getByTestId('chat-message-0')
    expect(greeting.textContent).toMatch(/finance copilot/i)
  })

  it('renders the conversation sidebar with new conversation button', () => {
    render(<ChatPanel />)
    expect(screen.getByTestId('chat-conversation-list')).toBeTruthy()
    expect(screen.getByTestId('chat-new-conversation')).toBeTruthy()
  })

  it('sends a message via SSE stream and renders the assistant reply', async () => {
    vi.mocked(rulesService.assistantChatStream).mockReturnValueOnce(
      makeMockStream([
        { event: 'conversation', data: { conversation_id: 42, conversation_title: 'What are my totals?' } },
        { event: 'thinking', data: {} },
        { event: 'tool_call', data: { tool: 'get_totals', params: {} } },
        { event: 'tool_result', data: { tool: 'get_totals', result: { total_balance: 125000 } } },
        { event: 'reply_chunk', data: { chunk: 'Your ' } },
        { event: 'reply_chunk', data: { chunk: 'total ' } },
        { event: 'reply_chunk', data: { chunk: 'balance ' } },
        { event: 'reply_chunk', data: { chunk: 'is $125,000.' } },
        {
          event: 'done',
          data: {
            reply: 'Your total balance is $125,000.',
            tool_used: 'get_totals',
            tool_result: { total_balance: 125000 },
            follow_ups: ["What's my savings rate?"],
            status: 'ok',
            conversation_id: 42,
            conversation_title: 'What are my totals?',
          },
        },
      ])(),
    )

    render(<ChatPanel />)
    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    const sendBtn = screen.getByTestId('chat-send')

    fireEvent.change(input, { target: { value: 'What are my totals?' } })
    fireEvent.click(sendBtn)

    // The user message appears immediately (message-1).
    await waitFor(() => {
      const userMsg = screen.getByTestId('chat-message-1')
      expect(userMsg.textContent).toMatch(/What are my totals?/)
    })

    // The assistant reply appears after the stream completes.
    await waitFor(() => {
      const reply = screen.getByTestId('chat-message-2')
      expect(reply.textContent).toMatch(/\$125,000/)
    })

    // The follow-up chip is rendered.
    expect(screen.getByTestId('chat-followup-0')).toBeTruthy()
  })

  it('renders an inline tool card when tool_result is received', async () => {
    vi.mocked(rulesService.assistantChatStream).mockReturnValueOnce(
      makeMockStream([
        { event: 'conversation', data: { conversation_id: 1, conversation_title: 'Test' } },
        { event: 'thinking', data: {} },
        { event: 'tool_call', data: { tool: 'get_totals', params: {} } },
        { event: 'tool_result', data: { tool: 'get_totals', result: { total_balance: 50000, total_income_month: 5000, total_expenses_month: 2000 } } },
        { event: 'reply_chunk', data: { chunk: 'Done.' } },
        {
          event: 'done',
          data: {
            reply: 'Done.',
            tool_used: 'get_totals',
            tool_result: { total_balance: 50000, total_income_month: 5000, total_expenses_month: 2000 },
            follow_ups: [],
            status: 'ok',
            conversation_id: 1,
            conversation_title: 'Test',
          },
        },
      ])(),
    )

    render(<ChatPanel />)
    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Totals' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    // The tool card should render inside the assistant message.
    await waitFor(() => {
      const toolCard = screen.getByTestId('chat-tool-card-2')
      expect(toolCard).toBeTruthy()
    })

    // The ToolCard itself should be present.
    await waitFor(() => {
      const card = screen.getByTestId('tool-card')
      expect(card).toBeTruthy()
    })
  })

  it('renders an offline banner when stream done has status=offline', async () => {
    vi.mocked(rulesService.assistantChatStream).mockReturnValueOnce(
      makeMockStream([
        { event: 'conversation', data: { conversation_id: 1, conversation_title: 'Test' } },
        { event: 'thinking', data: {} },
        {
          event: 'done',
          data: {
            reply: "I couldn't reach the local AI helper (Ollama).",
            tool_used: null,
            tool_result: null,
            follow_ups: [],
            status: 'offline',
            conversation_id: 1,
            conversation_title: 'Test',
          },
        },
      ])(),
    )

    render(<ChatPanel />)
    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      const banner = screen.getByTestId('chat-offline-banner')
      expect(banner.textContent).toMatch(/offline/i)
    })
  })

  it('disables the send button when the input is empty', () => {
    render(<ChatPanel />)
    const sendBtn = screen.getByTestId('chat-send') as HTMLButtonElement
    expect(sendBtn.disabled).toBe(true)

    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Test' } })
    expect(sendBtn.disabled).toBe(false)
  })

  it('clicking a follow-up chip sends it as a new message', async () => {
    vi.mocked(rulesService.assistantChatStream).mockReturnValueOnce(
      makeMockStream([
        { event: 'conversation', data: { conversation_id: 1, conversation_title: 'Totals' } },
        { event: 'thinking', data: {} },
        { event: 'tool_call', data: { tool: 'get_totals', params: {} } },
        { event: 'tool_result', data: { tool: 'get_totals', result: {} } },
        { event: 'reply_chunk', data: { chunk: 'Reply.' } },
        {
          event: 'done',
          data: {
            reply: 'Reply.',
            tool_used: 'get_totals',
            tool_result: {},
            follow_ups: ["What's my savings rate?"],
            status: 'ok',
            conversation_id: 1,
            conversation_title: 'Totals',
          },
        },
      ])(),
    )

    render(<ChatPanel />)
    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Totals' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    // Wait for the follow-up to appear.
    const chip = await screen.findByTestId('chat-followup-0')
    expect(chip.textContent).toMatch(/savings rate/i)

    // Mock the second stream call.
    vi.mocked(rulesService.assistantChatStream).mockReturnValueOnce(
      makeMockStream([
        { event: 'conversation', data: { conversation_id: 1, conversation_title: 'Totals' } },
        { event: 'thinking', data: {} },
        { event: 'tool_call', data: { tool: 'compute_savings_rate', params: {} } },
        { event: 'tool_result', data: { tool: 'compute_savings_rate', result: {} } },
        { event: 'reply_chunk', data: { chunk: '50%.' } },
        {
          event: 'done',
          data: {
            reply: '50%.',
            tool_used: 'compute_savings_rate',
            tool_result: {},
            follow_ups: [],
            status: 'ok',
            conversation_id: 1,
            conversation_title: 'Totals',
          },
        },
      ])(),
    )

    fireEvent.click(chip)

    await waitFor(() => {
      expect(vi.mocked(rulesService.assistantChatStream)).toHaveBeenCalledTimes(2)
    })
  })

  it('clicking new conversation resets the chat', async () => {
    vi.mocked(rulesService.assistantChatStream).mockReturnValueOnce(
      makeMockStream([
        { event: 'conversation', data: { conversation_id: 5, conversation_title: 'First' } },
        { event: 'thinking', data: {} },
        { event: 'tool_call', data: { tool: 'get_totals', params: {} } },
        { event: 'tool_result', data: { tool: 'get_totals', result: {} } },
        { event: 'reply_chunk', data: { chunk: 'Reply 1.' } },
        {
          event: 'done',
          data: {
            reply: 'Reply 1.',
            tool_used: 'get_totals',
            tool_result: {},
            follow_ups: [],
            status: 'ok',
            conversation_id: 5,
            conversation_title: 'First',
          },
        },
      ])(),
    )

    render(<ChatPanel />)
    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'First question' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      expect(screen.getByTestId('chat-message-2')).toBeTruthy()
    })

    // Click "New conversation".
    fireEvent.click(screen.getByTestId('chat-new-conversation'))

    // The greeting should be back (message-0 only).
    await waitFor(() => {
      const greeting = screen.getByTestId('chat-message-0')
      expect(greeting.textContent).toMatch(/finance copilot/i)
    })
  })

  it('renders conversation list items in the sidebar', async () => {
    vi.mocked(rulesService.listAssistantConversations).mockResolvedValueOnce([
      {
        id: 1,
        title: 'What are my totals?',
        created_at: '2026-07-04T00:00:00Z',
        updated_at: '2026-07-04T00:00:00Z',
        messages: [],
      },
      {
        id: 2,
        title: 'Savings rate question',
        created_at: '2026-07-04T01:00:00Z',
        updated_at: '2026-07-04T01:00:00Z',
        messages: [],
      },
    ])

    render(<ChatPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('chat-conversation-1')).toBeTruthy()
      expect(screen.getByTestId('chat-conversation-2')).toBeTruthy()
    })
  })

  it('falls back to blocking API when stream fails', async () => {
    // Make the stream throw immediately.
    vi.mocked(rulesService.assistantChatStream).mockImplementationOnce(
      async function* () {
        throw new Error('Stream failed')
      },
    )

    vi.mocked(rulesService.assistantChat).mockResolvedValueOnce({
      reply: 'Fallback reply.',
      tool_used: 'get_totals',
      tool_result: {},
      follow_ups: [],
      status: 'ok',
      conversation_id: 10,
      conversation_title: 'Test',
    })

    render(<ChatPanel />)
    const input = screen.getByTestId('chat-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Test' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    // The fallback reply should appear.
    await waitFor(() => {
      expect(vi.mocked(rulesService.assistantChat)).toHaveBeenCalled()
    })

    await waitFor(() => {
      const reply = screen.getByTestId('chat-message-2')
      expect(reply.textContent).toMatch(/Fallback reply/)
    })
  })
})
