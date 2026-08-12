# Phase 5 Market Intelligence Brief Plan

## Authority, entry, and exit

Phase 5 begins only from certified Phase 4 (`phase-4-complete` at
`e724a0f70302e3de8b0995146fb391254c7ee52e`). It is limited to personal,
single-user, read/analyze/recommend behavior. It does not add brokerage
execution, money movement, cloud LLM use, multi-user rollout, scheduler
installation, or real email delivery during development or certification.

Its exit criterion is:

> A versioned, source-cited, portfolio-specific market briefing reports
> portfolio changes, material news, earnings and filings, deterministic
> actions to review, privacy-safe delivery, and tested failure behavior
> without paid data or autonomous execution.

## Reuse map and boundaries

| Existing component | Phase 5 use | Boundary retained |
| --- | --- | --- |
| `Holding`, holdings routes, and portfolio UI | authoritative portfolio-first universe and quantity/value snapshot input | never copy account number, credentials, import payload, or raw transaction data into a briefing |
| Existing Finnhub quote and analyst-ratings route patterns | server-side key handling, bounded HTTP calls, cache and operator-visible failures | replace unbounded per-route fan-out with provider-neutral pacing; never expose keys |
| Forecast Decimal contracts and canonical hashes | canonical decimal strings, validated time/version conventions | no float-based attribution and no changed forecast authority |
| Phase 3 recommendation/outcome contracts | goal linkage, evidence/risk/confidence/approval language and decision follow-up | briefing actions remain non-persistent candidates unless an existing approval flow is explicitly used later |
| Phase 4 immutable history/audit patterns | owner-scoped archive reads, append-only versioning and idempotency | a briefing is not a decision, trade, execution, or causal outcome |
| Next.js API, accessible section, toast, and print patterns | typed read clients, accessible archive/detail views and browser journeys | client never overrides a server feature flag |

## Zero-dollar provider matrix

| Provider | v1 permitted capability | Cost / legal-operational rule | Guardrail |
| --- | --- | --- | --- |
| Finnhub Free | quotes, company news, earnings calendar, and earnings surprises for held symbols | only endpoints confirmed as Free in operator configuration; re-verify terms and endpoint availability before enabling a new endpoint | reject paid-marked endpoints/configuration; 48 calls/min internal ceiling below the documented 60 calls/min allowance; cache and deduplicate |
| SEC `data.sec.gov` | submissions and normalized XBRL facts for matching public issuers | public unauthenticated JSON APIs; comply with SEC fair-access guidance (identify client and stay well below 10 requests/sec) | server-only User-Agent, 5 requests/sec ceiling, portfolio-first requests, bounded fields and links |
| Resend Free | optional transactional message send only | Free plan is the zero-dollar ceiling; confirm current plan/recipient/domain constraints before activation | adapter default-off; credentials and explicit recipient authorization required; otherwise preview only |
| Deterministic fixtures/fakes | all tests and certification | synthetic only, no network | required for CI |

Provider facts are reviewed against the official Finnhub API/pricing pages, SEC
EDGAR API and fair-access documentation, and Resend pricing before each real
provider enablement. The SEC APIs are unauthenticated JSON and include
submissions and XBRL data; the SEC limits users to 10 requests/second. No
Top-100/S&P-100 appendix ships unless a reliable, legally usable free source
is separately verified.

## Contracts, universe, and provenance

`PortfolioUniverse/v1` is a sorted, deduplicated snapshot of active portfolio
holdings; it includes normalized symbol, supported instrument type, quantity,
safe value/weight inputs, sector if authoritative, and a non-sensitive
universe hash. Every holding is primary. A user watchlist is optional only
when an explicit bounded watchlist contract is added. Broad-market context is
admitted only when it is demonstrably tied to at least one universe holding.
Cash has no external-symbol request; authoritative cash movement may be shown
only from the portfolio snapshot, otherwise it is omitted with a warning.

Provider-neutral `MarketQuoteSnapshot/v1`, `CompanyNewsItem/v1`,
`EarningsEvent/v1`, `EarningsResult/v1`, `SecFilingEvent/v1`,
`SourceMetadata/v1`, `ProviderStatus/v1`, and `NormalizedProviderFailure/v1`
carry a bounded symbol/CIK, provider, source URL, retrieved-at timestamp,
market-published/observed timestamp where supplied, freshness state, and safe
payload fields. Article body is never stored; news keeps a bounded headline,
summary/excerpt only when licensed for the endpoint, URL, publisher, and
published time. Normalization rejects unknown fields and records sanitized
failure classes (`disabled`, `unconfigured`, `paid_endpoint`, `rate_limited`,
`timeout`, `upstream`, `invalid_payload`, `stale`, `not_found`) without raw
responses or credentials.

All external text is untrusted data, never an instruction: it is rendered as
quoted/source-attributed content only, cannot invoke tools or alter rules, and
is length- and control-character-bounded. Provider usage accounting records
provider, endpoint class, cache hit/miss, count, and period only—never token,
account, recipient, or raw content.

## Market, portfolio, and relevance rules

Prices use the provider market timestamp plus retrieval time. Daily change is
`quantity × (current_price − previous_close)` when both valid positive prices
and quantity exist; weekly change uses a canonical stored/week-start snapshot,
never a fabricated prior price. Portfolio change sums only comparable
same-currency, non-stale position changes. Contribution is position change
divided by comparable portfolio change; allocation movement is current valid
weight minus baseline valid weight. Decimal arithmetic and canonical decimal
strings apply end-to-end; currency ambiguity, missing quantity, non-positive
price, conflicting quote, or stale baseline removes that calculation and adds
a warning. Sorting is deterministic (absolute impact, then normalized symbol).

Materiality is deterministic and disclosed: portfolio relevance requires a
held symbol/CIK plus a configured safe threshold (weight, absolute impact,
event imminence, or filing form allowlist). Sector exposure is computed only
from authoritative/declared sector mappings, otherwise `unknown`, never
inferred. Upcoming/recent earnings have explicit bounded windows; filing
forms are allowlisted (initially 8-K, 10-Q, 10-K, 20-F, 40-F, 6-K) and are
deduplicated by provider + issuer + accession/document identity. News,
earnings, and filings deduplicate by stable source identity, with normalized
symbol/date/title fallback. Stale/missing/conflicting data never produces a
false precision claim.

## Briefing and action contract

`atlas-market-intelligence-brief/v1` is immutable and versioned. It contains
brief ID, owner scope, report window, universe/state hash, generator version,
generated/as-of times, and the following ordered sections: executive summary;
portfolio changes; material holding news; earnings today/upcoming/recent
results; SEC filings; risks and opportunities; actions to review; sources and
as-of timestamps; and data-quality/provider warnings. Each displayed claim
has one or more `SourceCitation/v1` records (provider, stable source URL,
retrieved-at, published/market time, freshness). Missing sources cause the
claim to be omitted or downgraded to a warning.

Generation is idempotent for `(owner, portfolio_state_hash, universe_hash,
report_window, schema_version, calculation_version)` and returns the existing
record rather than duplicating it. New input or a contract/calculation version
produces a new record, never edits the historical one. `DeterministicTemplateProvider`
is v1 enabled; `OllamaProvider` is a non-enabled interface placeholder;
`CloudLLMProvider` is prohibited and default-off if represented at all. No
LLM is installed or called.

Each `ActionToReview/v1` has `action`, `why`, `goal_linkage`, `evidence`,
`expected_impact`, `risks`, `alternatives` (including do nothing where
meaningful), `confidence`, and `approval_requirement`. Templates use
conditional, educational language such as “review whether …”; they never say
that a trade was placed, direct execution, promise a return, or conceal stale
data. An action needing a portfolio change always requires explicit user
approval and remains outside execution scope.

## Archive, delivery, operations, and flags

The in-app archive is authenticated and owner-scoped: latest, bounded
pagination/list, and detail views authorize before revealing existence. It
uses accessible landmarks/headings, keyboard navigation, visible data-quality
states, source links, freshness labels, and print CSS. Detailed authenticated
views may show allowed values; email defaults to percentages/material change
only and excludes account numbers, user/internal IDs, evidence hashes, raw
holdings values, credentials, and provider payloads. A notification contains
a short summary and authenticated secure link.

`BriefEmailRenderer/v1` renders equivalent HTML and plaintext from the safe
delivery projection. `FakeEmailAdapter` is the certification default.
`ResendEmailAdapter` reads credentials only from local secrets/configuration,
is gated by server-owned delivery enablement, produces idempotent attempt and
receipt records, and has bounded retry for transient failures. Missing key,
from-address, explicit recipient authorization, or flag means fail-closed
preview-only behavior. No real recipient or key appears in source, fixtures,
logs, or certification.

`atlas_brief` local operator command supports `preview`, `generate`, and
`send`; `send` additionally requires the delivery flag and local explicit
authorization. An optional `launchd` plist template invokes preview/generate
under local operator control but is never installed by code. Rate limiters are
per-provider and endpoint, cache only bounded normalized records with
endpoint-specific TTLs, retry only transient transport/5xx failures with
jitter and a small bounded attempt count, and expose provider-health status.

Server-owned, configuration-only defaults are all false:
`atlas_market_brief_generation_enabled`, `atlas_market_brief_read_api_enabled`,
`atlas_market_brief_external_provider_enabled`,
`atlas_market_brief_email_delivery_enabled`,
`atlas_market_brief_scheduler_enabled`, and
`atlas_market_brief_local_summarization_enabled`. There is no client override.
Rollback is immediate flag disablement; cached data and historical records are
retained intact, while reads return the safe unavailable envelope.

### Safe local operational configuration

The archive is discoverable at `/market-briefs`, but every capability remains
off until the local operator sets server environment/configuration values and
restarts Rules Service.  To read previously archived briefs, set only
`ATLAS_MARKET_BRIEF_READ_API_ENABLED=true`.  To generate a new brief, also set
`ATLAS_MARKET_BRIEF_GENERATION_ENABLED=true`,
`ATLAS_MARKET_BRIEF_EXTERNAL_PROVIDER_ENABLED=true`, a local
`FINNHUB_API_KEY`, and `SEC_USER_AGENT` containing a bounded contact email as
required by SEC access guidance.  The startup factory makes no network call;
it wires no composer at all when any of these server-owned requirements is
missing or invalid.  The browser sends only the bounded report-window control:
holdings, owner identity, provider records, hashes, account identifiers, and
market facts are always assembled server-side.

Keep `ATLAS_MARKET_BRIEF_EMAIL_DELIVERY_ENABLED`,
`ATLAS_MARKET_BRIEF_SCHEDULER_ENABLED`, and
`ATLAS_MARKET_BRIEF_LOCAL_SUMMARIZATION_ENABLED` false.  Do not put secrets in
source control.  Certification uses synthetic provider fixtures and fake
delivery only; it neither imports into nor proves anything about a personal
local database.  Holdings currently carry no authoritative CIK mapping, so
the operational composer does not infer SEC filing relationships from ticker
symbols; this limitation is disclosed rather than guessed.

## Test and certification matrix

Tests are hermetic with synthetic fixtures/fakes: contracts and normalized
failures; paid-endpoint rejection and zero-dollar accounting; Finnhub pacing,
cache, timeout/retry, and 60/min ceiling; SEC User-Agent/pacing/parser tests;
deduplication; Decimal attribution and golden briefing fixtures; stale,
missing, currency-ambiguous, and conflicting prices; citations/freshness;
source/body/sensitive-data exclusion; injection-like external text; idempotent
versioning; owner isolation and feature flags; email HTML/plaintext and
duplicate-send/retry receipts; CLI preview and non-installed scheduler.

Certification additionally runs the complete Rules Service suite, relevant
Finlynq and cross-service suites, frontend Vitest/typecheck/lint, axe and a
dedicated briefing browser journey, canonical Playwright matrix, and tracker,
deterministic-render, and handoff validation. It uses fake/sandbox delivery
and sends no real email.

## File-by-file build plan and cohesive PR slices

1. **Slice 1 — research-data foundation (high risk):** add a bounded
   `app/market_intelligence/` provider-contract package, Finnhub and SEC
   adapters, cache/pacing/usage accounting, synthetic fixtures/fakes, settings
   flags, and focused tests. Reuse—not expand—legacy holdings routes.
2. **Slice 2 — deterministic impact and briefing engine (high risk):** add
   Decimal-safe portfolio snapshot/attribution, relevance/dedup rules,
   `Briefing` persistence migration/models/repository/service/schemas,
   deterministic templates, read/generate routes, fixtures, and tests.
3. **Slice 3 — archive, email, and scheduling interface (high risk):** add
   typed UI API client, briefing archive/latest/detail components/pages/tests,
   print styles, email projection/templates/adapters/preferences/delivery
   receipts, operator CLI and uninstalled `launchd` template, browser/a11y
   coverage, and documentation.

Each high-risk slice uses one branch, one PR, relevant CI, a fresh exact-head
read-only review, and no more than two correction/review cycles. A corrective
PR is permitted only for a real safety or certification boundary. The parent
operator owns Git, tracker, CI, merge, and certification; the single worker is
the sole implementation writer; each reviewer is read-only and short-lived.
