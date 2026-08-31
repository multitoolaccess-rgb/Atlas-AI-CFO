# Atlas Open-Source Investment Stack

**Repository:** `multitoolaccess-rgb/Atlas-AI-CFO`  
**Research date:** 2026-08-30  
**Scope:** Ecosystem research and architecture recommendation only. No packages were installed and no repository code was changed.

> **Important:** Project licenses, provider terms, datasets, and hosted-service terms change. This document records the sources and findings checked on the research date. Before adding a dependency or shipping a commercial service, perform a release-specific license and terms review.

## 1. Executive summary

### Atlas authority boundary

External/open-source projects may provide adapters, data sources, analytical engines, or research tools. Atlas validates their outputs and remains the canonical financial model, portfolio state, provenance, recommendation authority, authorization, decisions, and outcomes.

### Human decision boundary

```text
Research → Analysis → Recommendation → User Decision

Never: Research → Analysis → Recommendation → Automatic Execution
```

Atlas should adopt a **small, layered, permissive-by-default dependency set** and retain ownership of its financial authority, provenance, suitability, recommendation, and user-control contracts.

The recommended initial posture is:

1. **Keep the existing Atlas Market Intelligence adapters and contracts.** They already implement the most important safety boundaries: bounded normalized records, source metadata, freshness, coverage omissions, pacing, caching, retries, normalized failures, synthetic transports, and no raw provider payloads across the boundary.
2. **Use EdgarTools selectively for SEC/EDGAR parsing and XBRL convenience** if a focused compatibility spike confirms it can replace or complement the current SEC adapter without weakening Atlas’s bounded contracts. It is MIT-licensed, Python-native, typed, and specifically designed for filings, XBRL, insider trades, and fund holdings.
3. **Use Riskfolio-Lib or skfolio behind an Atlas optimizer interface, not directly from routes or agents.** Riskfolio-Lib is broad and powerful but heavier and solver-dependent. skfolio is particularly attractive for a later research/validation layer because it is scikit-learn compatible, supports factor models, model selection, stress testing, and purged/walk-forward validation, and is BSD-3-Clause. For the first slice, neither is required.
4. **Use QuantLib only for instruments and quantitative-finance areas where it materially reduces custom mathematics**—especially rates, bonds, derivatives, calendars, and cash-flow instruments. It is C++ with SWIG bindings, so it is not the natural first tool for basic equity portfolio metrics.
5. **Use pgvector only after PostgreSQL becomes an approved Atlas deployment dependency.** It keeps vectors beside relational ownership/history and is Apache-2.0. Do not introduce Qdrant, Weaviate, OpenSearch, or Elasticsearch for the current single-user local product unless scale or retrieval requirements prove PostgreSQL insufficient.
6. **Do not adopt FinceptTerminal or OpenBB as embedded application foundations without legal review.** Both currently present AGPL/commercial-license implications. Fincept’s current repository license explicitly states AGPL-3.0-or-later and that there is no paid exemption for the repository; commercial/institutional users are directed to a separate Enterprise product. OpenBB’s ODP licensing FAQ describes AGPL with a commercial-license option. They may be useful as external research tools or architectural references, but they are poor default dependencies for a proprietary Atlas product.
7. **Do not adopt FinRobot as Atlas’s recommendation authority.** It is a useful research reference and possible isolated experiment, but it overlaps Atlas’s intended agent architecture, depends on external data/LLM providers, and introduces a large framework surface. Reuse ideas and deterministic operator patterns rather than importing the platform.
8. **Do not use yfinance as an authoritative production data source.** Its code is Apache-licensed, but its own README says it uses Yahoo’s publicly available APIs, is intended for research/education, and the downloaded data is subject to Yahoo terms and personal-use restrictions.
9. **Do not add LangGraph or PydanticAI yet.** Atlas’s existing assistant/orchestration boundary plus Pydantic contracts is sufficient for the first bounded workflow. If durable multi-agent workflows become necessary, evaluate PydanticAI first for typed tools/output and LangGraph for long-running stateful orchestration; neither should own financial policy or calculations.

### Overall decision

**REUSE > ADAPT > BUILD**:

- Reuse Atlas’s existing provider, provenance, recommendation, journal, and security boundaries.
- Adapt narrowly scoped open-source numerical/filing libraries behind pure internal interfaces.
- Build only the Atlas-specific canonical investment ledger, portfolio-fit logic, suitability policy, evidence/recommendation contracts, and user-control workflow.

## 2. Candidate projects

Scores are Atlas fit scores out of 5, where 5 means strong fit for the stated Atlas role—not popularity or general quality.

### 2.1 Financial terminals and research platforms

#### FinceptTerminal

- **GitHub:** https://github.com/Fincept-Corporation/FinceptTerminal
- **Observed repository signals:** approximately 30.8k stars and 4.4k forks at research time; repository page identifies a modern finance application with market analytics, investment research, and economic-data tools.
- **Language/architecture:** desktop/full application; repository details should be checked at the selected commit before any technical reuse.
- **License:** current `LICENSE` is AGPL-3.0-or-later with an extensive licensing notice. The checked `docs/COMMERCIAL_LICENSE.md` version dated 2026-08-11 says the previous dual-licensing arrangement is discontinued, there is no paid exemption for the repository, and commercial/institutional/academic needs are served by separate Fincept Terminal Enterprise products.
- **Maturity:** substantial visible product/repository activity and broad surface area; maturity of individual components for embedding in Atlas is not established by popularity alone.
- **Strengths:** broad terminal UX, data connectors, financial research workflows, potential reference implementation for user-facing research ergonomics.
- **Weaknesses:** large application overlap, strong copyleft, trademark/trade-dress restrictions, provider/data coupling, unclear component-level reuse boundary, and high integration surface.
- **Data dependencies:** Fincept data/API services and other provider integrations; data terms are separate from code license.
- **API quality:** likely optimized for its own application rather than a stable embeddable Atlas library; requires component-by-component audit.
- **Extensibility:** technically broad, legally constrained for proprietary derivative/network use.
- **Commercial implications:** do not assume AGPL permits commercial Atlas use. The current repository text states AGPL obligations, no paid repository exemption, and directs commercial use to Enterprise. Trademark and trade-dress restrictions also matter.
- **Atlas integration complexity:** 5/5 (highest complexity).
- **Atlas fit:** **1.5/5**.
- **Recommended usage:** **Avoid as a code dependency.** It may be evaluated as an external personal research tool or UX reference. Individual independent libraries may only be reused after verifying their own licenses and provenance; do not copy repository components by assumption.

**Answers to the required questions:**

1. **External tool/service:** potentially usable by an individual personally under its current terms, but Atlas must not represent that use as a safe commercial/service dependency without legal and provider-terms review.
2. **Individual libraries/components:** only where the component has an independently applicable license and no derivative/trade-dress coupling; audit each component and dependency.
3. **Commercial license:** the current repository says there is no paid exemption for this repository; commercial/institutional use is directed to Fincept Terminal Enterprise. Do not plan around purchasing a repository commercial license.
4. **Default decision:** avoid embedding or forking. Prefer independent permissive libraries and Atlas’s existing adapters.

#### OpenBB / Open Data Platform

- **GitHub:** https://github.com/OpenBB-finance/OpenBB
- **Observed repository signals:** substantial community footprint; the repository describes ODP as a Python data-integration platform for analysts, quants, and AI agents, with Python, REST, MCP, and Workspace integration paths.
- **Language/architecture:** Python package/platform with provider plugins and API server surfaces.
- **License:** repository README says AGPLv3. OpenBB’s licensing FAQ says ODP transitioned from MIT to AGPL and offers a commercial-license option; it distinguishes unmodified internal research from distribution/network service and proprietary product use.
- **Maturity:** high ecosystem maturity and broad connector coverage; version/provider stability must be pinned and tested.
- **Strengths:** “connect once, consume everywhere” design, provider ecosystem, typed-ish data access patterns, REST/MCP integration, broad research coverage.
- **Weaknesses:** AGPL/commercial licensing, broad dependency graph, provider-specific data terms, overlap with Atlas Market Intelligence adapters, possible platform lock-in, and output semantics not equal to Atlas canonical evidence.
- **Data dependencies:** public, licensed, and proprietary providers depending on the plugin; data rights are not granted by the code license.
- **API quality:** strong platform/API story, but Atlas would need a translation layer into its bounded contracts.
- **Extensibility:** strong plugin architecture; extension licensing and distribution path require review.
- **Commercial implications:** commercial proprietary product/service use may require a commercial OpenBB license or strict unmodified/standard-interface deployment arrangement. Legal review is mandatory.
- **Atlas integration complexity:** 4/5.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** **Monitor; possibly use as an external sidecar or provider-development reference.** Do not make ODP a core Atlas dependency until legal terms, provider terms, binary/service boundaries, and operational value are proven.

#### Other financial terminal platforms

No other terminal was promoted to the initial stack. Terminal products tend to bundle UI, provider agreements, workflows, and proprietary assumptions. Atlas needs normalized evidence and deterministic domain services, not a second terminal application.

### 2.2 AI financial research

#### FinRobot

- **GitHub:** https://github.com/AI4Finance-Foundation/FinRobot
- **License:** repository materials identify Apache-2.0; verify the exact dependency tree and model/data licenses before redistribution.
- **Language/architecture:** Python, with current materials describing PydanticAI + FastAPI + React/Tauri, multiple role agents, deterministic valuation operators, provider integrations, and research/report pipelines.
- **Maturity:** active and ambitious; repository README describes a large full-stack platform and recent desktop release, but broad scope increases integration and audit burden.
- **Strengths:** explicit deterministic-computation/LLM-narration separation, investment research roles, debate/synthesis patterns, valuation/report examples, provenance concepts.
- **Weaknesses:** substantial overlap with Atlas’s planned agent architecture, external LLM/provider requirements, large surface area, possible hidden assumptions in prompts/data, and no reason to import a second product runtime.
- **Data dependencies:** FMP, Finnhub, yfinance, SEC EDGAR, Adanos, news, FX, and LLM providers according to the repository description.
- **API quality:** application/pipeline oriented rather than a small stable library interface for Atlas.
- **Extensibility:** broad but expensive to adapt to Atlas ownership, evidence, and recommendation contracts.
- **Commercial implications:** Apache code is permissive subject to notices/patents; bundled models, datasets, provider terms, and generated content need separate review.
- **Atlas integration complexity:** 4/5.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** **Reuse patterns, not the platform.** Consider isolated experiments with deterministic operators only; do not import its agents as Atlas authorities.

#### FinGPT and similar AI4Finance projects

- **Source:** AI4Finance Foundation ecosystem; FinRobot is the relevant current platform candidate.
- **Maturity:** useful research ecosystem, heterogeneous project quality and maintenance.
- **Strengths:** datasets, financial NLP research, agent/forecasting prototypes.
- **Weaknesses:** research/demo orientation, model/data license variability, possible stale dependencies, reproducibility and leakage concerns.
- **Atlas fit:** **2/5** as production dependencies; **3/5** as research references.
- **Recommended usage:** monitor and selectively borrow published methods after independent validation; do not treat project outputs as investment facts.

### 2.3 Portfolio optimization

#### PyPortfolioOpt

- **GitHub:** https://github.com/PyPortfolio/PyPortfolioOpt
- **License:** verify the repository’s current license file at adoption; the project is commonly distributed under the MIT license, but release-specific verification is required.
- **Language:** Python.
- **Maturity:** mature, focused library with documentation, tests, and a stable conceptual API.
- **Strengths:** easy integration, expected-return estimators, covariance models, efficient frontier, Black-Litterman, HRP, discrete allocation, modular design, pandas ecosystem.
- **Weaknesses:** optimization results are highly sensitive to expected-return/covariance assumptions; not a data-quality, tax, suitability, or recommendation engine; pandas/float-oriented workflows require a strict Atlas boundary.
- **Data dependencies:** caller supplies prices/returns and assumptions; no authoritative market data included.
- **API quality:** approachable and modular; suitable behind an internal adapter.
- **Extensibility:** good for classical optimization and custom objectives.
- **Commercial implications:** permissive license is favorable subject to dependency audit; outputs remain Atlas responsibility.
- **Atlas integration complexity:** 2.5/5.
- **Atlas fit:** **3.5/5**.
- **Recommended usage:** **Adapt later** for allocation/rebalance research and scenario analysis, never as a direct recommendation generator.

#### Riskfolio-Lib

- **GitHub:** https://github.com/dcajasn/Riskfolio-Lib
- **License:** BSD 3-Clause according to the repository license result.
- **Language:** Python.
- **Maturity:** mature quantitative portfolio library with extensive documented risk measures and optimization methods.
- **Strengths:** broad risk-measure support (CVaR, drawdown, EVaR, tail measures), risk parity, hierarchical methods, factor models, Black-Litterman, turnover/transaction-cost/cardinality/group constraints, solver flexibility.
- **Weaknesses:** large conceptual surface, CVXPY/solver complexity, pandas/float boundary, difficult validation burden, potential overkill for a personal first slice.
- **Data dependencies:** caller supplies prices, returns, factors, constraints, and assumptions; optional commercial solvers may be used.
- **API quality:** powerful but more domain-heavy than PyPortfolioOpt.
- **Extensibility:** excellent for advanced risk/optimization research.
- **Commercial implications:** BSD-3-Clause is permissive; preserve notices and audit transitive solver licenses.
- **Atlas integration complexity:** 3.5/5.
- **Atlas fit:** **4/5** for the advanced optimization stage; **2.5/5** for MVP.
- **Recommended usage:** **Preferred advanced optimizer candidate**, behind a versioned pure-service adapter and extensive golden fixtures.

#### skfolio

- **GitHub:** https://github.com/skfolio/skfolio
- **License:** 3-Clause BSD.
- **Language:** Python.
- **Maturity:** active modern library with scikit-learn compatibility, documentation, examples, model-selection tooling, factor models, stress tests, and purged/walk-forward validation features.
- **Strengths:** unified estimator/pipeline API, risk management, factor construction, cross-validation, leakage-aware validation tooling, uncertainty sets, stress testing, transaction costs, turnover/cardinality constraints.
- **Weaknesses:** comparatively newer ecosystem than legacy tools, broad ML surface can encourage overfitting, still requires Atlas’s own data and suitability policies, numerical boundary is not automatically Decimal-safe.
- **Data dependencies:** caller supplies price/return/factor data and assumptions.
- **API quality:** strong consistent scikit-learn style.
- **Extensibility:** excellent for research pipelines and controlled model comparison.
- **Commercial implications:** BSD-3-Clause favorable; inspect all optional solver/dependency licenses.
- **Atlas integration complexity:** 3/5.
- **Atlas fit:** **4/5** for research validation and advanced portfolio analysis.
- **Recommended usage:** **Monitor/adopt after a focused spike**; likely stronger than PyPortfolioOpt for validated quantitative research, but not needed for the first read-only slice.

### 2.4 Quant research and backtesting

#### vectorbt Community Edition

- **GitHub:** https://github.com/polakowo/vectorbt
- **License:** repository README states Apache 2.0 with Commons Clause. The Commons Clause restricts selling products/services primarily consisting of the software; optional dependencies may have more restrictive licenses. This is **not equivalent to plain Apache-2.0**.
- **Language:** Python with NumPy/pandas/Numba and optional Rust engine.
- **Maturity:** technically mature/high-performance community edition; separate VectorBT PRO is private/paid.
- **Strengths:** vectorized parameter sweeps, portfolio analytics, indicators, walk-forward tooling, interactive analysis, fast experimentation.
- **Weaknesses:** Commons Clause commercial restriction, research/backtest semantics not suitable as an authority, risk of overfitting/data leakage, float/pandas boundary, overlap with no current Atlas requirement.
- **Data dependencies:** caller/provider data; examples use Yahoo data.
- **API quality:** productive research API.
- **Extensibility:** high for research, less appropriate for constrained production domain services.
- **Commercial implications:** license must be reviewed by counsel before use in any commercial Atlas product/service; do not assume “Apache” in the name means unrestricted commercial use.
- **Atlas integration complexity:** 3/5.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** avoid as an initial dependency; use only in an isolated non-production research environment after license review.

#### Backtrader

- **GitHub:** https://github.com/mementum/backtrader
- **License:** verify current repository license before adoption; the project is widely used but its maintenance/release cadence and dependency age require scrutiny.
- **Language:** Python.
- **Maturity:** historically mature event-driven backtesting framework, but repository activity and modern Python compatibility should be verified at pin time.
- **Strengths:** event-driven simulation, feeds, commissions, slippage, calendars, indicators, analyzers, broker simulation.
- **Weaknesses:** older architecture/dependency assumptions, possible maintenance risk, trading/execution-oriented surface outside current Atlas scope, no built-in data truth or suitability.
- **Data dependencies:** caller feeds and broker/data adapters.
- **Atlas integration complexity:** 3/5.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** monitor only; do not adopt initially.

#### Zipline-compatible projects

- **Candidates:** Zipline Reloaded and related forks should be evaluated only against current Python 3.12, pandas, calendar, corporate-action, and maintenance requirements.
- **Maturity:** original Zipline ecosystem has historical importance but fragmented maintenance and operational friction.
- **Atlas fit:** **2/5**.
- **Recommended usage:** avoid initial adoption. A backtesting engine is not needed before Atlas has canonical valuations, transactions, corporate actions, and leakage-safe datasets.

#### QuantConnect LEAN

- **GitHub:** https://github.com/QuantConnect/Lean
- **License:** Apache-2.0 according to the repository license result.
- **Language:** C# with Python support.
- **Maturity:** professional-caliber event-driven engine with broad asset-class and live-trading infrastructure.
- **Strengths:** serious event model, modular components, multi-asset support, research/backtest/live architecture, commercial-friendly core license.
- **Weaknesses:** massive integration footprint, .NET/runtime/container requirements, strong trading/execution orientation, data/QuantConnect ecosystem coupling, unnecessary for Atlas’s no-execution phase.
- **Data dependencies:** caller/QuantConnect data sources; live and alternative data terms are separate.
- **Commercial implications:** Apache-2.0 code is favorable; data and QuantConnect services are separate.
- **Atlas integration complexity:** 5/5.
- **Atlas fit:** **2.5/5** now; higher only if Atlas later builds a serious strategy-research product.
- **Recommended usage:** monitor; do not embed initially.

### 2.5 Financial mathematics

#### QuantLib

- **GitHub:** https://github.com/lballabio/QuantLib
- **Bindings:** https://github.com/lballabio/QuantLib-SWIG
- **License:** QuantLib describes itself as non-copylefted, OSI-certified open-source software; verify the exact binding/package license at adoption.
- **Language:** C++ core with SWIG bindings including Python.
- **Maturity:** very mature, comprehensive quantitative-finance framework with long-standing community and documentation.
- **Strengths:** interest-rate curves, bonds, derivatives, calendars, term structures, pricing, risk, cash flows.
- **Weaknesses:** C++ build/binding complexity, broad API, not designed for Atlas’s basic equity portfolio ledger, numerical semantics must be wrapped and tested.
- **Data dependencies:** caller supplies curves, quotes, conventions, and market data.
- **Commercial implications:** generally favorable non-copyleft posture; review SWIG/package/transitive licenses.
- **Atlas integration complexity:** 4/5.
- **Atlas fit:** **3/5** now; **4/5** for fixed income/derivatives later.
- **Recommended usage:** keep as a future specialist dependency; do not add for basic equity recommendations.

### 2.6 Fundamental/company data

#### EdgarTools

- **GitHub:** https://github.com/dgunning/edgartools
- **License:** MIT according to repository and project materials.
- **Language:** Python.
- **Maturity:** active focused project; repository describes 1,000+ tests and typed objects for 20+ SEC forms, but production adoption should still pin and test versions.
- **Strengths:** SEC filings, standardized financial statements, XBRL facts, 13F, insider Forms 3/4/5, filing text extraction, ticker/CIK lookup, AI/MCP support, rate-limit awareness, direct EDGAR access.
- **Weaknesses:** maintained by a small project team according to its own README, SEC formats/taxonomies evolve, output must be bounded before entering Atlas, no market prices or portfolio suitability.
- **Data dependencies:** SEC EDGAR; SEC identity/User-Agent and rate-limit rules apply.
- **API quality:** clean Python object model and DataFrame exports; suitable behind an Atlas adapter.
- **Extensibility:** good for adding bounded filing/fact extractors.
- **Commercial implications:** MIT code is permissive; SEC data, filing content, and derived-data use still require terms/privacy review.
- **Atlas integration complexity:** 2.5/5.
- **Atlas fit:** **4/5**.
- **Recommended usage:** **Best initial new candidate**, but only as a parser/provider helper under existing `SecAdapter` contracts. Do not expose EdgarTools objects/raw filings directly to agents or UI.

#### SEC direct API/current adapter

- **Existing Atlas path:** `services/rules-service/app/market_intelligence/adapters.py` (`SecAdapter`) and contracts.
- **Assessment:** Atlas already has a safe, bounded SEC integration. This is the default choice before adding EdgarTools.
- **Recommendation:** first compare EdgarTools against the existing adapter on fixtures and operational needs. Adding it is justified only if it materially reduces parser code or adds required filing types without weakening controls.

#### SEC-API.io Python client

- **GitHub:** https://github.com/janlukasschroeder/sec-api-python
- **License/data model:** hosted API/client; commercial subscription and API terms are separate from any client license.
- **Strengths:** query/search API and normalized hosted responses.
- **Weaknesses:** paid dependency, vendor lock-in, credential/availability/cost risk, unnecessary while SEC direct access plus EdgarTools are available.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** avoid initially; consider only if direct EDGAR operations become an established bottleneck.

### 2.7 Market data

#### Existing Finnhub/SEC adapters

- **Existing Atlas paths:** `services/rules-service/app/market_intelligence/adapters.py`, `contracts.py`, `controls.py`.
- **Assessment:** reuse. The repository already has a provider-neutral interface, bounded records, source URLs, freshness, rate pacing, cache, retries, normalized failures, and synthetic tests.
- **Recommendation:** add providers only when a specific coverage/licensing gap is demonstrated. Provider licensing and market-data redistribution terms are separate from adapter-library licenses.

#### yfinance

- **GitHub:** https://github.com/ranaroussi/yfinance
- **License:** Apache according to repository README.
- **Language:** Python.
- **Maturity:** popular and actively used community library.
- **Strengths:** broad convenient historical/current Yahoo Finance access, options/news/search helpers, easy prototyping.
- **Weaknesses:** unofficial/public APIs, personal-use/research/education warning, Yahoo data terms, unstable endpoints, no contractual SLA, no provenance guarantee suitable for financial authority.
- **Data dependencies:** Yahoo Finance public endpoints and terms.
- **API quality:** convenient but unofficial and provider-dependent.
- **Extensibility:** useful for research adapters, not canonical production data.
- **Commercial implications:** Apache code does not grant rights to Yahoo data. Treat production/commercial use as legally constrained until data terms are approved.
- **Atlas integration complexity:** 2/5.
- **Atlas fit:** **2/5**.
- **Recommended usage:** local research/backtesting fixture acquisition only, never as default Atlas provider or recommendation evidence.

#### pandas-datareader / fredapi

- **pandas-datareader:** https://github.com/pydata/pandas-datareader  
- **fredapi:** https://github.com/mortada/fredapi
- **License:** verify the exact release licenses before adoption; both are thin clients, not data licenses.
- **Role:** FRED/ALFRED macroeconomic retrieval. `fredapi` specifically documents point-in-time/vintage retrieval, which is valuable for avoiding revised-data leakage.
- **Strengths:** simple API, macro series, ALFRED vintage awareness.
- **Weaknesses:** FRED API key/terms, sparse maintenance relative to core Atlas, raw series need normalization, revisions and release dates need explicit evidence modeling.
- **Atlas fit:** **3.5/5** for a later macro adapter.
- **Recommended usage:** monitor/adapt behind provider-neutral macro contracts; do not add until macro context is in scope.

### 2.8 News, sentiment, and transcript processing

#### FinBERT

- **GitHub:** https://github.com/ProsusAI/finBERT
- **License:** verify the repository and Hugging Face model artifact license separately before deployment; the repository and model/dataset obligations are not interchangeable.
- **Language:** Python/PyTorch-era BERT implementation.
- **Maturity:** influential research model; repository README notes reliance on the older `pytorch_pretrained_bert` implementation and a planned migration, so maintenance/modernization is a concern.
- **Strengths:** finance-domain sentiment classification, well-known baseline, local inference possibility.
- **Weaknesses:** old dependency stack, sentiment is weak evidence, dataset/model license and provenance complexity, domain drift, no source retrieval or truth verification.
- **Data dependencies:** Financial PhraseBank and training corpus references; Reuters TRC2 subset is not public according to README.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** monitor; if used, run as a non-authoritative feature with calibration, source linkage, and model/version metadata.

#### News aggregation/transcript projects

No single open-source news/transcript project was approved for the initial stack. News rights, transcript redistribution, publisher terms, and model training/data licenses are more consequential than NLP package popularity. Atlas should reuse existing `CompanyNewsItem`/`MarketNewsItem` contracts and add providers only after rights and source freshness are established.

### 2.9 RAG/search

#### pgvector

- **GitHub:** https://github.com/pgvector/pgvector
- **License:** Apache-2.0 according to repository materials.
- **Architecture:** PostgreSQL extension; exact and approximate vector search, metadata/SQL joins, ACID/PITR inherited from PostgreSQL.
- **Maturity:** mature and actively maintained.
- **Strengths:** one datastore for owner-scoped relational records and embeddings, SQL filtering/joins, exact search option, straightforward future PostgreSQL path.
- **Weaknesses:** requires PostgreSQL (current local setup is SQLite), extension operations/migrations, embeddings still require a model/provider, not a substitute for keyword/full-text search or evidence policy.
- **Atlas fit:** **4/5** after PostgreSQL adoption; **1.5/5** immediately.
- **Recommended usage:** preferred future vector layer; do not add while local SQLite remains the approved deployment.

#### Qdrant

- **GitHub:** https://github.com/qdrant/qdrant
- **License:** Apache-2.0.
- **Architecture:** Rust vector database/service with REST/gRPC, filtering, hybrid search, multitenancy, replication, and local/edge options.
- **Maturity:** mature production-oriented vector service.
- **Strengths:** excellent vector filtering/search, dedicated performance, self-hosted/cloud/edge choices.
- **Weaknesses:** second datastore, ownership synchronization, retention/deletion duplication, network service/security operations, unnecessary for Atlas’s current scale.
- **Atlas fit:** **3/5**.
- **Recommended usage:** monitor; select only if pgvector cannot meet scale/latency/isolation requirements.

#### Weaviate

- **GitHub:** https://github.com/weaviate/weaviate
- **License:** BSD 3-Clause according to repository materials.
- **Architecture:** Go cloud-native vector database with hybrid search, vectorizers, reranking, GraphQL/REST/gRPC, RBAC/multitenancy.
- **Maturity:** mature product with broad integrations.
- **Strengths:** integrated vectorization/hybrid/RAG features, rich API and operational features.
- **Weaknesses:** second datastore, built-in generative/vectorizer integrations may increase data leakage/provider coupling, overkill for single-user Atlas, more operational surface.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** monitor only.

#### OpenSearch

- **GitHub:** https://github.com/opensearch-project/OpenSearch
- **License:** Apache-2.0 according to repository materials.
- **Architecture:** distributed REST search/analytics engine with vector capabilities.
- **Maturity:** mature large-scale search ecosystem.
- **Strengths:** keyword/full-text, logs/observability, filters, vector search, operational tooling.
- **Weaknesses:** very large operational footprint, not a natural financial-record store, second datastore, query/retention/security complexity.
- **Atlas fit:** **2.5/5**.
- **Recommended usage:** consider only if Atlas later needs broad full-text research/archive search at scale.

#### Elasticsearch

- **GitHub:** https://github.com/elastic/elasticsearch
- **License:** current repository uses Elastic licensing/source-available terms rather than a simple permissive Apache-only assumption; exact release terms must be reviewed.
- **Maturity:** extremely mature technical platform.
- **Strengths:** excellent full-text, analytics, vector search, ecosystem.
- **Weaknesses:** license complexity/change history, operational size, vendor coupling, unnecessary duplicate persistence.
- **Atlas fit:** **2/5**.
- **Recommended usage:** avoid as initial dependency; prefer pgvector/PostgreSQL or OpenSearch if the use case later requires a separate search system.

### 2.10 Agent orchestration

#### LangGraph

- **GitHub:** https://github.com/langchain-ai/langgraph
- **License:** MIT according to repository materials.
- **Language:** Python and JavaScript ecosystem.
- **Maturity:** high adoption and active project; low-level stateful graph orchestration with durable execution and human-in-the-loop patterns.
- **Strengths:** durable/stateful workflows, branching/subgraphs, persistence, human approval, useful for long-running research runs.
- **Weaknesses:** framework lock-in/complexity, surrounding LangChain ecosystem optional but tempting, does not solve financial correctness, provenance, evaluation, or policy authority.
- **Atlas integration complexity:** 3/5.
- **Atlas fit:** **3/5** if durable multi-agent workflows become necessary; **1.5/5** now.
- **Recommended usage:** monitor; evaluate only after Atlas’s own agent contracts are specified.

#### PydanticAI

- **GitHub:** https://github.com/pydantic/pydantic-ai
- **License:** MIT according to current ecosystem references; verify exact release.
- **Language:** Python.
- **Maturity:** active modern SDK built around typed agents, tools, structured output, dependency injection, multiple model providers, OpenTelemetry, and evaluation/durable-execution integrations.
- **Strengths:** fits existing Pydantic contracts, typed tool boundaries, structured outputs, provider abstraction, easy incremental adoption.
- **Weaknesses:** fast-moving ecosystem, model/provider abstractions still require governance, does not replace Atlas policy/run ledger, durable integrations add operational dependencies.
- **Atlas integration complexity:** 2.5/5.
- **Atlas fit:** **3.5/5** for a future typed agent layer.
- **Recommended usage:** preferred framework candidate if Atlas outgrows its current orchestrator, but do not adopt before a framework decision and agent contract ADR.

## 3. License matrix

| Project | License observed/reported | Commercial posture | Atlas decision |
|---|---|---|---|
| FinceptTerminal | AGPL-3.0-or-later; current docs say no paid exemption for repository | Strong copyleft; commercial/institutional use directed to separate Enterprise product; trademarks/trade dress reserved | Avoid embedding/forking |
| OpenBB ODP | AGPL; FAQ describes commercial-license option | Proprietary product/service use may require commercial license or careful unmodified/service boundary | Legal review; monitor/sidecar only |
| FinRobot | Apache-2.0 reported | Generally permissive code; audit model/data/provider licenses | Reuse patterns, not platform |
| PyPortfolioOpt | Verify current release; commonly MIT | Likely permissive, but release audit required | Adapt behind interface |
| Riskfolio-Lib | BSD 3-Clause | Permissive; audit solvers/transitives | Preferred advanced optimizer candidate |
| skfolio | BSD 3-Clause | Permissive; audit optional solvers/transitives | Monitor/adopt after spike |
| vectorbt Community | Apache 2.0 with Commons Clause | Commercial restriction on selling products/services primarily consisting of software; optional deps vary | Avoid initial production dependency |
| Backtrader | Verify current repository/release | Must audit due age and maintenance | Monitor only |
| Zipline forks | Varies by fork | Must audit fork and dependencies | Avoid initial adoption |
| QuantConnect LEAN | Apache-2.0 | Permissive core; data/services separate | Monitor, not initial |
| QuantLib | Non-copyleft/OSI open source; verify bindings | Generally favorable; audit bindings/transitives | Future specialist dependency |
| EdgarTools | MIT | Permissive code; SEC data/terms separate | Best new candidate, adapter only |
| yfinance | Apache code; Yahoo data terms separate | Code license does not grant Yahoo data rights; README warns personal/research use | Research only |
| fredapi | Verify release license | Data/API key terms separate | Future macro adapter |
| FinBERT | Repository/model/dataset licenses must be separately verified | Model/data obligations may constrain redistribution/use | Monitor/isolated feature |
| pgvector | Apache-2.0 | Permissive extension; PostgreSQL deployment required | Future preferred vector layer |
| Qdrant | Apache-2.0 | Permissive server; hosted terms separate | Monitor |
| Weaviate | BSD 3-Clause | Permissive core; modules/services/data terms separate | Monitor |
| OpenSearch | Apache-2.0 | Permissive core; plugins/services separate | Later search option |
| Elasticsearch | Current source-available/Elastic terms; not simple Apache assumption | Legal review required | Avoid initial adoption |
| LangGraph | MIT | Permissive library; hosted LangSmith/services separate | Monitor |
| PydanticAI | MIT reported; verify release | Permissive library; model/provider terms separate | Preferred future agent candidate |

**License rules for Atlas:**

- Code license is not data license.
- Library license is not hosted-service/API license.
- Model license is not dataset/license or training-data permission.
- Optional solvers, plugins, model weights, fonts, and provider adapters require their own inventory.
- AGPL/source-available/Commons-Clause dependencies are not automatically disallowed, but they require explicit legal/product architecture decisions and should not enter the minimum stack by default.

## 4. Technical maturity matrix

Scores: 1 = weak/uncertain for Atlas, 5 = strong. “Maturity” is engineering/project maturity, not suitability as an investment authority.

| Candidate | Engineering maturity | Maintenance signal | API/extensibility | Data-quality fit | Atlas fit |
|---|---:|---:|---:|---:|---:|
| FinceptTerminal | 4 | 4 | 2 | 2 | 1.5 |
| OpenBB | 4 | 4 | 4 | 3 | 2.5 |
| FinRobot | 3 | 4 | 3 | 2 | 2.5 |
| PyPortfolioOpt | 4 | 4 | 4 | 3 | 3.5 |
| Riskfolio-Lib | 4 | 4 | 4 | 3 | 4.0 |
| skfolio | 4 | 4 | 5 | 4 | 4.0 |
| vectorbt | 4 | 4 | 4 | 2 | 2.5 |
| Backtrader | 3 | 2 | 3 | 2 | 2.5 |
| Zipline ecosystem | 2 | 2 | 2 | 2 | 2.0 |
| LEAN | 5 | 5 | 5 | 3 | 2.5 |
| QuantLib | 5 | 5 | 4 | 4 | 3.0 |
| EdgarTools | 4 | 4 | 4 | 4 | 4.0 |
| yfinance | 4 | 4 | 3 | 1 | 2.0 |
| fredapi | 3 | 3 | 3 | 4 | 3.5 |
| FinBERT | 3 | 2 | 2 | 2 | 2.5 |
| pgvector | 5 | 5 | 4 | 5 | 4.0 later |
| Qdrant | 5 | 5 | 5 | 4 | 3.0 |
| Weaviate | 5 | 5 | 5 | 4 | 2.5 |
| OpenSearch | 5 | 5 | 5 | 4 | 2.5 |
| Elasticsearch | 5 | 5 | 5 | 4 | 2.0 |
| LangGraph | 4 | 5 | 4 | 2 | 3.0 later |
| PydanticAI | 4 | 5 | 5 | 3 | 3.5 later |

## 5. Atlas fit score and decision summary

### Adopt/retain now

- **Atlas Market Intelligence contracts/adapters:** fit **5/5**. Already integrated, provider-neutral, provenance-aware, and tested.
- **Existing SEC adapter:** fit **5/5** for current scope. Do not replace it casually.
- **Existing Pydantic contracts:** fit **5/5**. They align with strict evidence and financial boundaries.

### First new dependency candidate

- **EdgarTools:** fit **4/5**. Run a focused spike comparing it with the existing `SecAdapter`. Add only if it reduces custom parsing or supplies needed filing forms while all outputs remain normalized into Atlas contracts.

### Later quantitative candidates

- **Riskfolio-Lib:** fit **4/5** for advanced portfolio risk/optimization.
- **skfolio:** fit **4/5** for leakage-aware research, factor models, validation, and portfolio optimization.
- **PyPortfolioOpt:** fit **3.5/5** for simpler allocation prototypes and explainable baseline optimization.
- **QuantLib:** fit **3/5** now; **4/5** for fixed income/derivatives.

### Do not use as initial production dependencies

- FinceptTerminal, OpenBB, FinRobot, vectorbt, Backtrader, Zipline forks, LEAN, yfinance, FinBERT, Qdrant, Weaviate, OpenSearch, Elasticsearch, LangGraph, PydanticAI.

This does not mean these projects are poor software. It means they either overlap Atlas’s core architecture, carry legal/data/operational costs, or solve a later problem.

## 6. Recommended stack

### Initial Atlas-owned core

1. **Rules Service + Finlynq** — canonical owner/account/financial authority.
2. **SQLAlchemy + Alembic** — existing persistence/migration conventions.
3. **Pydantic** — existing strict normalized contracts.
4. **Existing Market Intelligence adapters** — Finnhub and SEC direct adapter with bounded controls.
5. **Existing recommendation/decision/outcome substrate** — immutable, owner-scoped, idempotent user-control loop.
6. **Existing `httpx`/standard-library adapter controls** — avoid adding a generic integration platform.
7. **PostgreSQL + pgvector only when the deployment decision moves beyond SQLite** — not for the first local slice.

### First optional additions after validation

8. **EdgarTools** — optional SEC parser/helper behind `SecAdapter`.
9. **PyPortfolioOpt** — optional transparent baseline optimizer behind an Atlas service interface.
10. **Riskfolio-Lib or skfolio** — later, not both initially; select after a portfolio-analytics spike. Prefer Riskfolio-Lib for broad convex risk measures; prefer skfolio for leakage-aware model-selection/research workflows.
11. **QuantLib** — only when fixed income/derivatives or specialized financial mathematics is in scope.

### Explicitly deferred

- RAG/vector database until evidence retrieval volume and PostgreSQL deployment justify it.
- Agent framework until Atlas’s current orchestration boundary demonstrably fails requirements.
- Backtesting engine until canonical historical data, corporate actions, transaction costs, taxes, and leakage controls exist.
- Sentiment model until source rights, calibration, and measurable incremental value are established.
- Macro client until macro context is an approved product slice.

## 7. Projects to avoid

### Avoid as embedded foundations

1. **FinceptTerminal** — current AGPL-3.0-or-later repository terms, no paid repository exemption, Enterprise separation, trademark/trade-dress restrictions, and application overlap.
2. **OpenBB ODP** — AGPL/commercial-license complexity and overlap with Atlas’s existing provider boundary.
3. **FinRobot** — large overlapping application/agent runtime and provider/LLM coupling.
4. **vectorbt Community** — Commons Clause commercial restriction and research-only role.
5. **yfinance** — unofficial Yahoo data with personal/research-use warnings.
6. **Elasticsearch** — source-available/license complexity plus unnecessary operational duplication.
7. **A second vector database now** — Qdrant/Weaviate/OpenSearch add ownership, retention, and operations before Atlas needs them.
8. **A backtesting engine now** — no canonical investment history exists yet.

### Avoid conceptually

- Any library that supplies a “BUY” conclusion without explainable inputs.
- Any model that turns analyst sentiment into suitability.
- Any package that writes directly to canonical financial tables from agent code.
- Any provider that cannot disclose source, timestamp, freshness, and data rights.

## 8. Projects to monitor

- **skfolio** — promising integrated portfolio modeling and leakage-aware validation.
- **Riskfolio-Lib** — advanced risk measures and constrained optimization.
- **PydanticAI** — likely fit if typed agent workflows outgrow the current orchestrator.
- **LangGraph** — useful if durable long-running graph workflows become real.
- **QuantLib** — valuable when fixed income/derivatives arrive.
- **Qdrant** — dedicated vector option if PostgreSQL vectors become insufficient.
- **OpenSearch** — possible future full-text/research archive search platform.
- **fredapi/ALFRED ecosystem** — future point-in-time macro evidence.
- **FinBERT and newer finance NLP models** — only after modern dependency/license/calibration review.
- **OpenBB** — monitor licensing and architecture changes; do not depend by default.
- **FinceptTerminal** — monitor only for UX/research ideas and licensing changes, not code adoption.

## 9. Integration architecture

### 9.1 Dependency placement

```text
External data providers / open-source helpers
  ├─ Finnhub, SEC EDGAR, optional EdgarTools, optional FRED
  ├─ optional price-history provider for research only
  └─ optional optimizer/math libraries
              │
              ▼
Atlas adapter boundary
  ├─ provider credentials stay server-side
  ├─ rate limits, retries, cache, and usage ledger
  ├─ source URL and retrieved/published/observed timestamps
  ├─ freshness and market-session classification
  ├─ bounded Pydantic normalized records
  ├─ sanitized failures and coverage omissions
  └─ synthetic transport tests; no raw external payloads downstream
              │
              ▼
Atlas canonical investment boundary
  ├─ security master
  ├─ transactions/lots
  ├─ position and valuation snapshots
  ├─ portfolio snapshot hash
  ├─ deterministic performance/allocation/risk/fit analytics
  └─ suitability/policy gates
              │
              ▼
Atlas intelligence boundary
  ├─ specialist agents receive only validated snapshots/evidence
  ├─ agents request calculations; they do not calculate authority
  ├─ model output is typed, bounded, and provenance-linked
  └─ recommendation synthesizer cannot bypass policy gates
              │
              ▼
Existing Atlas decision boundary
  ├─ immutable recommendation repository
  ├─ user accept/reject/defer/watch decision
  ├─ append-only decision history/audit
  └─ outcome evaluation and calibration
```

### 9.2 Adapter rules

Every external/open-source component must be behind an Atlas-owned interface that:

- accepts only canonical, bounded inputs;
- returns only Atlas contracts;
- records provider/library/model/calculation versions;
- never leaks credentials, raw payloads, or untrusted text;
- exposes unavailable/stale/partial states explicitly;
- is deterministic under synthetic fixtures;
- can be replaced without changing domain or UI contracts;
- cannot write canonical records unless called by an authorized application service.

### 9.3 Open-source numerical library boundary

Optimizers and research libraries receive a frozen `PortfolioAnalyticsInput` containing exact canonical values converted at a controlled boundary. Their output is an untrusted calculation result until Atlas validates:

- constraints and weight totals;
- finite values and bounds;
- input/output asset identity;
- objective/risk model/version;
- data window and freshness;
- turnover, tax, liquidity, and user-policy constraints;
- reproducibility and solver status.

The library never emits a final user recommendation by itself.

## 10. Licensing and commercial risks

1. **AGPL network/derivative risk:** FinceptTerminal and OpenBB can create source-disclosure or commercial-license obligations depending on linking, modification, distribution, and network-service architecture. Obtain counsel’s written position before adoption.
2. **Source-available confusion:** Elasticsearch and other projects can appear “open source” while current terms differ from OSI permissive licenses. Record exact version/license files in an attribution inventory.
3. **Commons Clause:** vectorbt Community is not plain Apache-2.0 for commercial product use. Avoid assuming permissive rights.
4. **Data rights:** SEC, Yahoo, Finnhub, FRED, news publishers, transcripts, and market-data providers each have separate terms, redistribution limits, attribution requirements, and sometimes delayed/restricted use.
5. **Model/data licenses:** FinBERT weights, training datasets, transcript corpora, and embeddings may have distinct licenses and privacy/redistribution obligations.
6. **Optional dependencies:** solvers such as MOSEK/GUROBI, TA-Lib, Rust/C++ bindings, model packages, and provider plugins require separate inventory.
7. **Trademark/trade dress:** Fincept specifically reserves marks and trade dress; do not replicate its product identity or market an Atlas fork as a terminal clone.
8. **Hosted services:** managed Qdrant/Weaviate/OpenBB/Elastic/QuantConnect offerings carry contract, data-location, retention, SLA, and cost terms beyond OSS licenses.
9. **Attribution/SBOM:** maintain an automated dependency/SBOM and license notice process before external distribution.
10. **Financial output disclaimer:** open-source licenses do not transfer responsibility for Atlas recommendation quality, suitability, regulatory status, or user losses.
11. **Version pinning:** record exact commit/release, license text, transitive dependencies, test evidence, and upgrade policy for every adopted component.

## 11. Recommended minimum viable dependency set

For the first Investment Intelligence implementation slice, the minimum set should be:

### Required

- Existing Python 3.12 Rules Service environment.
- Existing `pydantic`, `sqlalchemy`, `alembic`, `httpx`, and current project dependencies.
- Existing Finnhub/SEC adapter layer and synthetic provider transports.
- Existing Atlas recommendation/decision/history/outcome modules.
- Existing PostgreSQL-compatible design discipline, even if local SQLite remains active.

### Optional after focused spike

- **EdgarTools** for SEC filing/XBRL parsing, only behind the existing `SecAdapter` contract.

### Not required for MVP

- OpenBB.
- FinceptTerminal.
- FinRobot.
- PyPortfolioOpt/Riskfolio-Lib/skfolio.
- VectorBT/Backtrader/Zipline/LEAN.
- QuantLib.
- FinBERT.
- Qdrant/Weaviate/OpenSearch/Elasticsearch.
- LangGraph/PydanticAI.
- A new macro/news/transcript framework.

The first MVP should establish canonical investment data and deterministic portfolio analytics before adding sophisticated optimization, RAG, quant research, or multi-agent orchestration.

## 12. Build vs Buy vs Reuse

### Atlas should build itself

These are the product-specific authorities and should remain Atlas-owned:

- Canonical security identity mapping and source reconciliation policy.
- Investment transaction/lot/position/valuation history model.
- Exact Decimal financial semantics and rounding policy.
- Portfolio snapshot/hash and as-of semantics.
- TWR/MWR/performance definitions and fixtures.
- Allocation, concentration, liquidity, fee, risk, and portfolio-fit calculations as governed Atlas services.
- Suitability/risk-capacity/goal/tax/restriction policy gates.
- Evidence coverage, freshness, conflict, abstention, and confidence policy.
- BUY/ADD/HOLD/REDUCE/SELL/WATCH recommendation contract and ranking policy.
- User decision, approval, journal, audit, and outcome/calibration semantics.
- Agent tool permissions, run ledger, model/version traceability, and evaluation suite.
- Privacy, retention, ownership isolation, and failure-safe behavior.
- Final UI interpretation and user-control workflow.

### Atlas should delegate to open-source projects

Use open-source components for bounded general-purpose capabilities:

- SEC/XBRL parsing: EdgarTools or existing direct SEC adapter.
- Numerical optimization: Riskfolio-Lib, skfolio, or PyPortfolioOpt behind a service adapter.
- Specialized quantitative mathematics: QuantLib when instrument scope justifies it.
- Macro retrieval: a small FRED/ALFRED client behind normalized contracts.
- Vector similarity: pgvector after PostgreSQL deployment is approved.
- Agent typed-loop mechanics: PydanticAI only if Atlas’s current orchestrator is insufficient.
- Durable graph orchestration: LangGraph only if long-running stateful agent runs are proven necessary.
- General numerical primitives: established NumPy/SciPy/pandas ecosystem, with controlled conversion boundaries.

### Atlas should not buy/reuse blindly

- Financial terminal applications.
- Unofficial market-data scrapers as authoritative providers.
- Black-box stock-picking or price-prediction systems.
- Hosted RAG/agent services that receive sensitive portfolio data without explicit privacy/retention review.
- Backtesting platforms before canonical historical data exists.
- Provider plugins whose data rights cannot be documented.

## 13. Recommended adoption sequence

1. **No dependency change:** implement the canonical investment-data design and acceptance criteria using existing Atlas contracts.
2. **SEC parser spike:** compare EdgarTools with `SecAdapter` using synthetic/approved fixtures; record license, performance, coverage, and output-boundary findings.
3. **Portfolio analytics spike:** implement a small Atlas-owned baseline and compare PyPortfolioOpt, Riskfolio-Lib, and skfolio on frozen fixtures; select at most one.
4. **Provider expansion review:** identify specific quote/history/corporate-action/macro gaps; research providers and terms before adding adapters.
5. **PostgreSQL decision:** if retrieval/history scale requires it, migrate the deployment decision and evaluate pgvector.
6. **Agent framework decision:** only after structured Atlas agent contracts and run/evaluation requirements are written; evaluate PydanticAI before LangGraph for typed incremental integration.
7. **Backtesting/advanced math:** only when user-facing quantitative signals have a defined historical dataset, leakage controls, calibration, and outcome policy.

## Sources checked

- Fincept repository license: https://github.com/Fincept-Corporation/FinceptTerminal/blob/main/LICENSE
- Fincept current commercial/licensing document: https://github.com/Fincept-Corporation/FinceptTerminal/blob/main/docs/COMMERCIAL_LICENSE.md
- OpenBB repository: https://github.com/OpenBB-finance/OpenBB
- OpenBB licensing FAQ: https://docs.openbb.co/odp/python/faqs/license
- FinRobot: https://github.com/AI4Finance-Foundation/FinRobot
- PyPortfolioOpt: https://github.com/PyPortfolio/PyPortfolioOpt
- Riskfolio-Lib: https://github.com/dcajasn/Riskfolio-Lib
- skfolio: https://github.com/skfolio/skfolio
- vectorbt: https://github.com/polakowo/vectorbt
- Backtrader: https://github.com/mementum/backtrader
- QuantConnect LEAN: https://github.com/QuantConnect/Lean
- QuantLib: https://github.com/lballabio/QuantLib
- EdgarTools: https://github.com/dgunning/edgartools
- yfinance: https://github.com/ranaroussi/yfinance
- FinBERT: https://github.com/ProsusAI/finBERT
- pgvector: https://github.com/pgvector/pgvector
- Qdrant: https://github.com/qdrant/qdrant
- Weaviate: https://github.com/weaviate/weaviate
- OpenSearch: https://github.com/opensearch-project/OpenSearch
- Elasticsearch: https://github.com/elastic/elasticsearch
- LangGraph: https://github.com/langchain-ai/langgraph
- PydanticAI: https://github.com/pydantic/pydantic-ai
- fredapi: https://github.com/mortada/fredapi

### Recommended stack

Initially adopt/retain:

1. Atlas’s existing Rules Service + Finlynq architecture.
2. Existing Pydantic/SQLAlchemy/Alembic/httpx stack.
3. Existing Finnhub and SEC Market Intelligence adapters/contracts.
4. Existing immutable recommendation, decision journal, history, and outcome systems.
5. **EdgarTools only after a focused compatibility/license spike**, as an optional SEC parsing helper.
6. **One** later portfolio-analysis library—preferably Riskfolio-Lib or skfolio after fixture-based evaluation; PyPortfolioOpt is the simpler baseline option.
7. **pgvector later**, only with an approved PostgreSQL deployment.

Do not initially adopt FinceptTerminal, OpenBB, FinRobot, vectorbt, yfinance as production authority, a dedicated vector database, a backtesting engine, or an agent framework.

### Build vs Buy vs Reuse

- **Build:** Atlas’s canonical investment ledger, security identity, exact financial semantics, portfolio analytics contract, suitability/policy, recommendation authority, provenance, decisions, outcomes, privacy, and user-control experience.
- **Buy/use external services:** only approved market/news/macro data access where data rights, cost, freshness, and retention are explicit.
- **Reuse/adapt:** existing Atlas adapters and contracts first; EdgarTools for bounded SEC parsing; one validated optimizer/math library behind Atlas interfaces; pgvector only when PostgreSQL is justified; agent frameworks only when Atlas’s current orchestration demonstrably needs them.
