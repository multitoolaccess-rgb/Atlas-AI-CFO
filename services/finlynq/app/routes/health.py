"""Finlynq /health endpoint.

Phase F1 ship target:
- 200 on ``GET /health`` always (no DB hit).
- Response shape identifies the service so a dashboard / monitoring
  layer can disambiguate from rules-service's /health route.

The contract test ``services/finlynq/tests/test_health.py`` pins:
- HTTP 200.
- Response body is JSON with the four keys below.
- ``service == "finlynq"`` and ``version`` matches ``settings.app_version``
  so a future rolldown of Finlynq is observable from the wire.
"""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe. No DB hit. Phase F2a adds a DB-liveness sub-route
    once both services share the engine — see TODO marker in app/main.py.
    """
    return {
        "status": "healthy",
        "service": "finlynq",
        "version": settings.app_version,
        "role": "canonical-store",
    }
