"""Bounded provider-backed UI-10 investment-context research.

This module deliberately does not implement arbitrary URL retrieval or a
browser-to-web/LLM path. It resolves canonical security identity from
owner-authorized Atlas records, calls the existing normalized Finnhub/SEC
adapters, and returns source-linked typed claims.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.market_intelligence.adapters import FinnhubAdapter, ProviderConfigurationError, SecAdapter
from app.market_intelligence.contracts import (
    CompanyNewsItem,
    EarningsEvent,
    EarningsResult,
    MarketBriefReasonCode,
    SecFilingEvent,
)
from app.investments.committee_contracts import CommitteeFinding
from app.investments.contracts import InvestmentStrictModel
from app.investments.persistence_repository import InvestmentRepository, InvestmentRepositoryError
from app.investments.portfolio_intelligence import _identity as holding_identity
from app.investments.securities import SecurityIdentity, SecurityState
from app.models import Account, Holding


SCOUT_METHODOLOGY_VERSION = "ui10-scout-provider-research/v1"
SCOUT_CALCULATION_VERSION = "ui10-source-normalization/v1"


class ScoutState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ScoutClaimKind(StrEnum):
    RETRIEVED_FACT = "retrieved_fact"
    DERIVED_OBSERVATION = "derived_observation"
    MODEL_INTERPRETATION = "model_interpretation"
    UNCERTAINTY = "uncertainty"


class ScoutSourceType(StrEnum):
    COMPANY_NEWS = "company_news"
    EARNINGS = "earnings"
    SEC_FILING = "sec_filing"
    COMPANY_PROFILE = "company_profile"


class ScoutFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ScoutResearchRequest(InvestmentStrictModel):
    """Only bounded user intent crosses the public research boundary."""

    schema_version: Literal["InvestmentScoutResearchRequest/v1"] = "InvestmentScoutResearchRequest/v1"
    recommendation_id: str | None = Field(default=None, max_length=160)
    committee_finding_id: str | None = Field(default=None, max_length=160)
    security_id: str | None = Field(default=None, max_length=128)
    discovery_candidate_id: str | None = Field(default=None, max_length=200)
    question: str = Field(min_length=1, max_length=500)
    max_sources: int = Field(default=12, ge=1, le=24)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def exactly_one_selector(self) -> "ScoutResearchRequest":
        values = (self.recommendation_id, self.committee_finding_id, self.security_id, self.discovery_candidate_id)
        if sum(value is not None and bool(value.strip()) for value in values) != 1:
            raise ValueError("exactly one canonical research selector is required")
        if self.discovery_candidate_id:
            raise ValueError("discovery candidate research is not available in this Scout boundary")
        return self


class ScoutSourceRecord(InvestmentStrictModel):
    """Validated source metadata; provider text remains untrusted data."""

    schema_version: Literal["InvestmentScoutSource/v1"] = "InvestmentScoutSource/v1"
    source_id: str = Field(min_length=1, max_length=160, pattern=r"^scout-source:[a-f0-9]{32}$")
    source_type: ScoutSourceType
    provider: str = Field(min_length=1, max_length=32)
    source_url: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=300)
    publisher: str | None = Field(default=None, max_length=120)
    excerpt: str | None = Field(default=None, max_length=1200)
    publication_at: datetime | None = None
    retrieved_at: datetime
    freshness: ScoutFreshness = ScoutFreshness.FRESH
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("title", "publisher", "excerpt")
    @classmethod
    def sanitize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.replace("\x00", " ").split())[:1200]

    @field_validator("publication_at", "retrieved_at")
    @classmethod
    def timestamps_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Scout timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def source_temporal_order(self) -> "ScoutSourceRecord":
        if self.publication_at is not None and self.publication_at > self.retrieved_at:
            raise ValueError("source publication cannot be later than retrieval")
        return self


class ScoutEvidenceRecord(InvestmentStrictModel):
    """A typed evidence projection between a validated source and a claim."""

    schema_version: Literal["InvestmentScoutEvidence/v1"] = "InvestmentScoutEvidence/v1"
    evidence_id: str = Field(min_length=1, max_length=160, pattern=r"^scout-evidence:[a-f0-9]{32}$")
    evidence_type: Literal["source_snapshot"] = "source_snapshot"
    source_id: str = Field(min_length=1, max_length=160, pattern=r"^scout-source:[a-f0-9]{32}$")
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=1, max_length=1200)
    retrieved_at: datetime
    data_state: Literal["observed", "unavailable"] = "observed"

    @field_validator("summary")
    @classmethod
    def sanitize_summary(cls, value: str) -> str:
        return " ".join(value.replace("\x00", " ").split())[:1200]

    @field_validator("retrieved_at")
    @classmethod
    def evidence_timestamp_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Scout evidence timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ScoutClaim(InvestmentStrictModel):
    schema_version: Literal["InvestmentScoutClaim/v1"] = "InvestmentScoutClaim/v1"
    claim_id: str = Field(min_length=1, max_length=160, pattern=r"^scout-claim:[a-f0-9]{32}$")
    kind: ScoutClaimKind
    text: str = Field(min_length=1, max_length=1200)
    source_ids: tuple[str, ...] = Field(default=(), max_length=8)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=8)
    data_state: Literal["observed", "derived", "uncertain", "unavailable"]

    @field_validator("text")
    @classmethod
    def sanitize_claim(cls, value: str) -> str:
        return " ".join(value.replace("\x00", " ").split())[:1200]

    @model_validator(mode="after")
    def source_requirement(self) -> "ScoutClaim":
        if self.kind in {ScoutClaimKind.RETRIEVED_FACT, ScoutClaimKind.DERIVED_OBSERVATION} and (not self.source_ids or not self.evidence_ids):
            raise ValueError("retrieved and derived claims require source and evidence references")
        if self.kind is ScoutClaimKind.UNCERTAINTY and self.data_state != "uncertain":
            raise ValueError("uncertainty claims must be marked uncertain")
        return self


class ScoutSecurityProjection(InvestmentStrictModel):
    schema_version: Literal["InvestmentScoutSecurity/v1"] = "InvestmentScoutSecurity/v1"
    security: SecurityIdentity
    symbol: str = Field(min_length=1, max_length=32)


class ScoutResearchResult(InvestmentStrictModel):
    schema_version: Literal["InvestmentScoutResearchResult/v1"] = "InvestmentScoutResearchResult/v1"
    run_id: str = Field(min_length=1, max_length=160, pattern=r"^scout-run:[a-f0-9]{32}$")
    owner_id: int = Field(gt=0, exclude=True)
    question: str = Field(min_length=1, max_length=500)
    security: ScoutSecurityProjection
    state: ScoutState
    requested_at: datetime
    as_of: datetime
    as_known_at: datetime
    sources: tuple[ScoutSourceRecord, ...] = Field(default=(), max_length=24)
    evidence: tuple[ScoutEvidenceRecord, ...] = Field(default=(), max_length=24)
    claims: tuple[ScoutClaim, ...] = Field(default=(), max_length=48)
    limitations: tuple[str, ...] = Field(default=(), max_length=16)
    warnings: tuple[str, ...] = Field(default=(), max_length=16)
    methodology_version: Literal["ui10-scout-provider-research/v1"] = SCOUT_METHODOLOGY_VERSION
    calculation_version: Literal["ui10-source-normalization/v1"] = SCOUT_CALCULATION_VERSION
    hypothetical: Literal[False] = False
    predictive: Literal[False] = False
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("requested_at", "as_of", "as_known_at")
    @classmethod
    def result_timestamps_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Scout result timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def temporal_contract(self) -> "ScoutResearchResult":
        if self.as_known_at > self.as_of:
            raise ValueError("as_known_at cannot be later than as_of")
        for source in self.sources:
            if source.retrieved_at > self.as_of:
                raise ValueError("source retrieval cannot be later than result as_of")
            if source.publication_at is not None and source.publication_at > self.as_known_at:
                raise ValueError("source publication cannot be later than result as_known_at")
        source_by_id = {source.source_id: source for source in self.sources}
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        for item in self.evidence:
            source = source_by_id.get(item.source_id)
            if source is None or source.source_hash != item.source_hash:
                raise ValueError("evidence references an unknown or mismatched source")
            if item.retrieved_at > self.as_of:
                raise ValueError("evidence retrieval cannot be later than result as_of")
        for claim in self.claims:
            if not set(claim.source_ids).issubset(source_by_id):
                raise ValueError("claim references an unknown source")
            if not set(claim.evidence_ids).issubset(evidence_by_id):
                raise ValueError("claim references unknown evidence")
            if any(evidence_by_id[evidence_id].source_id not in claim.source_ids for evidence_id in claim.evidence_ids):
                raise ValueError("claim evidence must resolve to one of its source references")
        return self

    def canonical_payload(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude={"owner_id", "run_id", "requested_at", "result_hash"}),
            sort_keys=True,
            separators=(",", ":"),
        )

    def with_hash(self) -> "ScoutResearchResult":
        digest = hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()
        return self.model_copy(update={"result_hash": digest, "run_id": f"scout-run:{digest[:32]}"})

    def validate_hash(self) -> None:
        expected = hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()
        if expected != self.result_hash or self.run_id != f"scout-run:{expected[:32]}":
            raise ScoutResearchError("stored Scout result hash validation failed")
        for source in self.sources:
            expected_source_hash = _text_hash({
                key: value
                for key, value in source.model_dump(mode="json").items()
                if key != "source_hash"
            })
            if expected_source_hash != source.source_hash:
                raise ScoutResearchError("stored Scout source hash validation failed")


class ScoutRunSummary(InvestmentStrictModel):
    schema_version: Literal["InvestmentScoutRunSummary/v1"] = "InvestmentScoutRunSummary/v1"
    run_id: str = Field(min_length=1, max_length=160)
    security_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    state: ScoutState
    as_of: datetime
    source_count: int = Field(ge=0, le=24)
    result_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ScoutResearchError(ValueError):
    """Sanitized research availability failure."""


def _text_hash(value: object) -> str:
    def _default(item: object) -> str:
        if isinstance(item, datetime):
            return item.astimezone(UTC).isoformat()
        if isinstance(item, StrEnum):
            return item.value
        return str(item)

    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_default).encode()).hexdigest()


def _safe_source_url(url: str, *, provider: str, source_type: ScoutSourceType) -> str | None:
    """Preserve provider source references without copying credentials."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        return None
    safe_pairs = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = name.casefold().replace("_", "").replace("-", "")
        if any(marker in normalized for marker in ("token", "apikey", "secret", "password", "credential", "authorization")):
            continue
        safe_pairs.append((name, value))
    # The normalized adapters sometimes construct endpoint URLs with the
    # server credential in the query. Strip only that credential; preserve
    # the actual article/reference URL and its non-sensitive parameters.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_pairs), ""))


def _source_id(provider: str, url: str, publication_at: datetime | None, title: str) -> str:
    return f"scout-source:{_text_hash([provider, url, publication_at.isoformat() if publication_at else None, title])[:32]}"


def _claim_id(kind: ScoutClaimKind, text: str, source_ids: tuple[str, ...], evidence_ids: tuple[str, ...]) -> str:
    return f"scout-claim:{_text_hash([kind.value, text, source_ids, evidence_ids])[:32]}"


def _evidence_id(source_id: str, source_hash: str) -> str:
    return f"scout-evidence:{_text_hash([source_id, source_hash])[:32]}"


def _source_from(
    *,
    provider: str,
    source_type: ScoutSourceType,
    url: str,
    title: str,
    publisher: str | None,
    excerpt: str | None,
    publication_at: datetime | None,
    retrieved_at: datetime,
) -> ScoutSourceRecord | None:
    if publication_at is not None and publication_at > retrieved_at:
        return None
    safe_url = _safe_source_url(url, provider=provider, source_type=source_type)
    if safe_url is None:
        return None
    source_id = _source_id(provider, safe_url, publication_at, title)
    provisional = {
        "source_id": source_id,
        "source_type": source_type,
        "provider": provider,
        "source_url": safe_url,
        "title": title,
        "publisher": publisher,
        "excerpt": excerpt,
        "publication_at": publication_at,
        "retrieved_at": retrieved_at,
        "freshness": ScoutFreshness.FRESH,
        "source_hash": "0" * 64,
    }
    source_hash = _text_hash({key: value for key, value in provisional.items() if key != "source_hash"})
    return ScoutSourceRecord(**{**provisional, "source_hash": source_hash})


def _evidence_from(source: ScoutSourceRecord) -> ScoutEvidenceRecord:
    return ScoutEvidenceRecord(
        evidence_id=_evidence_id(source.source_id, source.source_hash),
        source_id=source.source_id,
        source_hash=source.source_hash,
        summary=source.excerpt or source.title,
        retrieved_at=source.retrieved_at,
    )


def _claim(
    kind: ScoutClaimKind,
    text: str,
    source_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    state: Literal["observed", "derived", "uncertain", "unavailable"],
) -> ScoutClaim:
    return ScoutClaim(
        claim_id=_claim_id(kind, text, source_ids, evidence_ids),
        kind=kind,
        text=text,
        source_ids=source_ids,
        evidence_ids=evidence_ids,
        data_state=state,
    )


def _resolve_security(db: Session, owner_id: int, request: ScoutResearchRequest) -> SecurityIdentity:
    requested_id = request.recommendation_id or request.committee_finding_id or request.security_id
    if request.recommendation_id:
        try:
            projection = InvestmentRepository(db).get_recommendation(owner_id=owner_id, recommendation_id=request.recommendation_id)
        except InvestmentRepositoryError as exc:
            raise ScoutResearchError("investment context integrity validation failed") from exc
        if projection is None:
            raise ScoutResearchError("investment research context unavailable")
        requested_id = projection.recommendation.security_id
    elif request.committee_finding_id:
        try:
            finding = InvestmentRepository(db).get_committee_finding_domain(owner_id=owner_id, finding_id=request.committee_finding_id)
        except InvestmentRepositoryError as exc:
            raise ScoutResearchError("investment context integrity validation failed") from exc
        if finding is None:
            raise ScoutResearchError("investment research context unavailable")
        requested_id = finding.subject_security_id

    holdings = db.scalars(
        select(Holding)
        .join(Account, Account.id == Holding.account_id)
        .where(Account.user_id == owner_id, Account.is_active.is_(True))
        .order_by(Holding.account_id.asc(), Holding.id.asc())
    ).all()
    matches: list[SecurityIdentity] = []
    for holding in holdings:
        identity = holding_identity(holding)
        if identity.security_id == requested_id and identity.state is SecurityState.RESOLVED:
            matches.append(identity)
    if len(matches) != 1:
        # Do not reverse-map a ticker or expose whether another owner has a
        # matching security. Ambiguous and non-held identities fail closed.
        raise ScoutResearchError("investment security identity is unavailable or ambiguous")
    return matches[0]


def _provider_failure_message(label: str, result) -> str:
    failure = result.failure
    if failure is None:
        return f"{label} is unavailable."
    return f"{label} is unavailable ({failure.failure_class.value})."


def research_current_security(*, db: Session, owner_id: int, request: ScoutResearchRequest, now: datetime | None = None) -> ScoutResearchResult:
    """Retrieve a bounded, current-context source set for one owner security."""
    if not settings.atlas_investment_scout_external_provider_enabled:
        raise ScoutResearchError("provider-backed Scout research is disabled")
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    security = _resolve_security(db, owner_id, request)
    # The portfolio identity adapter uses a sentinel identity timestamp for
    # legacy holdings. This projection timestamps the server-side resolution
    # event without changing the stable security ID or alias semantics.
    security = security.model_copy(update={"as_of": resolved_now})
    symbol = security.symbol
    if not symbol:
        raise ScoutResearchError("investment security identity is unavailable")

    api_key = (os.environ.get("FINNHUB_API_KEY") or settings.finnhub_api_key or "").strip()
    user_agent = (os.environ.get("SEC_USER_AGENT") or settings.sec_user_agent or "").strip()
    if not api_key and not user_agent:
        raise ScoutResearchError("approved research providers are not configured")

    finnhub = FinnhubAdapter(api_key=api_key, enabled=bool(api_key), now=lambda: resolved_now)
    sec: SecAdapter | None = None
    try:
        if user_agent:
            sec = SecAdapter(user_agent=user_agent, enabled=True, now=lambda: resolved_now)
    except ProviderConfigurationError:
        sec = None

    sources: list[ScoutSourceRecord] = []
    evidence: list[ScoutEvidenceRecord] = []
    claims: list[ScoutClaim] = []
    limitations: list[str] = ["This is current-context research; historical source reconstruction is unavailable."]
    warnings: list[str] = []
    window_start = resolved_now - timedelta(days=14)

    def add_source(source: ScoutSourceRecord | None, claim_text: str | None = None) -> None:
        if source is None:
            warnings.append("A provider record with an invalid or future timestamp was rejected.")
            return
        if source.retrieved_at > resolved_now:
            warnings.append("A provider record with a future retrieval timestamp was rejected.")
            return
        if source.source_id in {item.source_id for item in sources}:
            return
        if len(sources) >= request.max_sources:
            return
        sources.append(source)
        source_evidence = _evidence_from(source)
        evidence.append(source_evidence)
        if claim_text:
            claims.append(_claim(ScoutClaimKind.RETRIEVED_FACT, claim_text, (source.source_id,), (source_evidence.evidence_id,), "observed"))

    news_result = finnhub.company_news(symbol, from_date=window_start.date().isoformat(), to_date=resolved_now.date().isoformat())
    if news_result.value:
        for item in news_result.value[: request.max_sources]:
            source = _source_from(
                provider="finnhub",
                source_type=ScoutSourceType.COMPANY_NEWS,
                url=item.source.source_url,
                title=item.headline,
                publisher=item.publisher,
                excerpt=item.summary,
                publication_at=item.source.published_at,
                retrieved_at=item.source.retrieved_at,
            )
            add_source(source, item.headline)
    else:
        limitations.append(_provider_failure_message("Company news", news_result))

    earnings_result = finnhub.earnings_calendar(symbol)
    if earnings_result.value:
        for event in earnings_result.value[: request.max_sources]:
            text = f"Earnings calendar event for {event.symbol} on {event.event_date.date().isoformat()}."
            source = _source_from(
                provider="finnhub",
                source_type=ScoutSourceType.EARNINGS,
                url=event.source.source_url,
                title="Earnings calendar event",
                publisher="Finnhub",
                excerpt=text,
                publication_at=event.source.published_at,
                retrieved_at=event.source.retrieved_at,
            )
            add_source(source, text)
    else:
        limitations.append(_provider_failure_message("Earnings calendar", earnings_result))

    profile_result = finnhub.company_profile(symbol)
    cik: str | None = None
    if profile_result.value:
        profile = profile_result.value
        cik = profile.cik
        profile_text = f"Provider profile identifies {symbol}" + (f" as {profile.company_name}." if profile.company_name else ".")
        source = _source_from(
            provider="finnhub",
            source_type=ScoutSourceType.COMPANY_PROFILE,
            url=profile.source.source_url,
            title=profile.company_name or f"{symbol} company profile",
            publisher=profile.exchange,
            excerpt=profile_text,
            publication_at=profile.source.published_at,
            retrieved_at=profile.source.retrieved_at,
        )
        add_source(source, profile_text)
    else:
        limitations.append(_provider_failure_message("Company profile", profile_result))

    if sec is not None and cik:
        filings_result = sec.submissions(cik)
        if filings_result.value:
            for filing in filings_result.value[: request.max_sources]:
                filing_text = f"SEC {filing.form} filing {filing.accession_number} dated {filing.filing_date.date().isoformat()}."
                source = _source_from(
                    provider="sec",
                    source_type=ScoutSourceType.SEC_FILING,
                    url=filing.source.source_url,
                    title=f"SEC {filing.form} filing {filing.accession_number}",
                    publisher="SEC",
                    excerpt=filing_text,
                    publication_at=filing.filing_date,
                    retrieved_at=filing.source.retrieved_at,
                )
                add_source(source, filing_text)
        else:
            limitations.append(_provider_failure_message("SEC filings", filings_result))
    elif not cik:
        limitations.append("SEC filings are unavailable because no provider-supplied CIK was resolved.")
    elif sec is None:
        limitations.append("SEC filings are unavailable because the server-side SEC contact configuration is missing.")

    sources.sort(key=lambda item: (item.publication_at or item.retrieved_at, item.source_id), reverse=True)
    evidence.sort(key=lambda item: item.evidence_id)
    claims.sort(key=lambda item: item.claim_id)
    unavailable_limitations = tuple(
        item for item in limitations
        if not item.startswith("This is current-context")
        and ("unavailable" in item.casefold() or "missing" in item.casefold() or "failed" in item.casefold())
    )
    if not sources:
        state = ScoutState.UNAVAILABLE
    elif warnings or unavailable_limitations:
        state = ScoutState.PARTIAL
    else:
        state = ScoutState.READY
    result = ScoutResearchResult(
        run_id="scout-run:" + "0" * 32,
        owner_id=owner_id,
        question=request.question,
        security=ScoutSecurityProjection(security=security, symbol=symbol),
        state=state,
        requested_at=resolved_now,
        as_of=resolved_now,
        as_known_at=resolved_now,
        sources=tuple(sources[: request.max_sources]),
        evidence=tuple(evidence[: request.max_sources]),
        claims=tuple(claims),
        limitations=tuple(dict.fromkeys(limitations)),
        warnings=tuple(dict.fromkeys(warnings)),
        result_hash="0" * 64,
    )
    return result.with_hash()


def load_scout_run(db: Session, *, owner_id: int, run_id: str) -> ScoutResearchResult | None:
    from app.models.investment_scout import InvestmentScoutRun

    row = db.scalar(select(InvestmentScoutRun).where(InvestmentScoutRun.owner_id == owner_id, InvestmentScoutRun.run_id == run_id))
    if row is None:
        return None
    try:
        payload = json.loads(row.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("Scout payload must be an object")
        payload["owner_id"] = row.owner_id
        result = ScoutResearchResult.model_validate(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ScoutResearchError("stored Scout result is invalid") from exc
    if result.result_hash != row.result_hash or result.run_id != row.run_id or result.security.security.security_id != row.security_id:
        raise ScoutResearchError("stored Scout result integrity validation failed")
    result.validate_hash()
    return result


def persist_scout_result(db: Session, result: ScoutResearchResult) -> tuple[ScoutResearchResult, bool]:
    """Insert a result once; replay identical owner-scoped requests safely."""
    from sqlalchemy.exc import IntegrityError
    from app.models.investment_scout import InvestmentScoutRun

    result.validate_hash()
    row = db.scalar(select(InvestmentScoutRun).where(
        InvestmentScoutRun.owner_id == result.owner_id,
        InvestmentScoutRun.run_id == result.run_id,
    ))
    if row is not None:
        existing = load_scout_run(db, owner_id=result.owner_id, run_id=result.run_id)
        if existing is None or existing.result_hash != result.result_hash:
            raise ScoutResearchError("stored Scout result conflicts with the requested result")
        return existing, True
    row = InvestmentScoutRun(
        owner_id=result.owner_id,
        run_id=result.run_id,
        security_id=result.security.security.security_id,
        symbol=result.security.symbol,
        requested_at=result.requested_at,
        as_of=result.as_of,
        result_hash=result.result_hash,
        payload_json=result.model_dump_json(exclude={"owner_id"}),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = load_scout_run(db, owner_id=result.owner_id, run_id=result.run_id)
        if existing is None or existing.result_hash != result.result_hash:
            raise ScoutResearchError("Scout result persistence conflict") from exc
        return existing, True
    db.refresh(row)
    return result, False


def list_scout_runs(db: Session, *, owner_id: int, limit: int = 20) -> list[ScoutRunSummary]:
    from app.models.investment_scout import InvestmentScoutRun

    rows = db.scalars(
        select(InvestmentScoutRun)
        .where(InvestmentScoutRun.owner_id == owner_id)
        .order_by(InvestmentScoutRun.as_of.desc(), InvestmentScoutRun.id.desc())
        .limit(min(max(limit, 1), 50))
    ).all()
    summaries: list[ScoutRunSummary] = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json)
            if not isinstance(payload, dict):
                raise ValueError("Scout payload must be an object")
            # Owner scope is intentionally excluded from the persisted public
            # payload; restore it only for strict server-side validation.
            payload["owner_id"] = row.owner_id
            result = ScoutResearchResult.model_validate(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ScoutResearchError("stored Scout result is invalid") from exc
        if result.run_id != row.run_id or result.result_hash != row.result_hash:
            raise ScoutResearchError("stored Scout summary integrity validation failed")
        summaries.append(ScoutRunSummary(run_id=row.run_id, security_id=row.security_id, symbol=row.symbol, state=result.state, as_of=row.as_of, source_count=len(result.sources), result_hash=row.result_hash))
    return summaries


__all__ = [
    "SCOUT_CALCULATION_VERSION", "SCOUT_METHODOLOGY_VERSION", "ScoutClaim", "ScoutClaimKind", "ScoutEvidenceRecord",
    "ScoutFreshness", "ScoutResearchError", "ScoutResearchRequest", "ScoutResearchResult",
    "ScoutRunSummary", "ScoutSecurityProjection", "ScoutSourceRecord", "ScoutSourceType",
    "ScoutState", "list_scout_runs", "load_scout_run", "research_current_security",
]
