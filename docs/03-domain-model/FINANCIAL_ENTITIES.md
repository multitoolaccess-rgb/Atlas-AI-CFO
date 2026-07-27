# Atlas Financial Entities

**Version:** 1.0  
**Status:** Foundational domain model

## Purpose

Define the entities in the user’s Financial Digital Twin.

## Entities

### User and household

Identity, age, location, family structure, membership, ownership, roles, preferences, and life context.

### Asset

Cash, investments, retirement accounts, real estate, businesses, and other property. Attributes include value, valuation date, ownership, liquidity, growth assumptions, risk, and tax treatment.

### Liability

Mortgages, loans, credit, and business debt. Attributes include balance, interest, payment, term, security, and tax treatment.

### Account

A source or container for balances, transactions, or holdings, linked to institution, owner, type, and permissions.

### Income and expense

Cash inflows and outflows with amount, recurrence, stability, category, source, and goal relevance.

### Transaction

A dated financial event with amount, currency, merchant, category, account, source, and classification confidence.

### Investment

A holding with security, quantity, cost basis, market value, allocation, risk, performance, and tax characteristics.

### Business

An entrepreneurial asset with ownership, revenue, expenses, profit, valuation, financing, and forecasts.

### Goal

A desired outcome with measurable target, timeline, priority, constraints, and probability.

### Decision

A first-class record of a question, context, options, analysis, recommendation, user action, and outcome.

### Opportunity

A possible investment, business, tax, career, income, or real-estate action with upside, risk, effort, and confidence.

## Design principle

Atlas stores facts plus context, intent, provenance, assumptions, and outcomes.
