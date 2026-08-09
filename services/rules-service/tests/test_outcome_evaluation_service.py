"""Application-layer tests for :class:`OutcomeEvaluationService`.

The world fixtures (:mod:`tests._outcome_world`) reuse the Phase 2
commit-3 alembic-upgraded SQLite world and plant decision journal
entries, so the outcome_evaluations immutability / ownership / format
triggers ARE installed.  Every test opens + asserts inside a single
``with Session(engine)`` block so the returned ORM object stays attached
while attributes are read (SQLAlchemy expires objects on commit).

Coverage invariants:

* ownership-before-existence: goal, recommendation, and decision are
  verified BEFORE persistence; cross-user access is indistinguishable
  from missing
* decision must already be ``accept`` — rejected / deferred / missing
  decisions raise ``DecisionNotFoundError``
* lifecycle-state evidence contract enforced at the service layer
  (pending / not_yet_measurable forbid evidence; measured requires it)
* privacy: ``evidence_reference_hash`` is server-derived (the service
  exposes NO client-supplied hash / raw-reference parameter), and the
  conflict surface carries only the stable ETag
* idempotent retry ⇒ identical row, ``replayed=True``
* same idempotency key + different lifecycle / evidence payload /
  recommendation ⇒ ``OutcomeConflictError``
* race handling: pre-seeded winner + new-session call ⇒ ``replayed=True``
* append-only: the service exposes no UPDATE / DELETE, and the Phase 3
  SQL triggers still block UPDATE / DELETE at the SQL layer
* failed record leaves no partial evaluation row
"""
from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.forecasts.outcome_evaluation_schemas import OUTCOME_EVALUATION_SCHEMA_VERSION
from app.forecasts.outcome_evaluation_service import (
    DecisionNotFoundError,
    EvidenceSourceKindError,
    GoalNotFoundError,
    IdempotencyKeyRequiredError,
    LifecycleError,
    OutcomeConflictError,
    OutcomeEvaluationService,
    OutcomeWriteResult,
    RecommendationNotFoundError,
    _derive_evidence_reference_hash,
    outcome_etag_for,
)
from app.forecasts.recommendation_schemas import DECISION_JOURNAL_SCHEMA_VERSION
from app.models import DecisionJournalEntry, OutcomeEvaluation
from app.models.decision_journal_identities import (
    canonical_idempotency_key_hash,
    decision_journal_id_for,
    outcome_evaluation_id_for,
    recommendation_id_for,
)

from tests._commit3_world import (
    cross_user_id,
    primary_goal_id,
    primary_user_id,
    recommendation_row_id,
    world_engine,
    world_with_recommendation,
)
from tests._outcome_world import (
    accepted_decision_row_id,
    deferred_decision_row_id,
    rejected_decision_row_id,
    world_with_accepted_decision,
    world_with_deferred_decision,
    world_with_rejected_decision,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _measured_kwargs(*, now: datetime) -> dict:
    """Canonical measured evidence payload (all six caller-supplied fields)."""
    return dict(
        lifecycle="measured",
        evidence_source_kind="account_balance_delta",
        measurement_window_start=now,
        measurement_window_end=now,
        result_json='{"delta_usd": "150.00"}',
        confidence="high",
        explanation="Account balance increased by $150 in the measurement window",
    )


# ---------------------------------------------------------------------------
# Persistence across the three bounded lifecycles
# ---------------------------------------------------------------------------


def test_service_persists_pending_outcome(world_with_accepted_decision):
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        result = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key="k-pending-1",
        )
        assert isinstance(result, OutcomeWriteResult)
        assert result.replayed is False
        assert result.conflict is False
        assert result.current_etag == outcome_etag_for(result.entry.id)
        assert result.entry.lifecycle == "pending"
        assert result.entry.evidence_source_kind is None
        assert result.entry.evidence_reference_hash is None
        assert result.entry.measurement_window_start is None
        assert result.entry.result_json is None
        assert result.entry.confidence is None
        assert result.entry.explanation is None


def test_service_persists_not_yet_measurable_outcome(world_with_accepted_decision):
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        result = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="not_yet_measurable", raw_idempotency_key="k-nym-1",
        )
        assert result.replayed is False
        assert result.entry.lifecycle == "not_yet_measurable"
        assert result.entry.evidence_source_kind is None
        assert result.entry.evidence_reference_hash is None


def test_service_persists_measured_outcome_with_server_derived_hash(world_with_accepted_decision):
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        result = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key="k-measured-1", **_measured_kwargs(now=now),
        )
        assert result.replayed is False
        assert result.entry.lifecycle == "measured"
        assert result.entry.evidence_source_kind == "account_balance_delta"
        assert result.entry.measurement_window_start is not None
        assert result.entry.result_json is not None
        assert result.entry.confidence == "high"
        assert result.entry.explanation is not None
        expected_hash = _derive_evidence_reference_hash(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            evidence_source_kind="account_balance_delta",
            measurement_window_start=now, measurement_window_end=now,
        )
        assert result.entry.evidence_reference_hash == expected_hash


# ---------------------------------------------------------------------------
# Ownership-before-existence
# ---------------------------------------------------------------------------


def test_service_rejects_cross_user_goal(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(GoalNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=cross_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="pending", raw_idempotency_key="k-cross-goal",
            )


def test_service_rejects_cross_user_recommendation(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(RecommendationNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id="00000000-0000-4000-8000-000000000099",
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="pending", raw_idempotency_key="k-cross-rec",
            )


def test_service_rejects_missing_decision(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(DecisionNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id="00000000-0000-4000-8000-000000000099",
                lifecycle="pending", raw_idempotency_key="k-missing-dec",
            )


def test_service_rejects_rejected_decision(world_with_rejected_decision):
    with Session(world_with_rejected_decision) as session:
        with pytest.raises(DecisionNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=rejected_decision_row_id(),
                lifecycle="pending", raw_idempotency_key="k-reject-dec",
            )


def test_service_rejects_deferred_decision(world_with_deferred_decision):
    with Session(world_with_deferred_decision) as session:
        with pytest.raises(DecisionNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=deferred_decision_row_id(),
                lifecycle="pending", raw_idempotency_key="k-defer-dec",
            )


def test_service_rejects_decision_for_different_recommendation(world_with_accepted_decision):
    """Decision on rec B cannot back an outcome recorded against rec A."""
    now = _now()
    rec_b = recommendation_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        forecast_version_id="00000000-0000-4000-8000-000000000020",
        recommendation_kind="increase_savings", rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    )
    idem_b = canonical_idempotency_key_hash("outcome-world-decision-b")
    decision_b = decision_journal_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=rec_b, decision_action="accept",
        idempotency_key_hash=idem_b, schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
    )
    with Session(world_with_accepted_decision) as session, session.begin():
        session.execute(
            text(
                "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                "forecast_input_state_hash, recommendation_kind, rule_version, "
                "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                "expected_impact_max_decimal, confidence_score, assumptions_json, "
                "risks_json, freshness_json, provenance_json, derived_at, data_as_of) "
                "VALUES (:id, 1, 1, '00000000-0000-4000-8000-000000000020', :h, "
                "'increase_savings', 'v1.0', 'atlas-recommendation/v1', 'USD', 'r2', "
                "0.0, 0.0, 0.65, '{}', '[]', '{}', '{}', :now, :now)"
            ),
            {"id": rec_b, "h": "a" * 64, "now": now},
        )
        session.add(
            DecisionJournalEntry(
                id=decision_b,
                recommendation_id=rec_b,
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                decision_action="accept",
                schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
                idempotency_key_hash=idem_b,
                currency="USD",
                decided_at=now,
            )
        )
        session.flush()
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(DecisionNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),  # rec A
                decision_journal_entry_id=decision_b,  # decision for rec B
                lifecycle="pending", raw_idempotency_key="k-diff-rec-dec",
            )


# ---------------------------------------------------------------------------
# Lifecycle-state evidence contract (service-layer defense-in-depth)
# ---------------------------------------------------------------------------


def test_service_rejects_unknown_lifecycle(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(LifecycleError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="measured!", raw_idempotency_key="k-bad-lifecycle",
            )


def test_service_measured_requires_evidence_source_kind(world_with_accepted_decision):
    now = _now()
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(LifecycleError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="measured", raw_idempotency_key="k-no-source",
                measurement_window_start=now, measurement_window_end=now,
                result_json='{}', confidence="high", explanation="x",
            )


def test_service_measured_requires_measurement_window(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(LifecycleError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="measured", raw_idempotency_key="k-no-window",
                evidence_source_kind="account_balance_delta",
                result_json='{}', confidence="high", explanation="x",
            )


def test_service_pending_forbids_evidence_fields(world_with_accepted_decision):
    now = _now()
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(LifecycleError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="pending", raw_idempotency_key="k-pending-ev",
                evidence_source_kind="account_balance_delta",
                measurement_window_start=now, measurement_window_end=now,
                result_json='{}', confidence="high", explanation="x",
            )


def test_service_not_yet_measurable_forbids_evidence_fields(world_with_accepted_decision):
    now = _now()
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(LifecycleError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="not_yet_measurable", raw_idempotency_key="k-nym-ev",
                evidence_source_kind="account_balance_delta",
                measurement_window_start=now, measurement_window_end=now,
                result_json='{}', confidence="high", explanation="x",
            )


def test_service_rejects_non_allowlisted_evidence_source_kind(world_with_accepted_decision):
    now = _now()
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(EvidenceSourceKindError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="measured", raw_idempotency_key="k-bad-source",
                evidence_source_kind="raw_transaction_url",
                measurement_window_start=now, measurement_window_end=now,
                result_json='{}', confidence="high", explanation="x",
            )


# ---------------------------------------------------------------------------
# Privacy contract: server-derived hash, no client-supplied evidence
# ---------------------------------------------------------------------------


def test_service_never_accepts_client_evidence_hash_or_raw_reference():
    """The service API cannot express a raw evidence reference or a client hash.

    ``evidence_reference_hash`` is SERVER-derived only; the prior unsafe
    ``authoritative_evidence_reference`` String(512) surface is gone.
    """
    sig = inspect.signature(OutcomeEvaluationService.record)
    params = set(sig.parameters)
    assert "evidence_reference_hash" not in params
    assert "evidence_reference" not in params
    assert "authoritative_evidence_reference" not in params
    assert "evidence_reference_url" not in params


def test_service_evidence_reference_hash_is_never_a_raw_value(world_with_accepted_decision):
    """The stored evidence reference is always a 64-char lowercase hex digest."""
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        result = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key="k-privacy-1", **_measured_kwargs(now=now),
        )
        ref = result.entry.evidence_reference_hash
        assert re.fullmatch(r"[0-9a-f]{64}", ref)
        # A raw reference could carry a URL scheme, path, or filename — none
        # of these can appear in a lowercase-hex digest.
        assert "http" not in ref
        assert "/" not in ref
        assert "." not in ref
        assert ":" not in ref


# ---------------------------------------------------------------------------
# Idempotency-Key: required + hashed-only storage
# ---------------------------------------------------------------------------


def test_service_rejects_empty_idempotency_key(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(IdempotencyKeyRequiredError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id=accepted_decision_row_id(),
                lifecycle="pending", raw_idempotency_key="",
            )


def test_service_never_persists_raw_idempotency_key(world_with_accepted_decision):
    raw = "atlas-test-key-v1"
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        result = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key=raw,
        )
        eval_id = result.entry.id
    with Session(world_with_accepted_decision) as session:
        stored_hash = session.execute(
            text("SELECT idempotency_key_hash FROM outcome_evaluations WHERE id = :id"),
            {"id": eval_id},
        ).scalar_one()
        assert stored_hash == canonical_idempotency_key_hash(raw)
        assert stored_hash != raw
        assert len(stored_hash) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", stored_hash)


# ---------------------------------------------------------------------------
# Idempotent replay ↔ conflict detection
# ---------------------------------------------------------------------------


def test_service_idempotent_replay_returns_same_row(world_with_accepted_decision):
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        first = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key="k-replay-1",
        )
        first_id = first.entry.id
    with Session(world_with_accepted_decision) as session:
        replay = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key="k-replay-1",
        )
        assert replay.entry.id == first_id
        assert replay.replayed is True
        assert replay.conflict is False


def test_service_idempotent_replay_measured_same_payload(world_with_accepted_decision):
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        first = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key="k-replay-measured", **_measured_kwargs(now=now),
        )
        first_id = first.entry.id
        first_hash = first.entry.evidence_reference_hash
    with Session(world_with_accepted_decision) as session:
        replay = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key="k-replay-measured", **_measured_kwargs(now=now),
        )
        assert replay.entry.id == first_id
        assert replay.replayed is True
        assert replay.entry.evidence_reference_hash == first_hash


def test_service_same_key_different_lifecycle_raises_conflict(world_with_accepted_decision):
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        first = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key="k-conflict-life",
        )
        first_id = first.entry.id
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(OutcomeConflictError) as captured:
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=rec_id, decision_journal_entry_id=dec_id,
                raw_idempotency_key="k-conflict-life", **_measured_kwargs(now=_now()),
            )
        assert captured.value.code == "outcome_conflict"
        assert captured.value.current_etag == outcome_etag_for(first_id)
        assert captured.value.current_etag.endswith("-o1")


def test_service_same_key_different_measured_payload_raises_conflict(world_with_accepted_decision):
    """Same key + same lifecycle but a divergent measured payload is a conflict,
    not a silent replay of the prior evidence."""
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        first = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key="k-conflict-payload", **_measured_kwargs(now=now),
        )
        first_id = first.entry.id
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(OutcomeConflictError) as captured:
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=rec_id, decision_journal_entry_id=dec_id,
                raw_idempotency_key="k-conflict-payload",
                lifecycle="measured",
                evidence_source_kind="account_balance_delta",
                measurement_window_start=now, measurement_window_end=now,
                result_json='{"delta_usd": "999.00"}',  # divergent
                confidence="high", explanation="different explanation",
            )
        assert captured.value.current_etag == outcome_etag_for(first_id)


def test_service_same_key_different_recommendation_raises_conflict(world_with_accepted_decision):
    now = _now()
    rec_b = recommendation_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        forecast_version_id="00000000-0000-4000-8000-000000000020",
        recommendation_kind="increase_savings", rule_version="v1.0",
        derivation_schema_version="atlas-recommendation/v1",
    )
    idem_b = canonical_idempotency_key_hash("outcome-world-decision-b")
    decision_b = decision_journal_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=rec_b, decision_action="accept",
        idempotency_key_hash=idem_b, schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
    )
    with Session(world_with_accepted_decision) as session, session.begin():
        session.execute(
            text(
                "INSERT INTO recommendations (id, user_id, goal_id, forecast_version_id, "
                "forecast_input_state_hash, recommendation_kind, rule_version, "
                "derivation_schema_version, currency, reason, expected_impact_min_decimal, "
                "expected_impact_max_decimal, confidence_score, assumptions_json, "
                "risks_json, freshness_json, provenance_json, derived_at, data_as_of) "
                "VALUES (:id, 1, 1, '00000000-0000-4000-8000-000000000020', :h, "
                "'increase_savings', 'v1.0', 'atlas-recommendation/v1', 'USD', 'r2', "
                "0.0, 0.0, 0.65, '{}', '[]', '{}', '{}', :now, :now)"
            ),
            {"id": rec_b, "h": "a" * 64, "now": now},
        )
        session.add(
            DecisionJournalEntry(
                id=decision_b,
                recommendation_id=rec_b,
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                decision_action="accept",
                schema_version=DECISION_JOURNAL_SCHEMA_VERSION,
                idempotency_key_hash=idem_b,
                currency="USD",
                decided_at=now,
            )
        )
        session.flush()
    rec_a = recommendation_row_id()
    dec_a = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_a, decision_journal_entry_id=dec_a,
            lifecycle="pending", raw_idempotency_key="k-conflict-rec",
        )
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(OutcomeConflictError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=rec_b, decision_journal_entry_id=decision_b,
                lifecycle="pending", raw_idempotency_key="k-conflict-rec",
            )


def test_service_conflict_error_carries_only_etag(world_with_accepted_decision):
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    raw_key = "k-conflict-surface"
    with Session(world_with_accepted_decision) as session:
        OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key=raw_key, **_measured_kwargs(now=now),
        )
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(OutcomeConflictError) as captured:
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=rec_id, decision_journal_entry_id=dec_id,
                raw_idempotency_key=raw_key,
                lifecycle="measured",
                evidence_source_kind="account_balance_delta",
                measurement_window_start=now, measurement_window_end=now,
                result_json='{"delta_usd": "999.00"}',
                confidence="high", explanation="different explanation",
            )
    surf = (captured.value.current_etag + " " + captured.value.code).lower()
    for sensitive in (
        raw_key.lower(),
        "account_balance_delta",
        "999.00",
        "150.00",
        "different explanation",
        "transaction_pattern",
    ):
        assert sensitive not in surf, f"sensitive leak on conflict surface: {sensitive!r}"


# ---------------------------------------------------------------------------
# Race recovery: pre-seeded winner + new-session call replays
# ---------------------------------------------------------------------------


def test_service_race_recovery_returns_committed_winner(world_with_accepted_decision):
    """Pre-seed the deterministic PK row (writer-A) and replay writer-B's
    identical canonical request ⇒ ``replayed=True``."""
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    raw_key = "k-race-1"
    idem_hash = canonical_idempotency_key_hash(raw_key)
    eval_id = outcome_evaluation_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=rec_id, decision_journal_entry_id=dec_id,
        lifecycle="measured", idempotency_key_hash=idem_hash,
        schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION,
    )
    derived_hash = _derive_evidence_reference_hash(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=rec_id, decision_journal_entry_id=dec_id,
        evidence_source_kind="account_balance_delta",
        measurement_window_start=now, measurement_window_end=now,
    )
    with Session(world_with_accepted_decision) as session, session.begin():
        session.add(
            OutcomeEvaluation(
                id=eval_id,
                recommendation_id=rec_id,
                decision_journal_entry_id=dec_id,
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                lifecycle="measured",
                schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION,
                idempotency_key_hash=idem_hash,
                currency="USD",
                evidence_source_kind="account_balance_delta",
                evidence_reference_hash=derived_hash,
                measurement_window_start=now,
                measurement_window_end=now,
                result_json='{"delta_usd": "150.00"}',
                confidence="high",
                explanation="Account balance increased by $150 in the measurement window",
                recorded_at=now,
            )
        )
        session.flush()
    with Session(world_with_accepted_decision) as session:
        result = OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            raw_idempotency_key=raw_key, **_measured_kwargs(now=now),
        )
        assert result.replayed is True
        assert result.conflict is False
        assert result.entry.id == eval_id


def test_recover_database_winner_falls_back_to_idempotency_key(world_with_accepted_decision):
    """A UNIQUE-collision loser whose PK differs from the winner's is recovered
    via the cross-row idempotency-key lookup, not reported as a generic error."""
    now = _now()
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    raw_key = "k-race-divergent"
    idem_hash = canonical_idempotency_key_hash(raw_key)
    # Divergent lifecycle ⇒ the loser's deterministic PK differs from the
    # committed winner's even though the UNIQUE tuple collides.
    winner_id = outcome_evaluation_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=rec_id, decision_journal_entry_id=dec_id,
        lifecycle="measured", idempotency_key_hash=idem_hash,
        schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION,
    )
    loser_id = outcome_evaluation_id_for(
        user_id=primary_user_id(), goal_id=primary_goal_id(),
        recommendation_id=rec_id, decision_journal_entry_id=dec_id,
        lifecycle="pending", idempotency_key_hash=idem_hash,
        schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION,
    )
    assert loser_id != winner_id
    with Session(world_with_accepted_decision) as session, session.begin():
        session.add(
            OutcomeEvaluation(
                id=winner_id,
                recommendation_id=rec_id,
                decision_journal_entry_id=dec_id,
                user_id=primary_user_id(),
                goal_id=primary_goal_id(),
                lifecycle="measured",
                schema_version=OUTCOME_EVALUATION_SCHEMA_VERSION,
                idempotency_key_hash=idem_hash,
                currency="USD",
                evidence_source_kind="account_balance_delta",
                evidence_reference_hash=_derive_evidence_reference_hash(
                    user_id=primary_user_id(), goal_id=primary_goal_id(),
                    recommendation_id=rec_id, decision_journal_entry_id=dec_id,
                    evidence_source_kind="account_balance_delta",
                    measurement_window_start=now, measurement_window_end=now,
                ),
                measurement_window_start=now,
                measurement_window_end=now,
                result_json='{"delta_usd": "150.00"}',
                confidence="high",
                explanation="Account balance increased by $150 in the measurement window",
                recorded_at=now,
            )
        )
        session.flush()
    with Session(world_with_accepted_decision) as session:
        service = OutcomeEvaluationService(session)
        recovered = service._recover_database_winner(
            user_id=primary_user_id(),
            idempotency_key_hash=idem_hash,
            evaluation_id=loser_id,
        )
        assert recovered is not None
        assert recovered.id == winner_id
        assert recovered.lifecycle == "measured"


# ---------------------------------------------------------------------------
# Append-only: service exposes no UPDATE/DELETE + SQL triggers still block
# ---------------------------------------------------------------------------


def test_service_has_no_mutating_methods():
    for name in ("update", "delete", "cancel", "transition", "modify"):
        assert not hasattr(OutcomeEvaluationService, name), (
            f"append-only outcome service must not expose {name}()"
        )


def test_outcome_immutable_trigger_blocks_update(world_with_accepted_decision):
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key="k-immut-u",
        )
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE outcome_evaluations SET lifecycle = 'measured' WHERE user_id = 1")
            )


def test_outcome_immutable_trigger_blocks_delete(world_with_accepted_decision):
    rec_id = recommendation_row_id()
    dec_id = accepted_decision_row_id()
    with Session(world_with_accepted_decision) as session:
        OutcomeEvaluationService(session).record(
            user_id=primary_user_id(), goal_id=primary_goal_id(),
            recommendation_id=rec_id, decision_journal_entry_id=dec_id,
            lifecycle="pending", raw_idempotency_key="k-immut-d",
        )
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM outcome_evaluations WHERE user_id = 1"))


# ---------------------------------------------------------------------------
# Rollback behaviour (failed record leaves no partial evaluation row)
# ---------------------------------------------------------------------------


def test_failed_record_does_not_persist_partial_row(world_with_accepted_decision):
    with Session(world_with_accepted_decision) as session:
        before = session.execute(
            text("SELECT COUNT(*) FROM outcome_evaluations")
        ).scalar_one()
    assert before == 0
    with Session(world_with_accepted_decision) as session:
        with pytest.raises(DecisionNotFoundError):
            OutcomeEvaluationService(session).record(
                user_id=primary_user_id(), goal_id=primary_goal_id(),
                recommendation_id=recommendation_row_id(),
                decision_journal_entry_id="00000000-0000-4000-8000-000000000099",
                lifecycle="pending", raw_idempotency_key="k-rollback-1",
            )
    with Session(world_with_accepted_decision) as session:
        after = session.execute(
            text("SELECT COUNT(*) FROM outcome_evaluations")
        ).scalar_one()
    assert after == 0


# `world_engine` is imported to keep the alembic-upgraded substrate in the
# module's test graph alongside the decision-planted worlds.
_ = world_engine
