# INV-03 Portfolio Intelligence — Implementation Record

## Status

Implementation foundation complete; this record describes the bounded contract currently implemented. It is not a claim that the full future portfolio analytics roadmap is complete.

## Canonical authority

The projection consumes Atlas's existing `Account` and `Holding` records. It does not create a second portfolio ledger, mutate holdings, or infer historical transactions, lots, dividends, or brokerage state. Account ownership is enforced by selecting accounts whose `user_id` matches the requested owner; holdings outside those accounts are excluded.

## Implemented contract

`services/rules-service/app/investments/portfolio_intelligence.py` provides:

- `PortfolioPosition`, an owner-scoped position projection;
- `ExposureBucket`, a deterministic per-position exposure result;
- `PortfolioSnapshot`, a frozen snapshot with UTC `as_of`, source holding IDs, completeness, calculation version, and deterministic hash;
- `build_portfolio_snapshot`, which orders inputs deterministically and preserves missing values as unavailable;
- explicit `Completeness` and `CostBasisState` values.

The projection normalizes finite numeric values to canonical Decimal text. Missing quantity, value, symbol, or other unsupported input marks the snapshot partial rather than manufacturing a complete portfolio result. Missing cost basis remains `unknown`; it is never treated as zero. Market value percentages are unavailable when a complete denominator cannot be established.

## Identity and data quality

Security identity is delegated to the INV-02 provider-neutral identity primitive. A missing symbol is `unresolved`; an unknown instrument type is `unsupported`; neither is silently promoted to a valid equity. The current legacy Holding model does not provide authoritative currency for every holding, so the projection leaves position currency unknown rather than assuming USD. Current holdings are therefore not treated as historical investment truth.

## Temporal and provenance semantics

Every projected position carries the requested UTC snapshot `as_of` and the source holding ID. Snapshot ordering, schema version, calculation version, and canonical payload hashing make repeated projections reproducible for identical inputs. This slice does not persist snapshots or rewrite history; persistence and transaction/lot reconstruction remain future bounded work.

## Not implemented in this slice

The current implementation intentionally does not claim to provide:

- available cash reconstruction;
- transaction/lot-based cost basis;
- realized or unrealized return calculations;
- time-weighted or money-weighted returns;
- sector, geography, market-cap, factor, volatility, correlation, drawdown, beta, or liquidity analytics;
- portfolio-impact previews or new APIs;
- database migrations or external provider ingestion.

These capabilities require authoritative inputs and separate financial-correctness fixtures before implementation.

## Provider and dependency strategy

No new dependency was added. INV-02 models and normalization contracts are used directly; no provider is activated and no network call is required. External analytical libraries are not used in this slice, preserving replaceability and Atlas canonical authority.

## Testing and rollback

Focused tests cover owner isolation, deterministic hashing, empty/partial data, unresolved identity, unsupported instruments, missing cost basis, missing values, and timezone validation. Compilation and relevant existing portfolio/market/foundation tests are run before commit. The change is additive and rollback is straightforward: remove or feature-gate the projection and test without changing legacy tables or history.

## Safety boundary

This is read-only decision-support infrastructure. It adds no order, broker, transfer, money-movement, portfolio-mutation, or execution capability.
