/**
 * Shared error class thrown when the rules-service backend is unreachable.
 *
 * Kept in a module with no 'use client' directive so it can be imported
 * by both server components (root layout) and client components
 * (error boundary).
 */
export class BackendUnavailableError extends Error {
  constructor() {
    super('BackendUnavailable')
    this.name = 'BackendUnavailableError'
  }
}
