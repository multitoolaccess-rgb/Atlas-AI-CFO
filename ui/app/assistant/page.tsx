'use client';

import PageLayout from '@/components/layout/PageLayout';
import ChatPanel from '@/components/assistant/ChatPanel';

/**
 * Phase 30a — Scout (AI assistant) page.
 *
 * Hosts the ``<ChatPanel />`` component inside the standard
 * ``PageLayout`` shell. The sidebar's "Scout" nav link points
 * here (``/assistant``).
 *
 * Blocking v1 — the chat request blocks until the orchestrator
 * finishes. SSE streaming + inline tool cards are Phase 30e.
 */
export default function AssistantPage() {
  return (
    <PageLayout>
      <div className="mb-4">
        <h1 className="headline-xl text-primary mb-1">Scout</h1>
        <p className="body-md text-secondary">
          Ask me about your finances. I&apos;ll look up real numbers
          from your accounts and explain them clearly.
        </p>
      </div>
      <ChatPanel />
    </PageLayout>
  );
}
