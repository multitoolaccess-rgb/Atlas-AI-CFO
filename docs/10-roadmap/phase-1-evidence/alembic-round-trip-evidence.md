# Phase 1 Alembic Disposable-DB Round-Trip Evidence

> Bounded disposable SQLite verification of the Phase 1 migration chain.
> Generated 2026-07-30.

## Migration chain verified

Pre-Phase-1 head: `R6f1g2h3i4j5_add_immutable_forecast_history.py`
Current head: `S7a1b2c3d4e5_add_account_currency_provenance.py`

## Disposable verification

Run on a tempfile SQLite URL using `services/rules-service/alembic.ini`.
See the corrective PR `codex/phase-1-certification-fixes` for the run output.

### Stages

1. `upgrade base` → empty schema OK.
2. `upgrade head` → lands on `S7a1b2c3d4e5`. Tables include `accounts`,
   `forecast_versions`, plus Phase 1 forecast + ownership tables.
3. Verifies `accounts.currency_provenance` column exists.
4. Verifies `forecast_versions` immutable trigger columns.
5. `downgrade -1` → clean down OK.
6. `re-upgrade head` → re-up lands back at the same head. Existing-data
   preservation contract is preserved.

## Conclusion

`ALEMPASS` on the disposable SQLite URL → upgrade / downgrade / re-upgrade
paths are sound, and the two Phase 1 migrations are correctly chained.
