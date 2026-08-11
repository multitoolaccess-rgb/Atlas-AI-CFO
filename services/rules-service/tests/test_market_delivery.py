from datetime import UTC, datetime

from app.market_intelligence.briefing import BriefingInput, DeterministicTemplateProvider
from app.market_intelligence.briefing import PositionInput
from app.market_intelligence.contracts import SourceMetadata
import pytest
from app.market_intelligence.delivery import FakeEmailAdapter, ResendEmailAdapter, RetryPolicy, project_for_email, render_html, render_plaintext
from app.market_intelligence.cli import main


def test_fake_delivery_is_idempotent_and_projection_is_private() -> None:
    brief = DeterministicTemplateProvider().generate(BriefingInput(owner_id=99, portfolio_state_hash="a" * 64, universe_hash="b" * 64, report_window="2026-08-10", positions=[], generated_at=datetime(2026, 8, 10, tzinfo=UTC)))
    projection = project_for_email(brief)
    assert "99" not in render_plaintext(projection)
    assert "aaaa" not in render_html(projection)
    fake = FakeEmailAdapter()
    assert fake.send(idempotency_key="brief-1", projection=projection) == fake.send(idempotency_key="brief-1", projection=projection)
    assert len(fake.sent) == 1


def test_cli_send_is_always_fail_closed(monkeypatch, capsys) -> None:
    from app.config import settings
    monkeypatch.setattr(settings, "atlas_market_brief_email_delivery_enabled", False)
    assert main(["send"]) == 2
    assert "preview-only" in capsys.readouterr().out


def test_cli_preview_and_generation_flags(monkeypatch, capsys) -> None:
    from app.config import settings
    assert main(["preview"]) == 0
    monkeypatch.setattr(settings, "atlas_market_brief_generation_enabled", False)
    assert main(["generate"]) == 2
    assert "unavailable" in capsys.readouterr().out


def test_delivery_contracts_bound_retry_escape_and_never_network() -> None:
    assert RetryPolicy().max_attempts == 3
    with pytest.raises(ValueError): RetryPolicy(max_attempts=4, delays_seconds=(0, 0, 0, 0))
    projection = type("Projection", (), {"subject": "<unsafe>", "summary": "&", "source_urls": ("https://example.test/a?safe=1#fragment",)})()
    assert "&lt;unsafe&gt;" in render_html(projection)
    with pytest.raises(RuntimeError, match="disabled"):
        ResendEmailAdapter().send(idempotency_key="x", projection=projection)


def test_resend_requires_explicit_injected_transport_and_sends_private_projection() -> None:
    projection = type("Projection", (), {"subject": "Atlas market briefing", "summary": "Secure summary", "source_urls": ("https://source.test",)})()
    calls: list[tuple[str, dict[str, object]]] = []
    def transport(key: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((key, payload)); return {"id": "sandbox-receipt"}
    with pytest.raises(RuntimeError):
        ResendEmailAdapter(enabled=True, api_key="key", recipient="owner@example.test").send(idempotency_key="x", projection=projection, secure_link="https://app.test/brief/1")
    receipt = ResendEmailAdapter(enabled=True, api_key="key", recipient="owner@example.test", transport=transport).send(idempotency_key="x", projection=projection, secure_link="https://app.test/brief/1")
    assert receipt == "sandbox-receipt" and calls[0][0] == "key"
    assert calls[0][1] == {"to": ["owner@example.test"], "subject": "Atlas market briefing", "text": "Secure summary\n\nView securely: https://app.test/brief/1"}


def test_email_projection_strips_source_query_and_fragment() -> None:
    source = SourceMetadata(provider="synthetic", source_url="https://example.test/report?context=private", retrieved_at=datetime(2026, 8, 10, tzinfo=UTC))
    brief = DeterministicTemplateProvider().generate(BriefingInput(owner_id=1, portfolio_state_hash="c" * 64, universe_hash="d" * 64, report_window="2026-08-10", positions=[PositionInput(symbol="AAPL", quantity="1", current_price="2", previous_close="1", currency="USD", source=source)], generated_at=datetime(2026, 8, 10, tzinfo=UTC)))
    assert project_for_email(brief).source_urls == ("https://example.test/report",)


def test_delivery_preferences_are_owner_scoped(db_session) -> None:
    from app.market_intelligence.delivery_repository import DeliveryRepository
    from app.models import User
    from app.models.market_brief_delivery import MarketBriefDeliveryPreference
    db_session.add_all((User(local_user_sub="delivery-one", email="delivery-one@test", hashed_password="x"), User(local_user_sub="delivery-two", email="delivery-two@test", hashed_password="x")))
    db_session.commit()
    users = {user.local_user_sub: user for user in db_session.query(User).filter(User.local_user_sub.in_(("delivery-one", "delivery-two"))).all()}
    one, two = users["delivery-one"], users["delivery-two"]
    db_session.add(MarketBriefDeliveryPreference(user_id=one.id, email_authorized=True)); db_session.commit()
    repository = DeliveryRepository(db_session)
    assert repository.preference(one.id).email_authorized is True
    assert repository.preference(two.id) is None
