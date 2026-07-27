# Atlas Agent Architecture

**Version:** 1.0

## Philosophy

Atlas uses specialized financial agents coordinated by an orchestrator. Deterministic financial calculations remain separate from probabilistic AI reasoning.

## System flow

Financial state → Orchestrator → Specialist agents → Decision engine → Recommendation engine → Approval and policy layer → Integrations.

## Orchestrator

Coordinates work, selects agents, merges results, resolves conflicts, maintains context, and produces a coherent explanation.

## Specialist agents

- **Wealth Agent:** Net worth, forecasts, retirement probability, and goals.
- **Investment Agent:** Allocation, diversification, performance, risk, fees, and tax-aware investing.
- **Tax Agent:** Estimated taxes, deductions, conversions, loss harvesting, and withdrawal planning.
- **Opportunity Agent:** Business, career, investment, real-estate, and income opportunities.
- **Risk Agent:** Concentration, liquidity, debt, insurance, emergency reserves, and unusual activity.
- **Life Agent:** Retirement, business launches, moves, property, and major purchases.

## Decision engine

Ranks options using financial impact, goal alignment, probability, risk, time, preferences, constraints, and confidence.

## Recommendation contract

Each recommendation includes summary, rationale, expected impact, confidence, risks, trade-offs, alternatives, evidence, assumptions, and expiration conditions.

## Execution layer

Starts read-only, progresses to explicit user approval, and may later execute within scoped, revocable policies. All material actions require permissions, audit history, and rollback guidance where possible.

## Memory

Atlas remembers goals, preferences, recommendations, decisions, outcomes, behavior patterns, and long-term trends.

## Explainability

Every output identifies why now, data used, assumptions made, and what would change the recommendation.
