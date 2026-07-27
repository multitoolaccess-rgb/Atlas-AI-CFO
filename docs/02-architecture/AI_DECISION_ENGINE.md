# Atlas AI Decision Engine

**Version:** 1.0

## Purpose

Convert financial information into ranked, explainable recommended actions.

## Pipeline

Financial data → Validated state → Agent analysis → Candidate actions → Scenario and impact calculation → Risk and policy checks → Ranking → Recommendation → Outcome learning.

## Inputs

Goals, current state, preferences, constraints, risk tolerance, market context, past decisions, and specialist-agent findings.

## Scoring dimensions

- Goal alignment
- Expected financial impact
- Downside and tail risk
- Confidence and data quality
- Complexity and reversibility
- Liquidity and time requirements
- Tax and legal implications
- Urgency

Scores are decision support, not a substitute for the underlying evidence.

## Priority order

1. Prevent catastrophic loss or fraud.
2. Protect solvency and liquidity.
3. Improve goal probability.
4. Create wealth.
5. Optimize costs and efficiency.

## Recommendation format

Title, action, why now, expected impact, risks, confidence, alternatives, evidence, assumptions, required approvals, and review date.

## Learning loop

Record the recommendation and prediction, observe the user’s decision and actual outcome, compare forecast with reality, and calibrate future recommendations without rewriting history.

## Autonomy

Observe → Recommend → Approve → Execute → Operate within explicit guardrails.

Material actions must pass permissions, suitability, policy, audit, and user-control checks.
