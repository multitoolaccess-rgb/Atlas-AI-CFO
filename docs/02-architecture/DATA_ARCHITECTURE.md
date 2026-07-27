# Atlas Data Architecture

**Version:** 1.0

## Purpose

Create a unified, historical, and explainable Financial Digital Twin—not merely a transaction store.

## Core model

Atlas models people, households, goals, income, expenses, assets, liabilities, accounts, transactions, investments, businesses, decisions, and opportunities.

## Data requirements

- Canonical identifiers and source provenance
- Ownership and household scope
- Effective dates and historical snapshots
- Currency and valuation timestamps
- Confidence and reconciliation status
- Consent, permissions, and retention controls

## Principal entities

- **User and household:** Identity, membership, roles, preferences, and risk profile.
- **Goal:** Target, date, priority, constraints, and probability.
- **Asset and liability:** Value, ownership, liquidity, tax treatment, and assumptions.
- **Account and transaction:** Institution, balance, activity, category, and confidence.
- **Investment:** Security, quantity, cost basis, allocation, risk, and tax attributes.
- **Business:** Ownership, operations, valuation, and forecasts.
- **Decision and recommendation:** Context, evidence, expected result, status, and outcome.
- **Opportunity:** Capital, upside, risk, effort, alignment, and confidence.

## History

Important states are append-only or versioned. Atlas preserves what was known, when it was known, and which source supplied it.

## AI memory

Derived memory stores preferences, decisions, outcomes, and behavior patterns. It never replaces canonical financial records.

## Principles

Accuracy, provenance, security, minimization, transparency, user control, and deterministic calculations for material financial facts.
