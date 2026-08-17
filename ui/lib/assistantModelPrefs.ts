// =============================================================================
// Phase 30f — per-browser preference for the Scout Ollama model. Persisted in
// localStorage (NOT in the BE users row) because the choice of which local
// model drives the assistant is a single-browser UX concern, not a
// multi-device finance data fact. The BE has no equivalent setting because
// ``POST /api/assistant/chat`` is stateless — the model is passed per request.
//
// Bound rationale:
//   - ``null`` means "use the service default" (the FE falls back to the
//     ``default`` field returned by ``GET /api/assistant/models``). This is
//     the sentinel so a fresh user never sends a stale model name.
//   - Any non-empty string is a user-picked model name from the picker.
//     The value is stored verbatim (Ollama model names are opaque strings).
// =============================================================================

/** localStorage key. Scoped to the fc_ namespace used elsewhere. */
const KEY = 'fc_assistant_model'

/**
 * Read the currently-selected Scout model. Returns ``null`` when the
 * user hasn't picked one (use the service default).
 *
 * SSR-safe: returns ``null`` when ``window`` is undefined so Next.js
 * server-rendering never reads localStorage.
 */
export function getAssistantModel(): string | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(KEY)
  if (!raw) return null
  const trimmed = raw.trim()
  return trimmed || null
}

/**
 * Persist a new model selection. ``null`` clears the preference (falls
 * back to the service default). Always stores the trimmed value so the
 * read path never sees a whitespace-only string.
 */
export function setAssistantModel(model: string | null): void {
  if (typeof window === 'undefined') return
  const trimmed = model?.trim() ?? ''
  if (trimmed) {
    window.localStorage.setItem(KEY, trimmed)
  } else {
    window.localStorage.removeItem(KEY)
  }
}
