"""Phase F1 contract: GET /health must respond 200 with stable shape.

The Phase F1 ship target: Finlynq's HTTP shell is up and identifiable
from a /health probe. Monitoring / dashboard / dev tooling can hit it
without spinning up the parser or categorizer (F3-F5 deferred work).

What this test locks:
- HTTP 200 on GET /health.
- Response carries ``status=healthy``.
- Response carries ``service=finlynq`` so a multi-service probe
  disambiguates from rules-service's /health (also 200 + ``status``
  but missing ``service``). The dashboard / scripts/watchdog keys off
  this string.
- Response carries ``version`` (any non-empty string).
"""
from app.config import settings


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200, (
        f"GET /health must return 200 (got {response.status_code}); "
        f"Finlynq's HTTP shell MUST be up before any F3-F5 work begins."
    )


def test_health_payload_shape(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    # The four keys below form the immutable contract from Phase F1
    # onward. Adding keys is fine; removing them breaks the
    # cross-service probe disambiguation.
    for key in ("status", "service", "version", "role"):
        assert key in body, f"/health response missing required key {key!r}: {body!r}"
    assert body["status"] == "healthy"
    assert body["service"] == "finlynq", (
        "service field MUST be 'finlynq' so multi-service monitors can "
        f"disambiguate from rules-service (got {body['service']!r})."
    )
    assert isinstance(body["version"], str) and body["version"], (
        f"version must be a non-empty string (got {body['version']!r})"
    )
    # Loose-equality on version: a release bumps it from 0.2.0 to 0.3.0;
    # F1-shipped tests should pass against any forward-compatible release.
    assert body["version"] == settings.app_version, (
        f"/health version {body['version']!r} must match "
        f"settings.app_version {settings.app_version!r}"
    )
    assert body["role"] == "canonical-store", (
        f"role field MUST be 'canonical-store' to document Finlynq's "
        f"architecture role per docs/master-plan.md end-state vision "
        f"(got {body['role']!r})."
    )
