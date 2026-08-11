"""Fake-only, privacy-safe briefing email projection and delivery contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import re
from typing import Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

from .briefing import MarketBrief


@dataclass(frozen=True)
class DeliveryProjection:
    subject: str
    summary: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    delays_seconds: tuple[float, ...] = (0.0, 0.1, 0.2)
    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3 or len(self.delays_seconds) != self.max_attempts or any(delay < 0 or delay > 1 for delay in self.delays_seconds):
            raise ValueError("retry policy must be bounded to three sandbox attempts")


def project_for_email(brief: MarketBrief) -> DeliveryProjection:
    """Exclude owner/internal identifiers, hashes, and detailed dollar values."""
    summary = "Your market briefing is ready for secure in-app review."
    urls = tuple(urlunsplit((*urlsplit(c.source_url)[:3], "", "")) for section in brief.sections for c in section.citations)
    return DeliveryProjection(subject="Atlas market briefing", summary=summary, source_urls=tuple(dict.fromkeys(urls)))


def render_plaintext(projection: DeliveryProjection) -> str:
    sources = "\n".join(f"Source: {url}" for url in projection.source_urls)
    return f"{projection.subject}\n\n{projection.summary}" + (f"\n\n{sources}" if sources else "")


def render_html(projection: DeliveryProjection) -> str:
    links = "".join(f'<li><a href="{escape(url, quote=True)}">Source</a></li>' for url in projection.source_urls)
    return f"<h1>{escape(projection.subject)}</h1><p>{escape(projection.summary)}</p>" + (f"<ul>{links}</ul>" if links else "")


class EmailAdapter(Protocol):
    def send(self, *, idempotency_key: str, projection: DeliveryProjection) -> str: ...


@dataclass
class FakeEmailAdapter:
    sent: dict[str, DeliveryProjection] = field(default_factory=dict)

    def send(self, *, idempotency_key: str, projection: DeliveryProjection) -> str:
        self.sent.setdefault(idempotency_key, projection)
        return f"fake-receipt-{idempotency_key}"


class ResendEmailAdapter:
    """Explicitly injected transport; never reads env, SDKs, or opens sockets itself."""
    def __init__(self, *, enabled: bool = False, api_key: str | None = None,
                 recipient: str | None = None,
                 transport: Callable[[str, dict[str, object]], dict[str, object]] | None = None) -> None:
        self.enabled, self._api_key, self._recipient, self._transport = enabled, (api_key or "").strip(), (recipient or "").strip(), transport

    def send(self, *, idempotency_key: str, projection: DeliveryProjection,
             secure_link: str | None = None) -> str:
        if (not self.enabled or not self._api_key or not self._recipient or
                not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self._recipient) or
                self._transport is None or not secure_link or not secure_link.startswith("https://")):
            raise RuntimeError("Email delivery is disabled or incomplete; preview only.")
        # Keep the vendor payload intentionally narrower than the in-app brief.
        payload: dict[str, object] = {
            "to": [self._recipient],
            "subject": projection.subject,
            "text": f"{projection.summary}\n\nView securely: {secure_link}",
        }
        response = self._transport(self._api_key, payload)
        receipt = response.get("id")
        if not isinstance(receipt, str) or not receipt:
            raise RuntimeError("Email provider returned an invalid receipt.")
        return receipt
