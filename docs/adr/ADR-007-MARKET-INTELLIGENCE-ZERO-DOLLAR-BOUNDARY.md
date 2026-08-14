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

## Reliability correction amendment (2026-08-12)

The accepted zero-dollar boundary now uses a deterministic standard-library US
market-session policy. During regular US sessions (09:30–16:00 Eastern on
weekday trading days, excluding the documented full-day holiday set), Finnhub
quotes must be observed within 15 minutes to be labelled `live`. Outside the
session, a quote observed at or after the close boundary may be labelled
`prior_close` only when it is within three completed trading sessions. Weekend,
holiday, premarket, and after-hours behavior therefore remains bounded without
introducing a paid calendar dependency. Early closes are intentionally not
modeled.

The operational composer evaluates every active non-cash holding independently.
It uses value-weighted coverage when all eligible current values are finite and
usable, otherwise position-count coverage, and requires at least 80% coverage.
Partial briefs disclose omitted symbols and stable sanitized reason codes;
zero-coverage, below-threshold, mixed-currency, and invalid-evidence cases fail
closed. Coverage basis, percentage, omission reasons, and price basis are part
of new canonical hashes so idempotent replay cannot change the data basis.

This amendment changes no provider cost boundary, ownership boundary,
immutability rule, delivery behavior, execution capability, or Phase 6 Scenario
Lab contract. It remains deterministic, source-cited, review-only, and default-
off.

## Market Intelligence v2 amendment (2026-08-13)

Market Intelligence v2 keeps the same zero-dollar provider boundary and adds
two explicitly authorized layers on top of it, without paid endpoints, cloud
LLM activation, execution capability, or financial mathematics changes.

### Per-holding evidence contract

The composer now assembles a bounded, source-cited intelligence packet per
safely covered holding (quote, profile/CIK, company news, earnings events and
results, SEC filings, analyst consensus and price target, dividends) and ranks
packets as `high` / `watch` / `informational` using deterministic rules. Every
optional evidence category can fail independently: the failure is recorded as
an `EvidenceAvailability` omission with a stable reason code and user-safe
recovery guidance, and never kills the complete brief. The brief fails closed
only when trustworthy portfolio coverage falls below the tested threshold.
Anticipated provider and composition failures are converted at the route
boundary into sanitized stable responses (never raw provider text or secrets),
and nothing is persisted when complete generation fails.

### Authorized universe expansion

ADR-007's original universe (portfolio + optional watchlist) is explicitly
expanded to include a read-only, quota-aware market-pulse layer and a bundled
S&P 500 symbol list used only as a scanner universe. This expansion is
authorized because it remains: (1) zero-dollar — only Finnhub free-tier
endpoints (quotes, `market_news`, market earnings calendar) are used; (2)
bounded — the scanner requests at most a bounded sample per refresh with
provider pacing and caching, portfolio holdings always take priority, and the
wholesale universe is never requested; (3) truthful — categories the free tier
cannot supply (raw indices, VIX, sector performance, top movers) are surfaced
as unavailable rather than fabricated, and index direction is reported only
through approved, clearly labeled ETF proxies (SPY/QQQ); and (4) review-only.
The bundled symbol list is factual ticker data with no financial claims.

### Command-center UI

Market Briefs is presented as a Market Intelligence command center with five
views (My Portfolio, Market Pulse, Earnings & Events, S&P 500 Scanner, Archive)
built on the existing appearance system. It preserves the provider-status
model (not checked / checking / ready / coverage limited / unavailable), the
sanitized error model, immutable archive replay, keyboard navigation,
reduced-motion support, and accessible states for every designed scenario.

This amendment changes no cost boundary, ownership boundary, immutability
rule, delivery behavior, execution capability, or financial mathematics. All
external data remains default-off behind server-owned flags, deterministic,
source-cited, and review-only.
