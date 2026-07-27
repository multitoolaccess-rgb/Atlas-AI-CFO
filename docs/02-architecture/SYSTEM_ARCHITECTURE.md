# Atlas System Architecture

**Version:** 1.0  
**Status:** Foundational architecture

## Purpose

Define Atlas as a layered AI Financial Operating System.

## Principles

1. Separate financial truth from AI reasoning.
2. Make recommendations explainable.
3. Use specialized agents.
4. Establish trust before autonomy.
5. Give users ownership and control.

## Layers

1. **Ingestion:** Banks, brokerages, retirement accounts, credit, real estate, businesses, taxes, and user input.
2. **Canonical data:** Normalize, validate, reconcile, categorize, and preserve provenance.
3. **Financial intelligence:** Compute cash flow, wealth, risk, forecasts, and derived signals.
4. **Agent orchestration:** Coordinate specialized analysis.
5. **Decision and recommendation:** Rank actions and create user-facing explanations.
6. **Simulation:** Model retirement, business, property, investing, and purchases.
7. **Experience:** Mission Control, advisor, simulation lab, opportunities, and approvals.
8. **Execution:** Broker, bank, and workflow integrations behind permissions and audit controls.

## Current codebase mapping

Existing accounts, transactions, categories, and investments form the data foundation. Sankey, trend, and dashboard components become the visualization layer. Existing copilot, rules, and insight services evolve into orchestration and intelligence services.

## Deployment

- Next.js user experience
- API and background services
- Model gateway and agent orchestration
- Financial database, historical snapshots, decision journal, and retrieval memory
- Observability, audit, and policy enforcement

## Evolution

Financial dashboard → Proactive recommendations → Multi-agent CFO → Policy-governed financial operations.
