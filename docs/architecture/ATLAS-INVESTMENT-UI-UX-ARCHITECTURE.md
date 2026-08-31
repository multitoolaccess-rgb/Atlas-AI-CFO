# Atlas Investment Intelligence UI/UX Architecture

**Status:** UI/UX-01 architecture checkpoint — planning only
**Scope:** Atlas-native investment experience; no production UI, API, schema, dependency, or backend changes
**Boundary:** Atlas analyzes and explains; the user decides. No trading, brokerage mutation, transfers, or money movement.

## 1. Executive summary

Atlas should evolve its existing Wealth, Portfolio, Market Intelligence, Decisions, Goals, and Scout surfaces into one evidence-first investment workspace rather than a separate terminal product. The UI consumes Atlas-owned read models and preserves the existing shell, tokens, accessibility conventions, route compatibility, and server-owned financial authority.

The primary experience is a calm decision workspace: a user can see what changed, understand what deserves attention, inspect evidence and uncertainty, ask Scout questions in context, and record a decision without any implication that Atlas executed an investment action.

This document is authoritative for future investment UI planning. It does not authorize implementation.

## 2. Current Atlas UI assessment

Atlas is a Next.js 14 App Router application using React 18, Tailwind CSS, Lucide icons, Recharts, Framer Motion, and existing Atlas-owned primitives. `PageLayout` provides the shared shell; `Sidebar` groups routes into Home, Money, Wealth, Intelligence, and System; `PageHeader`, `PageTabs`, `AnalyticalContextBar`, `AnalyticalPageFrame`, `Card`, `Surface`, `ChartWrapper`, `Badge`, `EmptyState`, and `ErrorBanner` provide the current composition vocabulary. `ui/lib/informationArchitecture.ts` already defines route and tab contracts.

| Surface | Assessment | Rationale |
|---|---|---|
| Mission Control `/` | KEEP | Cross-domain priority surface; investment attention can be summarized here later without making it an investment terminal. |
| Portfolio `/portfolio` | ENHANCE | Existing holdings, import, refresh, allocation, and analyst coverage provide the correct owner-scoped home; add read-only intelligence progressively. |
| Wealth `/wealth` | ENHANCE | Keep balance-sheet authority; link to Portfolio for investment detail rather than duplicating analytics. |
| Market Intelligence `/market-intelligence` | ENHANCE | Existing evidence-first brief, pulse, events, scanner, and archive patterns are a strong home for daily market context. |
| Decisions `/decisions` | ENHANCE | Existing append-only decision and outcome boundary should become the recommendation review surface. |
| Goals `/goals` | KEEP / ENHANCE LATER | Existing goal and forecast workflows remain authoritative; investment fit should consume them, not copy them. |
| Scout `/assistant` and copilot dock | ENHANCE | Add contextual evidence queries only through typed, read-only contracts. |
| Scenario Lab `/scenario-lab` | KEEP / ENHANCE LATER | Existing bounded what-if pattern is suitable for portfolio-impact previews when backend contracts exist. |
| Accounts / Data Connections | KEEP | Source and ownership management remain separate from research. |
| Legacy `/recommendations`, `/market-briefs`, `/accounts`, `/income`, `/expenses`, `/activity` | KEEP compatibility | Existing redirects and route compatibility protect user muscle memory; do not replace abruptly. |
| New terminal-style dashboard | REJECT | Duplicates the shell, increases density, and conflicts with Atlas's consumer CFO character. |

No existing page should be replaced solely for visual reasons. Existing modified UI files in the worktree are unrelated to this checkpoint and remain untouched.

## 3. Goals and design principles

1. **Questions before modules.** Navigation starts with user intent: review, understand, investigate, compare, and decide.
2. **Evidence before conclusion.** Every material claim has a visible path to source observations or deterministic calculations.
3. **Calm precision.** Preserve Atlas's Space Grotesk / JetBrains Mono typography, semantic tokens, restrained surfaces, and tabular financial values.
4. **One source of truth.** UI consumes Atlas projections; it never reads provider payloads or calculates authoritative financial facts.
5. **Uncertainty is information.** Observed, derived, estimated, stale, missing, and unavailable states are explicit text, not color-only decoration.
6. **Progressive disclosure.** Normal users see a concise explanation; advanced users can expand the full provenance chain.
7. **User control.** Use Review, Consider, Compare, Watch, Analyze, Accept analysis, Reject analysis, and Record decision. Never use Buy Now, Sell Now, Execute Trade, or Auto Invest.
8. **Responsive by design.** Mobile is a prioritized reading and review flow, not a shrunken desktop terminal.
9. **Reversible delivery.** New screens are additive, feature-gated, and backed by stable contracts and explicit empty/partial/error states.

## 4. Existing UI reuse strategy

Reuse the existing `PageLayout`, sidebar groups, `PageHeader`, URL-synced `PageTabs`, `AnalyticalContextBar`, `AnalyticalPageFrame`, `Card`/`Surface`, `ChartWrapper`, `Badge`, `EmptyState`, `ErrorBanner`, Lucide icons, Recharts wrappers, theme tokens, and Scout/coplayout. Investment-specific components should be thin compositions of these primitives, not a second design system.

Use existing `market-intelligence` evidence/citation patterns as the model for source links, freshness, coverage limitations, and archive behavior. Use existing `decisions` patterns as the model for append-only user decisions. Use existing Portfolio ownership and data-quality disclosures as the model for private data.

## 5. Investment information architecture

The recommended hierarchy keeps current Atlas navigation stable:

```text
Home
  Mission Control
Money
  Cash Flow · Plan
Wealth
  Wealth · Portfolio · Goals
Intelligence
  Investment Brief       (future, may initially be a Market Intelligence view)
  Market Intelligence   (existing)
  Research              (future)
  Decisions             (existing; recommendation review)
  Scenario Lab          (existing)
System
  Data Connections · Settings · Help
```

Avoid a deep module tree such as separate top-level Fundamentals, Technicals, Macro, and Quant routes. Those are evidence lenses inside a security workspace and should also appear in a brief or portfolio context. Proposed future route surfaces:

- `/investments` — Investment Overview / Daily Brief, only when a complete read model exists.
- `/investments/security/[securityId]` — canonical security research workspace.
- `/investments/research` — opportunity discovery and saved research, later.
- `/portfolio` — owner-scoped holdings and portfolio intelligence remains canonical.
- `/decisions` — recommendations, decision journal, and outcomes remain one lifecycle.

Route activation must follow `ui/lib/informationArchitecture.ts`; no destination is activated before its complete surface and backend contract exist.

## 6. Backend capability to UI mapping

| Backend capability | User concept | UI component pattern | Screen / workflow |
|---|---|---|---|
| Investment context / evidence | “What supports this?” | EvidenceCard + EvidenceDrawer | Any brief, security, portfolio, or decision view |
| Security identity + market observations (INV-02) | Trusted security and price context | SecurityHeader + freshness/data-quality badge | Security workspace; Portfolio drill-down |
| Portfolio snapshot (INV-03) | What I own and how it is distributed | PositionStrip + ExposureChart + concentration list | Portfolio Overview / Analysis |
| Fundamental facts (INV-04) | Business performance and quality | FundamentalMetricCard + period selector | Security Research |
| Technical Research (INV-05) | Trend, momentum, volatility | PriceChart + indicator rows | Security Research |
| Macro Intelligence (INV-06) | Current economic backdrop | MacroIndicatorCard + context strip | Daily Brief / Security context |
| Quant Research (INV-07) | Returns and risk statistics | QuantMetricCard + methodology disclosure | Security Research / Portfolio Analysis |
| AI Committee (INV-08) | Balanced thesis and dissent | ThesisCard + SignalSummary + dissent panel | Decision review |
| Recommendations (INV-09) | A considered action with reasons | RecommendationCard + evidence drawer | Decisions / Daily Brief |
| CIO reports (INV-10) | Periodic review | BriefHeader + report sections + archive | Investment Brief |
| Tracking (INV-11) | What was decided and what happened | DecisionTimeline + OutcomeCard | Decisions |
| Evaluation (INV-12) | How reliable is the system? | EvaluationSummary, internal/advanced | Later operations/research surface |

All components consume Atlas-owned projections. Provider-specific names, raw payloads, and external schemas terminate in backend adapters.

## 7. Primary user journeys

### A. Morning review

Mission Control or Investment Brief → portfolio movement and coverage → macro/market context → attention items → evidence → optional recommendations → investigate or record a decision. The first view should answer “what changed?” before “what should I do?”

### B. Research a security

Search/select security → identity and price header → Atlas View summary → fundamentals → technicals → quant → macro context → valuation/risk when available → evidence → thesis/scenarios later. Above the fold contains identity, as-of/freshness, current market context, and a concise evidence summary; deep metrics are below.

### C. Evaluate a recommendation

Recommendation → thesis and action vocabulary → signal agreement/conflict → portfolio impact → risks and invalidation conditions → evidence drawer → scenarios → user decision. The primary CTA records a review/decision, never a trade.

### D. Portfolio review

Portfolio → snapshot/as-of and data coverage → allocation/concentration → performance/drawdown/risk → position drill-down → decision review. Unknown or stale holdings remain visible as limitations.

### E. Discover an opportunity

Research → bounded screen/filter → candidate list → compare → security workspace → Atlas analysis → watch/consider/reject. Screening and ranking must expose methodology and never imply a recommendation by position alone.

## 8. Daily Investment Brief

The brief should be a server-owned, immutable read model with this hierarchy:

1. **As of / coverage:** report timestamp, source freshness, and omitted or stale data.
2. **Portfolio:** material changes and concentration/risk attention.
3. **Market and macro:** relevant context, not an undifferentiated news wall.
4. **Attention:** ranked evidence items with why they matter.
5. **Opportunities:** candidates only when an approved backend projection exists.
6. **Recommendations:** evidence-first cards with action, confidence, risks, portfolio impact, and user-control state.
7. **Sources and methodology:** expandable provenance.

A brief must render honest loading, empty, partial, stale, unavailable, and archived states. “No items” must not mean “no risk.” Every recommendation card displays action vocabulary, confidence semantics, thesis, supporting domains, conflicts, risks, invalidation conditions, freshness, as-of, and a View Evidence affordance.

## 9. Portfolio experience

Keep the current Portfolio page as the owner-scoped source-facing workspace. Add intelligence in progressive layers:

- **Overview:** snapshot as-of, total coverage, allocation, largest exposures, cash/unknown state, and attention summary.
- **Detailed analysis:** position intelligence, sector/geography/currency/account exposure, concentration, performance, drawdown, risk, and provenance.
- **Drill-down:** position → security research, preserving account/owner context without exposing unnecessary account identifiers.

Do not silently treat legacy Float holdings as exact historical truth. Show missing cost basis, stale price, unresolved identity, and partial history as data-quality states.

## 10. Security research experience

The canonical security workspace should use one page with evidence lenses rather than seven disconnected routes:

```text
Security header: identity, exchange, price basis, as-of, freshness
Atlas View: concise evidence summary, not an opaque score
Fundamentals · Technicals · Quant · Macro · Valuation · Risk
Events / filings / relevant news
Thesis and scenarios (later, server-owned)
Evidence and methodology
```

The header and Atlas View are above the fold. A compact signal summary may show `Observed`, `Derived`, `Stale`, or `Unavailable`; it must not collapse mixed signals into a green overall badge. Empty and unsupported securities explain what is missing and how to recover.

## 11. Opportunity discovery

Later research should provide a bounded universe, explicit filters, result provenance, comparison selection, and a saved watch state. Avoid a “hot stocks” feed. Ranking must be explainable, timestamped, and separated from recommendation authority. The first implementation can be a read-only table with mobile filter sheets and a clear “not a recommendation” boundary.

## 12. Recommendation UX

The primary unit is an evidence-first review card:

```text
AAPL · Atlas View: Consider
Confidence: High / Medium / Limited evidence
Why now: concise thesis generated from validated evidence
Signals: Fundamentals Positive · Technicals Mixed · Quant Positive · Macro Unknown
Portfolio impact: concentration / liquidity / objective context
Risks: explicit bullets
What would change the view: invalidation conditions
As of: timestamp · Freshness: label
[View evidence] [Compare] [Record decision]
```

Action labels and confidence are server-owned. Conflicting signals are represented explicitly with positive, negative, and uncertain groups. The UI never turns confidence into a probability unless the backend defines calibration and semantics.

## 13. Evidence and provenance UX

Use three disclosure levels:

- **Normal:** `SEC EDGAR · Aug 28, 2026 · Observed` or `Atlas calculation · as of ...`.
- **Expanded:** source/series, observation period, as-known-at, retrieved-at, methodology, calculation version, quality, and source identifiers.
- **Advanced:** full evidence chain, input hashes, normalization/calculation versions, revision links, and related records.

Evidence drawers must preserve the originating screen context and be keyboard dismissible. Source links are sanitized server-owned URLs. Derived metrics list source fact/observation references rather than presenting prose as authority.

## 14. Uncertainty UX

Every status uses at least a text label and, where useful, an icon or pattern:

| State | UI treatment |
|---|---|
| Observed | “Observed” badge + source/as-of |
| Derived | “Derived” badge + formula/version |
| Estimated | “Estimate” badge + estimate type/source |
| Unknown | “Unknown” label + explanation |
| Missing | “Missing input” label + recovery |
| Stale | “Stale” warning + timestamp |
| Insufficient history | “Insufficient history” label + required lookback |
| Conflicting | “Signals are mixed” panel with domain-level reasons |
| Unavailable | “Unavailable” label + provider/coverage reason without secrets |

Do not rely on red/green alone. Tooltips explain unfamiliar terms; screen-reader text includes state and consequence.

## 15. AI interaction model

Scout has three context levels:

1. **Global:** “What changed in my portfolio this week?”
2. **Page context:** “Why is concentration high here?”
3. **Evidence context:** “What supports this revenue-growth claim?”

The UI passes a server-owned context reference, not raw provider payloads or client-authored financial facts. Responses cite evidence references and clearly separate facts, calculations, assumptions, and interpretation. Scenario questions remain hypothetical. No assistant affordance can execute, place, submit, transfer, or mutate.

## 16. Human decision boundary

The persistent copy should state: `Atlas analyzes and recommends. You decide.` Decision buttons are `Consider`, `Review evidence`, `Add to watchlist`, `Compare`, `Record decision`, `Dismiss`, or `Ask Scout`. The system may record accept/reject/defer/watch decisions as append-only user decisions; this is not execution and does not update brokerage state.

## 17. Visualization strategy

Use visualization only where it clarifies a question:

- **Security:** price/adjustment-basis chart, volume, SMA/RSI when available, drawdown, benchmark comparison, event markers, and fundamental period markers.
- **Portfolio:** value/performance, allocation, concentration, drawdown, contribution, and risk; tables remain the authoritative detail.
- **Macro:** rate/yield curve, inflation, growth, labor, and regime context when supported.
- **Evidence:** compact sparklines and source-linked metric rows, never decorative dashboards.

All charts include an accessible label, date/period, source/freshness, legend, and a textual/table fallback when data is unavailable or chart semantics are insufficient.

## 18. Charting architecture

**Recommendation: retain Recharts now and add a dedicated financial chart library only after a focused compatibility spike.** Recharts is already installed, integrated, and tested; it is sufficient for allocation, trend, macro, and compact analytical charts. Do not add a dependency during UI/UX-01.

For future OHLCV/zoom/pan/overlay needs, evaluate Apache-2.0 Lightweight Charts as a later, isolated adapter candidate, with license and accessibility review at the exact release. TradingView-style interaction is useful, but Atlas should not copy TradingView's product identity or workflow. D3 remains an internal utility only where existing Atlas charts require it. Avoid FinceptTerminal, OpenBB, or a terminal framework as UI foundations.

## 19. Component architecture

Prefer a small set of reusable compositions:

- `InvestmentBrief` / `AttentionList`
- `SecurityHeader` / `AtlasViewSummary`
- `EvidenceCard` / `EvidenceDrawer`
- `DataQualityBadge` / `ProvenanceBadge`
- `SignalSummary` / `ConflictPanel`
- `InvestmentMetricCard`
- `FinancialTimeSeriesChart` adapter over selected chart technology
- `PortfolioExposureView`
- `RecommendationReviewCard`
- `DecisionTimeline`
- `ScenarioComparison`

These should compose current `Card`, `Badge`, `ChartWrapper`, `PageTabs`, and `AnalyticalPageFrame`; avoid one component per backend field or domain module.

## 20. API/data requirements

Future screens require read-only Atlas projections, not provider calls from the browser:

| UI need | Required backend projection |
|---|---|
| Investment Brief | immutable brief/report envelope with coverage, freshness, sections, evidence references |
| Portfolio analysis | owner-scoped snapshot, position/exposure/risk projection with as-of/hash |
| Security research | public security projection plus evidence and research metrics; no portfolio fields by default |
| Evidence drawer | bounded evidence packet with source, timestamps, versions, hashes, and access scope |
| Recommendation review | recommendation lifecycle record, signal findings, confidence semantics, risks, and decision preconditions |
| Compare | bounded multi-security read model with common period/basis and omissions |
| Scenario | server-owned deterministic preview, no persistence or mutation unless separately authorized |
| Archive | immutable report/research index with owner scope and retention policy |

All endpoints must follow existing auth, owner isolation, response envelopes, sanitized errors, pagination, cache, and versioning conventions. Public/company research must not leak holdings, account IDs, cost basis, or portfolio weights.

## 21. Responsive strategy

- **Desktop/laptop:** fixed rail plus fluid canvas; asymmetric lead area and evidence rail; tables may scroll horizontally.
- **Tablet:** collapsible rail, two-column evidence where readable, controls wrap rather than compress.
- **Mobile:** off-canvas navigation, one-column cards, horizontal tab scroller, filter bottom sheets, priority summary first, compact chart with table fallback, no hover-only meaning, and 44px targets.
- **All sizes:** preserve as-of/freshness and uncertainty near the claim; do not hide limitations below an inaccessible fold.

## 22. Accessibility

Maintain WCAG 2.2 AA, visible keyboard focus, semantic headings, native controls, screen-reader labels, reduced motion, contrast, non-color status, 200% zoom, and focus-managed drawers/dialogs. Charts require a text summary or data table for meaningful values. Keyboard users must reach evidence, methodology, and decision controls in logical order. No information may be encoded only by position, animation, or color.

## 23. Performance

Lazy-load deep research tabs and expensive charts; load summary and data-quality state first; paginate large universes and archives; virtualize only after measured need; cache immutable research by contract/hash; use incremental evidence loading; keep expensive quant work server-side; avoid browser-side provider calls and large raw payloads. Live/streaming data is a later operational decision, not a UI assumption.

## 24. Open-source UI/UX evaluation and adoption matrix

The existing open-source investment stack was reviewed for UX patterns as well as backend suitability. Code and branding are not copied.

| Project | UI/UX pattern | Why useful | Atlas adoption | Implementation approach |
|---|---|---|---|---|
| FinceptTerminal | Dense research navigation, multi-panel terminal, watchlists, broad market workspace | Demonstrates discoverability and research breadth | INSPIRE | Borrow progressive research navigation and keyboard-minded density; simplify to personal-investor workflows; no code, branding, layout, or assets; AGPL/trade-dress concerns mean no embedding. |
| OpenBB | Unified data/workspace concept and modular research views | Shows one research surface can combine providers | INSPIRE | Apply only the “one Atlas contract, many evidence lenses” idea; retain Atlas adapters and licensing boundary; no platform dependency. |
| QuantConnect LEAN | Research notebook/backtest workflow separation | Useful for later advanced research concepts | INSPIRE | Keep research/evaluation separate from user decisions; no .NET engine or execution-oriented UI now. |
| PyPortfolioOpt | Focused analytical outputs | Baseline explainable allocation patterns | INSPIRE | Use compact metric/table presentation if later adopted behind backend adapter; no dependency now. |
| Riskfolio-Lib / skfolio | Risk and model-comparison workspaces | Future advanced risk context | INSPIRE | Show methodology, assumptions, and comparison; defer UI until backend scope exists. |
| TradingView / Lightweight Charts ecosystem | Zoomable financial time series, overlays, crosshair, event markers | Strong security-chart interaction | ADAPT later | Evaluate Lightweight Charts release/license/accessibility; wrap behind Atlas `FinancialTimeSeriesChart`; Recharts remains default now. |
| Recharts | Declarative React charts already in Atlas | Existing compatibility, tests, theme integration | ADOPT / RETAIN | Extend existing wrappers; add investment charts only with textual fallback and source context. |
| D3 / d3-sankey | Composable visualization primitives | Already supports Atlas custom flows | ADAPT selectively | Use only for bounded visual primitives; never expose D3 data models as domain contracts. |
| TanStack Table | Headless sortable/filterable table pattern | Useful for large research tables | MONITOR / ADAPT later | First use existing tables; evaluate only when pagination/virtualization demands it. |
| Lucide | Accessible icon vocabulary already installed | Consistent status and action cues | ADOPT / RETAIN | Reuse existing icons; pair with text for financial meaning. |
| FinRobot / finance AI workspaces | Debate and research-pane patterns | Highlights contextual explanation | INSPIRE | Adopt evidence/thread separation only; no second agent runtime or opaque AI score. |

### Fincept-specific conclusion

Fincept is useful as a reference for broad research navigation, watchlists, multi-panel exploration, and keyboard-aware density. Atlas should simplify those strengths into a morning brief, one security workspace, focused portfolio analysis, and an evidence drawer. Terminal-level provider breadth, perpetual dashboards, and dense multi-monitor workflows are excessive for a personal investor and are rejected.

## 25. Recommended technology stack

| Purpose | Recommendation | License / posture | Adopt now? | Alternatives / note |
|---|---|---|---|---|
| App framework | Existing Next.js + React | Existing project posture | Yes, retain | No migration. |
| Styling/design | Existing Tailwind + Atlas tokens/primitives | Existing project posture | Yes, retain | No separate investment theme. |
| Icons | Lucide React | Existing dependency; verify release at upgrade | Yes, retain | No new icon set. |
| General charts | Recharts | Existing dependency; verify release at upgrade | Yes, retain | D3 remains selective utility. |
| Financial OHLCV charts | Lightweight Charts candidate | Apache-2.0 reported; exact release/license review required | Later | ECharts/Plotly require separate license/accessibility/performance review. |
| Tables | Existing semantic tables first | No new dependency | Now | TanStack Table later if measured scale requires it. |
| Motion | Existing Framer Motion, reduced-motion guarded | Existing dependency | Retain sparingly | CSS transitions for basic state. |
| Data fetching | Existing `ui/lib/api.ts` and cache/query conventions | Atlas-owned boundary | Yes, retain | No browser provider SDKs. |

No dependencies were added or modified during UI/UX-01. The recommended stack is intentionally conservative.

## 26. Anti-goals

- Bloomberg, Fincept, or TradingView clone.
- Autonomous trading, broker execution, order submission, rebalancing, transfer, or money movement UI.
- A second portfolio ledger or provider-specific UI.
- Opaque “AI score” as the primary experience.
- Recommendation cards without evidence, risks, uncertainty, or as-of context.
- A separate investment design system or decorative terminal aesthetic.
- Browser-side external financial-data calls.
- Unbounded real-time streaming, huge watchlists, or a full optimizer before contracts and data quality exist.
- Copying proprietary branding, layouts, workflows, code, assets, trade dress, or visual identity.

## 27. Future implementation phases

The separate roadmap document defines bounded UI delivery phases. Backend INV-08 through INV-12 can continue independently unless a phase requires a concrete read-only projection contract. UI work must consume stable Atlas contracts and must not become a backdoor for backend authority.

## 28. Dependencies on INV-08 through INV-12

- **INV-08:** typed findings, evidence coverage, disagreement, and chair draft enable SignalSummary, conflict, thesis, and evidence views.
- **INV-09:** recommendation lifecycle and confidence semantics enable recommendation review and user decision controls.
- **INV-10:** immutable report profiles and scheduling/read models enable Daily Investment Brief and archive.
- **INV-11:** decision/outcome/supersession contracts enable Decision Timeline and review history.
- **INV-12:** replay/calibration/evaluation results enable internal trust and methodology views, not a marketing score.

These are data dependencies, not permission to implement later backend phases during this checkpoint.

## 29. Risks

- Stable read models may lag backend research contracts.
- Dense evidence can overwhelm normal users without progressive disclosure.
- Confidence semantics may be misunderstood without calibration.
- Stale or partial data can be visually overemphasized as current.
- Chart accessibility and mobile readability may be weaker than desktop interaction.
- Public research and private portfolio context may leak if projections are not separated.
- Open-source financial chart/table licenses and data rights may change.
- Existing dirty UI work increases merge/ownership risk; future implementation must isolate files and hunks.

## 30. Open questions

1. Should the first Investment Brief be a new `/investments` route or a tab inside existing Market Intelligence?
2. Which backend report envelope and evidence packet are stable enough for UI consumption after INV-08/10?
3. What confidence vocabulary and calibration disclosure will INV-09 approve?
4. Which exact Lightweight Charts release, if any, passes license, bundle, accessibility, and mobile tests?
5. When does Portfolio need a dedicated read model instead of extending existing route payloads?
6. How should user watch states and decision journal entries be retained under the current personal-use retention policy?
7. Which comparison limits preserve useful context without exposing unnecessary private portfolio data?
8. What is the minimum evaluation harness threshold required before recommendation UI is production-authoritative?

## 31. Validation and rollback

This checkpoint validates documentation against the actual Next.js routes, existing shell/primitives, current dependencies, information-architecture contract, Market Intelligence evidence patterns, Portfolio/Decisions/Scout surfaces, and INV-01–07 contracts. No production UI or dependency was changed.

Rollback is documentation-only: remove or supersede these planning documents. Future UI phases must be additive, feature-gated, and independently reversible; never delete or rewrite financial history to roll back presentation.
