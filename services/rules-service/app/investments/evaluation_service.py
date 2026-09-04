"""INV-12 internal evaluation / replay service and durable-store writers.

Implements design gate ``ATLAS-INVESTMENT-INV-12-DESIGN.md`` §17/§21a steps
6–8 with zero architectural choices left open:

- Store writers are server-internal only (``store_observation``,
  ``store_portfolio_snapshot``); there is no ingestion API and no browser
  write path.
- The evaluation engine calls the existing INV-11 ``evaluate_outcome()``
  as-is with observations projected from the durable observation store into
  the ``outcome_tracking.MarketObservation`` shape. No parallel engine.
- Measured values are frozen through the existing ``record_outcome()`` path
  (single store of measured values); the evaluation artifact row carries
  identity/lifecycle/replay metadata only.
- Replay (meanings C+D+E, decision D-3) is deterministic and read-only: it
  reproduces the stored result from the same frozen inputs and reports
  ``match`` / ``methodology_changed`` / ``inputs_unavailable`` /
  ``hash_mismatch`` without side effects.
- Every failure fails closed with a typed ``blocked_reason`` on the artifact
  (missing snapshot is never silently re-derived from current holdings;
  currency/adjustment-basis mismatch is ``not_comparable``, never converted).

No execution, mutation, scheduling, calibration, or retention code exists in
this module (D-7/D-8 deferrals).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InvestmentDecisionRecord,
    InvestmentEvaluationRecord,
    InvestmentMarketObservation,
    InvestmentOutcomeRecord,
    InvestmentPortfolioSnapshot,
)
from .evaluation_contracts import (
    EvaluationReplayState,
    EvaluationResultState,
    EvaluationState,
    HORIZONS,
    InvestmentEvaluationArtifact,
    InvestmentEvaluationReplay,
    METHODOLOGY_VERSION,
    StoredMarketObservation,
)
from .outcome_tracking import (
    MarketObservation,
    OutcomeState,
    RecommendationOutcome,
    TrackedRecommendation,
    evaluate_outcome,
    track_recommendation,
)
from .persistence_repository import InvestmentRepository, InvestmentRepositoryError
from .persistence_service import InvestmentPersistenceError, InvestmentPersistenceService
from .portfolio_intelligence import PortfolioSnapshot

# Horizon close deltas are determinism constants of the first slice: an
# evaluation window is "closed" once ``evaluation_as_of`` reaches
# ``window_start + delta``. Calendar-month semantics are intentionally not
# used here (no scheduler, no timezone calendar dependency); the constants
# are frozen and documented so identical inputs always produce identical
# artifacts.
HORIZON_DELTAS: dict[str, timedelta] = {
    "1D": timedelta(days=1),
    "1W": timedelta(days=7),
    "1M": timedelta(days=30),
    "3M": timedelta(days=91),
    "6M": timedelta(days=182),
    "1Y": timedelta(days=365),
}

# Typed blocked-reason codes (design §18). Values are frozen; new codes are a
# contract change, never an ad-hoc string.
BLOCKED_MISSING_SNAPSHOT = "missing_snapshot"
BLOCKED_MISSING_EVIDENCE = "missing_evidence"
BLOCKED_MISSING_OBSERVATION = "missing_observation"
BLOCKED_WINDOW_NOT_CLOSED = "window_not_closed"
BLOCKED_TEMPORAL_VIOLATION = "temporal_violation"
BLOCKED_CURRENCY_MISMATCH = "currency_mismatch"
BLOCKED_BASIS_MISMATCH = "basis_mismatch"
BLOCKED_DECISION_MISMATCH = "decision_mismatch"


class EvaluationServiceError(ValueError):
    """An INV-12 evaluation request violated an application invariant."""


@dataclass(frozen=True)
class EvaluationRun:
    """Result of one internal evaluation request."""

    artifact: InvestmentEvaluationArtifact
    outcome: RecommendationOutcome | None
    created: bool


class EvaluationService:
    """Server-internal INV-12 evaluation, replay, and store writers."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = InvestmentRepository(session)
        self.persistence = InvestmentPersistenceService(session)

    # ------------------------------------------------------------------ #
    # Durable-store writers (server-internal only)
    # ------------------------------------------------------------------ #

    def store_observation(self, observation: StoredMarketObservation) -> StoredMarketObservation:
        """Write one durable market observation (append-only, idempotent).

        Observations are owner-independent public security data (design §6b/
        §15). An identical delivery collapses onto its deterministic
        ``observation_id``; a restatement with a later ``as_known_at`` is a
        distinct payload and therefore a distinct row. No UPDATE or DELETE is
        ever issued here.
        """
        existing = self.session.scalar(select(InvestmentMarketObservation).where(InvestmentMarketObservation.observation_id == observation.observation_id))
        if existing is not None:
            if existing.observation_hash != observation.observation_hash or existing.payload_json != json.dumps(observation.model_dump(mode="json"), sort_keys=True, separators=(",", ":")):
                raise EvaluationServiceError("observation identity conflict")
            return observation
        row = InvestmentMarketObservation(
            observation_id=observation.observation_id,
            security_id=observation.security_id,
            observed_value=observation.observed_value,
            currency=observation.currency,
            adjustment_basis=observation.adjustment_basis.value,
            observed_at=observation.observed_at,
            as_known_at=observation.as_known_at,
            retrieved_at=observation.retrieved_at,
            source=observation.source,
            source_identifier=observation.source_identifier,
            state=observation.state.value,
            quality=observation.quality.value,
            freshness=observation.freshness.value,
            observation_hash=observation.observation_hash,
            payload_json=json.dumps(observation.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        # Sessions run with autoflush disabled; flush so a duplicate delivery
        # of the same deterministic observation_id is resolved by the select
        # above instead of violating the unique constraint at commit time.
        self.session.flush()
        return observation

    def store_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> InvestmentPortfolioSnapshot:
        """Persist the payload + hash of the single INV-03 snapshot builder.

        Owner-scoped and idempotent over ``(owner_id, snapshot_hash)``. The
        stored payload must be the builder's own digest: the canonical payload
        is re-derived and compared so a tampered payload can never enter the
        store under a valid-looking hash.
        """
        digest = hashlib.sha256(snapshot.canonical_payload().encode()).hexdigest()
        if digest != snapshot.snapshot_hash:
            raise EvaluationServiceError("portfolio snapshot hash mismatch")
        existing = self.session.scalar(select(InvestmentPortfolioSnapshot).where(InvestmentPortfolioSnapshot.owner_id == snapshot.owner_id, InvestmentPortfolioSnapshot.snapshot_hash == snapshot.snapshot_hash))
        if existing is not None:
            stored = json.loads(existing.payload_json)
            if stored != snapshot.model_dump(mode="json"):
                raise EvaluationServiceError("portfolio snapshot identity conflict")
            return existing
        row = InvestmentPortfolioSnapshot(
            owner_id=snapshot.owner_id,
            snapshot_id=f"portfolio-snapshot:{digest}",
            snapshot_hash=digest,
            as_of=snapshot.as_of,
            payload_json=json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        self.session.flush()
        return row

    # ------------------------------------------------------------------ #
    # Observation readers (evaluation input projection)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _aware(value: datetime) -> datetime:
        """Reconstruct the aware UTC instant for a stored row.

        SQLite strips tzinfo when persisting ``DateTime(timezone=True)``; the
        authoritative aware values always live in the canonical payload JSON.
        """
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _stored_observations(self, *, security_id: str, as_known_through: datetime) -> list[InvestmentMarketObservation]:
        rows = list(self.session.scalars(select(InvestmentMarketObservation).where(InvestmentMarketObservation.security_id == security_id)))
        bound = as_known_through.astimezone(UTC)
        return [row for row in rows if self._aware(row.as_known_at) <= bound]

    @staticmethod
    def _project_observations(rows: Iterable[InvestmentMarketObservation]) -> list[MarketObservation]:
        """Project stored rows to the ``outcome_tracking`` shape unchanged."""
        projected: list[MarketObservation] = []
        for row in rows:
            payload = json.loads(row.payload_json)
            projected.append(MarketObservation(
                observation_hash=row.observation_hash,
                security_id=row.security_id,
                price=row.observed_value,
                observed_at=payload["observed_at"],
                as_known_at=payload["as_known_at"],
                state=payload.get("state", "observed"),
            ))
        return projected

    def _currency_and_basis(self, rows: Iterable[InvestmentMarketObservation], observation_hash: str) -> tuple[str | None, str | None]:
        for row in rows:
            if row.observation_hash == observation_hash:
                payload = json.loads(row.payload_json)
                return row.currency, payload.get("adjustment_basis")
        return None, None

    # ------------------------------------------------------------------ #
    # Evaluation engine (reuses evaluate_outcome(); no parallel engine)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _input_hash(*, owner_id: int, recommendation_hash: str, decision_id: str | None, window_start: datetime, evaluation_as_of: datetime, horizon: str, benchmark_security_id: str | None, vintage_bound: datetime) -> str:
        inputs = {
            "owner_id": owner_id,
            "recommendation_hash": recommendation_hash,
            "decision_id": decision_id,
            "window_start": window_start.astimezone(UTC).isoformat(),
            "evaluation_as_of": evaluation_as_of.astimezone(UTC).isoformat(),
            "horizon": horizon,
            "benchmark_security_id": benchmark_security_id,
            "methodology_version": METHODOLOGY_VERSION,
            "vintage_bound": vintage_bound.astimezone(UTC).isoformat(),
        }
        return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _tracked(self, *, owner_id: int, recommendation_record_id: int) -> tuple[TrackedRecommendation, str]:
        packet_row = self.repository.get_evidence_packet(owner_id=owner_id, recommendation_record_id=recommendation_record_id)
        if packet_row is None:
            raise EvaluationServiceError(BLOCKED_MISSING_EVIDENCE)
        return packet_row.packet_hash

    def evaluate(
        self,
        *,
        owner_id: int,
        recommendation_id: str,
        evaluation_as_of: datetime,
        horizon: str,
        vintage_bound: datetime | None = None,
        decision_id: str | None = None,
        benchmark_security_id: str | None = None,
    ) -> EvaluationRun:
        """Run one internal on-demand evaluation (design §17 trigger (a))."""
        if horizon not in HORIZONS:
            raise EvaluationServiceError(f"unsupported horizon: {horizon}")
        if evaluation_as_of.tzinfo is None or evaluation_as_of.utcoffset() is None:
            raise EvaluationServiceError("evaluation_as_of must be timezone-aware UTC")
        evaluation_as_of = evaluation_as_of.astimezone(UTC)
        vintage_bound = (evaluation_as_of if vintage_bound is None else vintage_bound.astimezone(UTC))
        if vintage_bound > evaluation_as_of:
            raise EvaluationServiceError("vintage_bound cannot follow evaluation_as_of")

        projection = self.repository.get_recommendation(owner_id=owner_id, recommendation_id=recommendation_id)
        if projection is None:
            raise EvaluationServiceError("recommendation not found")
        recommendation = projection.recommendation
        record_row = projection.row
        window_start = recommendation.recommendation_as_of

        input_hash = self._input_hash(
            owner_id=owner_id,
            recommendation_hash=recommendation.recommendation_hash,
            decision_id=decision_id,
            window_start=window_start,
            evaluation_as_of=evaluation_as_of,
            horizon=horizon,
            benchmark_security_id=benchmark_security_id,
            vintage_bound=vintage_bound,
        )
        evaluation_id = f"investment-evaluation:{input_hash}"

        existing = self.session.scalar(select(InvestmentEvaluationRecord).where(InvestmentEvaluationRecord.owner_id == owner_id, InvestmentEvaluationRecord.evaluation_id == evaluation_id))
        if existing is not None:
            if existing.evaluation_hash == self._artifact_hash(existing):
                return EvaluationRun(artifact=self._load_artifact(existing), outcome=None, created=False)
            raise EvaluationServiceError("conflicting evaluation artifact")

        # Decision linkage (optional): must be the owner's persisted decision
        # on this recommendation with a matching recommendation hash.
        decision_record_id: int | None = None
        if decision_id is not None:
            decision_row = self.session.scalar(select(InvestmentDecisionRecord).where(
                InvestmentDecisionRecord.owner_id == owner_id,
                InvestmentDecisionRecord.decision_id == decision_id,
                InvestmentDecisionRecord.recommendation_record_id == record_row.id,
            ))
            if decision_row is None:
                raise EvaluationServiceError(BLOCKED_DECISION_MISMATCH)
            if decision_row.recommendation_hash != recommendation.recommendation_hash:
                raise EvaluationServiceError(BLOCKED_DECISION_MISMATCH)
            decision_record_id = decision_row.id

        created_at = datetime.now(UTC)

        # Snapshot closure: a recommendation whose snapshot payload is absent
        # from the store is blocked (never re-derived from current holdings).
        snapshot_rows = list(self.session.scalars(select(InvestmentPortfolioSnapshot).where(InvestmentPortfolioSnapshot.owner_id == owner_id, InvestmentPortfolioSnapshot.snapshot_hash == recommendation.portfolio_snapshot_hash)))
        if not snapshot_rows:
            return EvaluationRun(artifact=self._blocked(owner_id=owner_id, recommendation_record_id=record_row.id, decision_record_id=decision_record_id, recommendation=recommendation, decision_id=decision_id, evaluation_id=evaluation_id, input_hash=input_hash, window_start=window_start, evaluation_as_of=evaluation_as_of, horizon=horizon, benchmark_security_id=benchmark_security_id, vintage_bound=vintage_bound, created_at=created_at, result_state=None, blocked_reason=BLOCKED_MISSING_SNAPSHOT), outcome=None, created=True)

        # Temporal closure: an evaluation_as_of that precedes the baseline is
        # an invalid request, not a measurement. It fails closed with a typed
        # error (no artifact row exists that could satisfy the immutable
        # ``evaluation_as_of >= evaluation_window_start`` invariant while
        # recording the violation honestly).
        if evaluation_as_of < window_start:
            raise EvaluationServiceError(BLOCKED_TEMPORAL_VIOLATION)
        # Window closure: an evaluation before the frozen horizon closes is a
        # legitimate blocked request and is recorded as such.
        if evaluation_as_of < window_start + HORIZON_DELTAS[horizon]:
            return EvaluationRun(artifact=self._blocked(owner_id=owner_id, recommendation_record_id=record_row.id, decision_record_id=decision_record_id, recommendation=recommendation, decision_id=decision_id, evaluation_id=evaluation_id, input_hash=input_hash, window_start=window_start, evaluation_as_of=evaluation_as_of, horizon=horizon, benchmark_security_id=benchmark_security_id, vintage_bound=vintage_bound, created_at=created_at, result_state=None, blocked_reason=BLOCKED_WINDOW_NOT_CLOSED), outcome=None, created=True)

        # Rebuild the tracking record from the frozen recommendation + its
        # persisted evidence packet (reuse, never re-implemented).
        packet_hash = self._tracked(owner_id=owner_id, recommendation_record_id=record_row.id)
        tracking = track_recommendation(recommendation, evidence_packet_hash=packet_hash)

        rows = self._stored_observations(security_id=recommendation.security_id, as_known_through=vintage_bound)
        if not rows:
            # Nothing known at or before the vintage bound: fail closed as a
            # blocked artifact (no outcome row, no fabricated measurement).
            return EvaluationRun(artifact=self._blocked(owner_id=owner_id, recommendation_record_id=record_row.id, decision_record_id=decision_record_id, recommendation=recommendation, decision_id=decision_id, evaluation_id=evaluation_id, input_hash=input_hash, window_start=window_start, evaluation_as_of=evaluation_as_of, horizon=horizon, benchmark_security_id=benchmark_security_id, vintage_bound=vintage_bound, created_at=created_at, result_state=EvaluationResultState.INSUFFICIENT_HISTORY, blocked_reason=BLOCKED_MISSING_OBSERVATION), outcome=None, created=True)

        observations = self._project_observations(rows)
        try:
            result = evaluate_outcome(tracking, evaluation_as_of=evaluation_as_of, observations=observations, horizon=horizon, benchmark_security_id=benchmark_security_id)
        except ValueError as exc:
            raise EvaluationServiceError("outcome evaluation failed") from exc
        outcome = result.outcome

        # Currency / adjustment-basis comparability between the baseline and
        # evaluation observations. Mismatch -> not_comparable, never a silent
        # conversion, never a fabricated number.
        if outcome.state is OutcomeState.AVAILABLE and outcome.baseline_observation_hash and outcome.evaluation_observation_hash:
            baseline_currency, baseline_basis = self._currency_and_basis(rows, outcome.baseline_observation_hash)
            evaluation_currency, evaluation_basis = self._currency_and_basis(rows, outcome.evaluation_observation_hash)
            if baseline_currency is not None and evaluation_currency is not None and baseline_currency != evaluation_currency:
                return EvaluationRun(artifact=self._blocked(owner_id=owner_id, recommendation_record_id=record_row.id, decision_record_id=decision_record_id, recommendation=recommendation, decision_id=decision_id, evaluation_id=evaluation_id, input_hash=input_hash, window_start=window_start, evaluation_as_of=evaluation_as_of, horizon=horizon, benchmark_security_id=benchmark_security_id, vintage_bound=vintage_bound, created_at=created_at, result_state=EvaluationResultState.NOT_COMPARABLE, blocked_reason=BLOCKED_CURRENCY_MISMATCH), outcome=None, created=True)
            if baseline_basis is not None and evaluation_basis is not None and baseline_basis != evaluation_basis:
                return EvaluationRun(artifact=self._blocked(owner_id=owner_id, recommendation_record_id=record_row.id, decision_record_id=decision_record_id, recommendation=recommendation, decision_id=decision_id, evaluation_id=evaluation_id, input_hash=input_hash, window_start=window_start, evaluation_as_of=evaluation_as_of, horizon=horizon, benchmark_security_id=benchmark_security_id, vintage_bound=vintage_bound, created_at=created_at, result_state=EvaluationResultState.NOT_COMPARABLE, blocked_reason=BLOCKED_BASIS_MISMATCH), outcome=None, created=True)

        if decision_id is not None:
            outcome = outcome.model_copy(update={"decision_id": decision_id})
        # SQLite strips tzinfo when persisting DateTime(timezone=True), so
        # ``record_outcome`` (which compares the aware ``evaluation_as_of``
        # against the stored row) would trip on a naive row under the repo's
        # SQLite test DB. ``record_row`` is identity-mapped, so converting its
        # stored instant back to aware UTC keeps the certified persistence
        # service's invariant check meaningful on every dialect.
        record_row.recommendation_as_of = self._aware(record_row.recommendation_as_of)
        outcome_row = self.persistence.record_outcome(outcome, tracking=tracking)

        result_state = {
            OutcomeState.AVAILABLE: EvaluationResultState.AVAILABLE,
            OutcomeState.INSUFFICIENT_HISTORY: EvaluationResultState.INSUFFICIENT_HISTORY,
            OutcomeState.UNAVAILABLE: EvaluationResultState.UNAVAILABLE,
            OutcomeState.TEMPORAL_VIOLATION: EvaluationResultState.TEMPORAL_VIOLATION,
        }[outcome.state]

        artifact = InvestmentEvaluationArtifact.with_hash(
            evaluation_id=evaluation_id,
            owner_id=owner_id,
            recommendation_id=recommendation.recommendation_id,
            recommendation_hash=recommendation.recommendation_hash,
            decision_id=decision_id,
            outcome_id=outcome.outcome_id,
            outcome_hash=outcome.outcome_hash,
            security_id=recommendation.security_id,
            evaluation_window_start=window_start,
            evaluation_as_of=evaluation_as_of,
            horizon=horizon,
            benchmark_security_id=benchmark_security_id,
            evaluation_state=EvaluationState.EVALUATED,
            result_state=result_state,
            methodology_version=METHODOLOGY_VERSION,
            vintage_bound=vintage_bound,
            replay_state=EvaluationReplayState.MATCH,
            input_hash=input_hash,
            created_at=created_at,
        )
        self._persist_artifact(owner_id=owner_id, recommendation_record_id=record_row.id, decision_record_id=decision_record_id, outcome_record_id=outcome_row.id, artifact=artifact)
        return EvaluationRun(artifact=artifact, outcome=outcome, created=True)

    # ------------------------------------------------------------------ #
    # Blocked-artifact construction
    # ------------------------------------------------------------------ #

    def _blocked(
        self,
        *,
        owner_id: int,
        recommendation_record_id: int,
        decision_record_id: int | None,
        recommendation,
        decision_id: str | None,
        evaluation_id: str,
        input_hash: str,
        window_start: datetime,
        evaluation_as_of: datetime,
        horizon: str,
        benchmark_security_id: str | None,
        vintage_bound: datetime,
        created_at: datetime,
        result_state: EvaluationResultState | None,
        blocked_reason: str,
    ) -> InvestmentEvaluationArtifact:
        artifact = InvestmentEvaluationArtifact.with_hash(
            evaluation_id=evaluation_id,
            owner_id=owner_id,
            recommendation_id=recommendation.recommendation_id,
            recommendation_hash=recommendation.recommendation_hash,
            decision_id=decision_id,
            outcome_id=None,
            outcome_hash=None,
            security_id=recommendation.security_id,
            evaluation_window_start=window_start,
            evaluation_as_of=evaluation_as_of,
            horizon=horizon,
            benchmark_security_id=benchmark_security_id,
            evaluation_state=EvaluationState.BLOCKED,
            result_state=result_state,
            blocked_reason=blocked_reason,
            methodology_version=METHODOLOGY_VERSION,
            vintage_bound=vintage_bound,
            replay_state=EvaluationReplayState.MATCH,
            input_hash=input_hash,
            created_at=created_at,
        )
        self._persist_artifact(
            owner_id=owner_id,
            recommendation_record_id=recommendation_record_id,
            decision_record_id=decision_record_id,
            outcome_record_id=None,
            artifact=artifact,
        )
        return artifact

    # ------------------------------------------------------------------ #
    # Artifact persistence + typed read projections
    # ------------------------------------------------------------------ #

    def _persist_artifact(self, *, owner_id: int, recommendation_record_id: int, decision_record_id: int | None, outcome_record_id: int | None, artifact: InvestmentEvaluationArtifact) -> InvestmentEvaluationRecord:
        row = InvestmentEvaluationRecord(
            owner_id=owner_id,
            evaluation_id=artifact.evaluation_id,
            recommendation_record_id=recommendation_record_id,
            recommendation_id=artifact.recommendation_id,
            recommendation_hash=artifact.recommendation_hash,
            decision_record_id=decision_record_id,
            decision_id=artifact.decision_id,
            outcome_record_id=outcome_record_id,
            outcome_id=artifact.outcome_id,
            outcome_hash=artifact.outcome_hash,
            security_id=artifact.security_id,
            evaluation_window_start=artifact.evaluation_window_start,
            evaluation_as_of=artifact.evaluation_as_of,
            horizon=artifact.horizon,
            benchmark_security_id=artifact.benchmark_security_id,
            evaluation_state=artifact.evaluation_state.value,
            result_state=artifact.result_state.value if artifact.result_state else None,
            methodology_version=artifact.methodology_version,
            vintage_bound=artifact.vintage_bound,
            replay_state=artifact.replay_state.value,
            input_hash=artifact.input_hash,
            evaluation_hash=artifact.evaluation_hash,
            payload_json=json.dumps(artifact.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
            created_at=artifact.created_at,
        )
        self.session.add(row)
        self.session.flush()
        return row

    # ------------------------------------------------------------------ #
    # Replay (deterministic re-verification, read-only)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _artifact_hash(row: InvestmentEvaluationRecord) -> str:
        """Recompute the stored artifact hash from the row's own canonical
        payload columns (tamper detection on the read path)."""
        try:
            artifact = InvestmentEvaluationArtifact.model_validate(json.loads(row.payload_json))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise InvestmentRepositoryError("stored evaluation artifact is invalid") from None
        if artifact.evaluation_id != row.evaluation_id or artifact.owner_id != row.owner_id:
            raise InvestmentRepositoryError("stored evaluation artifact identity mismatch")
        return hashlib.sha256(artifact.canonical_payload().encode()).hexdigest()

    def _load_artifact(self, row: InvestmentEvaluationRecord) -> InvestmentEvaluationArtifact:
        canonical = self._artifact_hash(row)
        if canonical != row.evaluation_hash:
            raise InvestmentRepositoryError("stored evaluation artifact hash mismatch")
        artifact = InvestmentEvaluationArtifact.model_validate(json.loads(row.payload_json))
        return artifact

    def replay(self, *, owner_id: int, evaluation_id: str, at: datetime | None = None) -> InvestmentEvaluationReplay:
        """Re-verify one stored artifact against the durable store (D)."""
        row = self.session.scalar(select(InvestmentEvaluationRecord).where(InvestmentEvaluationRecord.owner_id == owner_id, InvestmentEvaluationRecord.evaluation_id == evaluation_id))
        if row is None:
            raise EvaluationServiceError("evaluation not found")
        replayed_at = (datetime.now(UTC) if at is None else at.astimezone(UTC))

        try:
            artifact = self._load_artifact(row)
        except InvestmentRepositoryError:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.HASH_MISMATCH, verified=False, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

        if artifact.methodology_version != METHODOLOGY_VERSION:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.METHODOLOGY_CHANGED, verified=True, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

        if artifact.evaluation_state is EvaluationState.BLOCKED:
            # A blocked artifact is the deterministic result of its request;
            # hash + identity re-verification above is the whole replay.
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.MATCH, verified=True, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

        outcome_row = self.session.scalar(select(InvestmentOutcomeRecord).where(InvestmentOutcomeRecord.owner_id == owner_id, InvestmentOutcomeRecord.outcome_id == artifact.outcome_id)) if artifact.outcome_id else None
        if outcome_row is None:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.INPUTS_UNAVAILABLE, verified=False, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

        projection = self.repository.get_recommendation(owner_id=owner_id, recommendation_id=artifact.recommendation_id)
        if projection is None:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.INPUTS_UNAVAILABLE, verified=False, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)
        record_row = projection.row
        packet_row = self.repository.get_evidence_packet(owner_id=owner_id, recommendation_record_id=record_row.id)
        if packet_row is None:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.INPUTS_UNAVAILABLE, verified=False, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

        tracking = track_recommendation(projection.recommendation, evidence_packet_hash=packet_row.packet_hash)
        rows = self._stored_observations(security_id=artifact.security_id, as_known_through=artifact.vintage_bound)
        observations = self._project_observations(rows)
        try:
            result = evaluate_outcome(tracking, evaluation_as_of=artifact.evaluation_as_of, observations=observations, horizon=artifact.horizon, benchmark_security_id=artifact.benchmark_security_id)
        except ValueError:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.HASH_MISMATCH, verified=False, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

        if result.outcome.outcome_hash != outcome_row.outcome_hash:
            return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.HASH_MISMATCH, verified=False, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)
        return InvestmentEvaluationReplay(evaluation_id=evaluation_id, replay_state=EvaluationReplayState.MATCH, verified=True, evaluation_hash=row.evaluation_hash, input_hash=row.input_hash, replayed_at=replayed_at)

    # ------------------------------------------------------------------ #
    # Read projections used by the owner-scoped read API
    # ------------------------------------------------------------------ #

    def get_evaluation(self, *, owner_id: int, evaluation_id: str) -> InvestmentEvaluationArtifact | None:
        row = self.session.scalar(select(InvestmentEvaluationRecord).where(InvestmentEvaluationRecord.owner_id == owner_id, InvestmentEvaluationRecord.evaluation_id == evaluation_id))
        if row is None:
            return None
        return self._load_artifact(row)

    def list_evaluations(self, *, owner_id: int, recommendation_id: str | None = None, horizon: str | None = None, limit: int = 50) -> list[InvestmentEvaluationArtifact]:
        rows = list(self.session.scalars(select(InvestmentEvaluationRecord).where(InvestmentEvaluationRecord.owner_id == owner_id)))
        artifacts: list[InvestmentEvaluationArtifact] = []
        for row in rows:
            artifact = self._load_artifact(row)
            if recommendation_id is not None and artifact.recommendation_id != recommendation_id:
                continue
            if horizon is not None and artifact.horizon != horizon:
                continue
            artifacts.append(artifact)
        artifacts.sort(key=lambda item: (item.evaluation_as_of, item.evaluation_id), reverse=True)
        return artifacts[:limit]


__all__ = [
    "BLOCKED_BASIS_MISMATCH",
    "BLOCKED_CURRENCY_MISMATCH",
    "BLOCKED_DECISION_MISMATCH",
    "BLOCKED_MISSING_EVIDENCE",
    "BLOCKED_MISSING_OBSERVATION",
    "BLOCKED_MISSING_SNAPSHOT",
    "BLOCKED_TEMPORAL_VIOLATION",
    "BLOCKED_WINDOW_NOT_CLOSED",
    "EvaluationRun",
    "EvaluationService",
    "EvaluationServiceError",
    "HORIZON_DELTAS",
]
