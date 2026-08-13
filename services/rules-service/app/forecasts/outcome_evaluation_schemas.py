"""Outcome-evaluation schema versioning for the Phase 3 slice.

Phase 3 Slice 1.  This module owns the canonical schema version literal
for outcome evaluation records, mirroring how
:mod:`app.forecasts.recommendation_schemas` owns
``DECISION_JOURNAL_SCHEMA_VERSION``.

The version literal is part of the persisted contract: it is stored on
every ``outcome_evaluations`` row and participates in the deterministic
row identity (via :func:`outcome_evaluation_id_for`) and in the
idempotency conflict check.  Bumping it is a breaking schema change and
must be a deliberate, documented decision.
"""
from __future__ import annotations

from typing import Final

OUTCOME_EVALUATION_SCHEMA_VERSION: Final[str] = "atlas-outcome-evaluation/v1"

__all__ = ["OUTCOME_EVALUATION_SCHEMA_VERSION"]
