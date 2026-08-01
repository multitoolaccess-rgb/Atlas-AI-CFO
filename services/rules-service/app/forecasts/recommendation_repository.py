"""Repository for append-only ``Recommendation`` persistence.

Phase 2 Slice 1 commit-3 application-layer repository.  Mirrors the
:class:`app.forecasts.ForecastRepository` pattern: class-based,
owning its own short transaction, with bounded savepoint + lookup
winner for race recovery.  Adds two commit-3-only guarantees:

* **Authorization before existence**: the goal is loaded + ownership
  verified BEFORE the forecast_version is loaded + ownership
  verified BEFORE the derivation engine runs.  Cross-user access
  returns :class:`GoalNotFoundError` /
  :class:`RecommendationNotFoundError` indistinguishably from a
  missing resource so a non-owner cannot tell whether a goal /
  forecast_version with the requested ids exists under a different
  user.
* **Idempotent replay**: same canonical inputs ⇒ same
  ``Recommendation`` PK ⇒ second call observes the existing row and
  returns it with ``created=False``.  Different ``rule_version``
  or ``recommendation_kind`` ⇒ different PK ⇒ new row.

The repository emits typed ``*Error`` exceptions that carry ONLY
the safe contract ``code`` literal; the HTTP route layer (commit-5)
will map these to envelopes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.forecasts.recommendation_engine import (
    ForecastSignals,
    InvalidCurrencyEvidence,
    InvalidForecastSignals,
    InvalidSchemaVersion,
    UnknownRecommendationKind,
    derive_recommendation,
)
from app.models import Forecast, ForecastVersion, Goal, Recommendation


class RecommendationRepositoryError(Exception):
    """Base class for repository errors. Carries only the safe contract ``code``."""


class GoalNotFoundError(RecommendationRepositoryError):
    code: Final[str] = "goal_not_found"


class ForecastVersionNotFoundError(RecommendationRepositoryError):
    code: Final[str] = "recommendation_not_found"


class ForecastVersionCurrencyInvalid(RecommendationRepositoryError):
    code: Final[str] = "currency_invalid"


class DerivationFailure(RecommendationRepositoryError):
    code: Final[str] = "derivation_invalid"


@dataclass(frozen=True)
class PersistedRecommendation:
    recommendation: Recommendation
    created: bool


class RecommendationRepository:
    """Owns the short transaction that creates or reuses a derived Recommendation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Authorization (ownership-before-existence)
    # ------------------------------------------------------------------

    def _authorize_goal_ownership(self, *, user_id: int, goal_id: int) -> Goal:
        goal = self._session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            # Same envelope for "missing" and "cross-user" → no disclosure.
            raise GoalNotFoundError("goal not accessible")
        if goal.is_archived:
            raise GoalNotFoundError("goal not accessible")
        return goal

    def _authorize_forecast_version_ownership(
        self, *, user_id: int, goal_id: int, forecast_version_id: str,
    ) -> ForecastVersion:
        fv = self._session.get(ForecastVersion, forecast_version_id)
        if fv is None:
            raise ForecastVersionNotFoundError("forecast_version not accessible")
        fcst = self._session.get(Forecast, fv.forecast_id)
        if fcst is None:
            raise ForecastVersionNotFoundError("forecast_version not accessible")
        if fcst.user_id != user_id or fcst.goal_id != goal_id:
            raise ForecastVersionNotFoundError("forecast_version not accessible")
        return fv

    # ------------------------------------------------------------------
    # Idempotent lookup helpers
    # ------------------------------------------------------------------

    def _existing_recommendation(self, *, rec_id: str) -> Recommendation | None:
        return self._session.get(Recommendation, rec_id)

    # ------------------------------------------------------------------
    # Persist (single transaction; owns commit / rollback)
    # ------------------------------------------------------------------

    def _persist_once(
        self,
        *,
        user_id: int,
        goal_id: int,
        goal: Goal,
        fv: ForecastVersion,
        signals: ForecastSignals,
        recommendation_kind: str,
        rule_version: str,
        derivation_schema_version: str,
        rec_id: str,
    ) -> Recommendation:
        try:
            payload = derive_recommendation(
                signals=signals,
                recommendation_kind=recommendation_kind,
                rule_version=rule_version,
                derivation_schema_version=derivation_schema_version,
            )
        except InvalidCurrencyEvidence as exc:
            raise ForecastVersionCurrencyInvalid("currency fail-closed") from exc
        except (InvalidForecastSignals, InvalidSchemaVersion, UnknownRecommendationKind) as exc:
            raise DerivationFailure("derivation ruled out by bounded signal or rule") from exc

        recommendation = Recommendation(
            id=rec_id,
            user_id=user_id,
            goal_id=goal_id,
            forecast_version_id=fv.id,
            forecast_input_state_hash=signals.forecast_input_state_hash,
            recommendation_kind=recommendation_kind,
            rule_version=rule_version,
            derivation_schema_version=derivation_schema_version,
            currency="USD",
            reason=payload["reason"],
            expected_impact_min_decimal=payload["expected_impact_min_decimal"],
            expected_impact_max_decimal=payload["expected_impact_max_decimal"],
            confidence_score=payload["confidence_score"],
            assumptions_json=payload["assumptions_json"],
            risks_json=payload["risks_json"],
            freshness_json=payload["freshness_json"],
            provenance_json=payload["provenance_json"],
            metadata_json=payload["metadata_json"],
            derived_at=fv.calculated_at,
            data_as_of=fv.data_as_of,
            expires_at=None,
        )
        self._session.add(recommendation)
        self._session.flush()
        return recommendation

    @staticmethod
    def _dialect_supports_for_update(session: Session) -> bool:
        bind = session.bind
        return bool(bind is not None and getattr(bind.dialect, "name", "") == "postgresql")

    def _recover_database_winner(
        self, *, rec_id: str,
    ) -> Recommendation | None:
        attempt_recovery = self._session.get(Recommendation, rec_id)
        if attempt_recovery is None:
            return None
        return attempt_recovery

    def persist(
        self,
        *,
        user_id: int,
        goal_id: int,
        forecast_version_id: str,
        recommendation_kind: str,
        rule_version: str = "v1.0",
        derivation_schema_version: str = "atlas-recommendation/v1",
    ) -> PersistedRecommendation:
        """Persist a derived recommendation with idempotent replay semantics.

        Returns:

            :class:`PersistedRecommendation` with ``created=False`` on a
            replayed retry, ``created=True`` on a fresh write.
        """
        from app.models.decision_journal_identities import recommendation_id_for

        rec_id = recommendation_id_for(
            user_id=user_id,
            goal_id=goal_id,
            forecast_version_id=forecast_version_id,
            recommendation_kind=recommendation_kind,
            rule_version=rule_version,
            derivation_schema_version=derivation_schema_version,
        )

        goal = self._authorize_goal_ownership(user_id=user_id, goal_id=goal_id)
        fv = self._authorize_forecast_version_ownership(
            user_id=user_id, goal_id=goal_id, forecast_version_id=forecast_version_id,
        )
        signals = ForecastSignals.from_forecast_version(fv)

        existing = self._existing_recommendation(rec_id=rec_id)
        if existing is not None:
            # In-replay path: the derivation is unchanged, so we surface
            # the existing row with ``created=False``.  The DB-level
            # immutability trigger continues to make UPDATE/DELETE
            # impossible, so we cannot accidentally mutate.
            return PersistedRecommendation(recommendation=existing, created=False)

        try:
            recommendation = self._persist_once(
                user_id=user_id,
                goal_id=goal_id,
                goal=goal,
                fv=fv,
                signals=signals,
                recommendation_kind=recommendation_kind,
                rule_version=rule_version,
                derivation_schema_version=derivation_schema_version,
                rec_id=rec_id,
            )
            self._session.commit()
            return PersistedRecommendation(recommendation=recommendation, created=True)
        except (
            GoalNotFoundError,
            ForecastVersionNotFoundError,
            ForecastVersionCurrencyInvalid,
            DerivationFailure,
        ):
            self._session.rollback()
            raise
        except (IntegrityError, OperationalError) as exc:
            self._session.rollback()
            recovered = self._recover_database_winner(rec_id=rec_id)
            if recovered is not None:
                self._session.commit()
                return PersistedRecommendation(recommendation=recovered, created=False)
            self._session.rollback()
            raise RecommendationRepositoryError("recommendation persistence conflict") from exc


__all__ = [
    "RecommendationRepositoryError",
    "GoalNotFoundError",
    "ForecastVersionNotFoundError",
    "ForecastVersionCurrencyInvalid",
    "DerivationFailure",
    "PersistedRecommendation",
    "RecommendationRepository",
]
