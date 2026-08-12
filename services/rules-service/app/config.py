"""Application settings loaded from environment variables.

Lift provenance: lifted essentially verbatim from the legacy WealthIQ settings
module in Phase 2 of the merge plan
(See ``docs/wealthiq-merge-plan.md`` §4 — Reuse Map, item 1).

Adapts applied:

- ``app_name`` default: ``"WealthIQ"`` → ``"Finance Copilot"`` (project rename).
- New ``local_user: str = "alex"`` field — single-user auth contract per
  ``docs/wealthiq-merge-plan.md`` §10 decision 4. ``app/auth.py`` validates the
  JWT signer's ``sub`` claim against this field.

Env precedence: ``os.environ`` via ``pydantic_settings.BaseSettings``; a
``services/rules-service/.env`` file (if present) is loaded but optional
(``env_file=None`` in tests via ``Settings(_env_file=None)`` to be hermetic).
"""
from typing import Optional

from pydantic import ConfigDict, model_validator
from pydantic_settings import BaseSettings  # noqa: F401 (re-exported for app.routes.* consumers)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://wealthiq:wealthiq@localhost:5432/wealthiq"

    # Application
    environment: str = "development"
    app_name: str = "Finance Copilot"
    app_version: str = "0.1.0"
    local_user: str = "alex"  # Single-user auth (§10 decision 4)

    # Security
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Plaid (optional — canonical ingest path per §10 decision 1)
    plaid_client_id: Optional[str] = None
    plaid_secret: Optional[str] = None
    plaid_env: str = "sandbox"

    # Phase-F3 — Finlynq cross-service URL. The 5-line httpx
    # forwarder at ``POST /api/imports/upload`` POSTs the multipart
    # upload to this URL and re-emits the response. Override via
    # env (``FINLYNQ_BASE_URL``) in CI / docker-compose where
    # Finlynq lives behind a hostname.
    finlynq_base_url: str = "http://localhost:8001"

    # Phase 9 / Phase 39.2 — Finnhub free-tier API key for
    # ``GET /api/analyst-ratings/{ticker}`` and the
    # ``POST /api/holdings/refresh-prices`` caller. pydantic-settings
    # reads ``services/rules-service/.env`` (via ``env_file=".env"``)
    # at instantiation, so a developer who pastes their key into the
    # .env file is wired up automatically on the next ``uvicorn``
    # cold-start — no shell ``export FINNHUB_API_KEY=...`` required.
    #
    # Routes should read this via the ``os.environ OR settings``
    # fallback chain — see Phase 39.2 comment in
    # ``app/routes/analyst_ratings.py`` and ``app/routes/holdings.py``.
    finnhub_api_key: Optional[str] = None
    # Phase 5 operational market-brief composition requires an SEC-compliant
    # contact User-Agent even though filing enrichment is skipped when a
    # holding has no authoritative CIK.  This value is server-only and must
    # never be supplied by a browser request.
    sec_user_agent: Optional[str] = None
    # Phase 1 forecast persistence flag (default off)
    atlas_forecast_persistence_enabled: bool = False
    # Phase 1 read-API flag (default off — peer to the persistence flag).
    # Strict default-off + case-insensitive env binding via pydantic-settings.
    # NO client-side override point: this lives only in the server Settings
    # base class; route layers MUST reject requests when this is False.
    atlas_forecast_read_api_enabled: bool = False
    # Phase 4 history API is a separate, server-only default-off rollout gate.
    atlas_decision_history_api_enabled: bool = False
    # Phase 5 market-intelligence controls are server-owned rollout gates.
    # No request, client bundle, or provider response can override them.
    atlas_market_brief_generation_enabled: bool = False
    atlas_market_brief_read_api_enabled: bool = False
    atlas_market_brief_external_provider_enabled: bool = False
    atlas_market_brief_email_delivery_enabled: bool = False
    atlas_market_brief_scheduler_enabled: bool = False
    atlas_market_brief_local_summarization_enabled: bool = False

    model_config = ConfigDict(extra="ignore", env_file=".env", case_sensitive=False)

    @model_validator(mode="after")
    def _refuse_dev_secret_in_non_development(self) -> "Settings":
        """Hardening raised by Phase 2 code-review: refuse the dev-default ``jwt_secret``
        in any non-``development`` environment so a misconfigured prod deploy fails
        loudly at startup instead of silently minting tokens a public attacker can forge.
        """
        if (
            self.environment != "development"
            and self.jwt_secret == "dev-secret-change-in-production"
        ):
            raise ValueError(
                "JWT_SECRET must be overridden in non-development environments; "
                "default 'dev-secret-change-in-production' is rejected."
            )
        return self


settings = Settings()
