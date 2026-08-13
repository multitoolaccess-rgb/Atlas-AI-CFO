'use client';

import PageLayout from '@/components/layout/PageLayout';
import ChatPanel from '@/components/assistant/ChatPanel';
import PageHeader from '@/components/ui/PageHeader';

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
      <PageHeader
        title="Scout"
        description="Ask me about your finances. I&apos;ll look up real numbers from your accounts and explain them clearly."
        className="mb-6"
      />
      <ChatPanel />
    </PageLayout>
  );
}
