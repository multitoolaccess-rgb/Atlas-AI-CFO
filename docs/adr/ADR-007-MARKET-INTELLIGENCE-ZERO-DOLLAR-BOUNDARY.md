# ADR-007: Zero-Dollar Deterministic Market Intelligence Boundary

- **Status:** Accepted
- **Date:** 2026-08-11
- **Scope:** Phase 5 Market Intelligence Brief
- **Related:** ADR-005, ADR-006, Phase 5 plan

## Context

Atlas needs portfolio-specific market context without creating a paid-data,
autonomous-trading, or cloud-LLM dependency. External news and filing text are
untrusted, and email is a lower-privacy channel than authenticated Atlas
access. The personal-use release must remain reproducible and safe when a
provider is unavailable, stale, malformed, rate-limited, or disabled.

## Decision

Phase 5 uses only a zero-dollar external-data boundary: Finnhub Free for
quotes, company news, and earnings data, and public SEC data APIs for filings
and XBRL facts. Provider adapters normalize bounded records, timestamps,
freshness, source metadata, failures, caching, pacing, and usage accounting.
They reject paid endpoints and are disabled by server-owned default-off flags.

Rules Service deterministically calculates Decimal-safe portfolio impact and
renders versioned templates. It does not call a cloud LLM. `OllamaProvider`
and `CloudLLMProvider` remain disabled architectural placeholders, not active
summarizers. The portfolio and optional explicitly configured watchlist are
the only universe; broad-market context must be material to that universe.

Brief records are immutable, owner-scoped, source-cited, and idempotent for
the same portfolio state, universe, and report window. Recommendations are
actions to review with evidence, risks, alternatives, confidence, and an
approval requirement. They never execute trades or move money.

Email is a notification surface only. Its projection excludes account and
internal identifiers, evidence hashes, and detailed holdings values by
default. Real Resend transport requires an explicit enabled configuration,
credentials, recipient authorization, a secure link, and injected transport;
the checked-in configuration and certification use only fake adapters. The
local scheduler artifact is an uninstalled template.

## Consequences

- Provider or data-quality failures produce visible bounded warnings or fail
  closed; they do not invent financial facts.
- Unit, integration, and certification tests use synthetic data and fake
  transports, so CI has no external market-data or email dependency.
- A paid provider, real delivery activation, local LLM activation, multi-user
  rollout, brokerage integration, or expanded data universe requires a new
  reviewed decision and authorization.
