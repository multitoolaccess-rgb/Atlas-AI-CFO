"""Finlynq application settings.

Phase F1 (per docs/master-plan.md end-state vision):

- Finlynq is the canonical source of truth for portfolio + transactions.
- rules-service becomes a passthrough reader (Phase F5) once Finlynq lands.
- Both services share the SAME ``JWT_SECRET`` so the ``fc_session`` cookie
  minted by rules-service's ``POST /api/auth/devlogin`` is accepted by
  Finlynq's ``Depends(require_user)`` dep. This MUST be locked in by an
  integration test (Phase F6) before F5 ships.

Mirrors services/rules-service/app/config.py verbatim — same JWT
contract, same SINGLE_USER (defaults to ``alex``), same prod-refuse-dev-secret
validator. Differences:
- ``app_name`` stays ``"Finance Copilot"`` but the token's ``iss`` claim is
  identical so a single devlogin cookie works against both services. (If
  you want different ``iss`` per service, change this AND rules-service
  carefully — the cookie minted by one is rejected by the other.)
- ``finlynq.version`` is bumped to ``0.2.0`` from rules-service's ``0.1.0``
  so the response shape on ``GET /health`` differentiates the two.
"""
from pathlib import Path
from typing import Optional

from pydantic import ConfigDict, model_validator
from pydantic_settings import BaseSettings


FINLYNQ_SERVICE_DIR = Path(__file__).resolve().parents[1]
FINLYNQ_SERVICE_ENV_FILE = FINLYNQ_SERVICE_DIR / ".env"


class Settings(BaseSettings):
    # Database — Phase F2a points this at the SAME engine rules-service
    # uses, owned by the project-root ``finance.db`` SQLite in dev or
    # the shared wealthiq Postgres elsewhere. Future phases can split.
    database_url: str = "sqlite:///./finance.db"

    # Application
    environment: str = "development"
    app_name: str = "Finance Copilot"
    app_version: str = "0.2.0"  # Bumped — Finlynq is the new canonical layer.
    # Phase F2a note: ``local_user`` MUST match rules-service's, otherwise
    # the JWT minted by /api/auth/devlogin is rejected by Finlynq's
    # require_user dep. The integration test in tests/test_auth_contract.py
    # pins this cross-service invariant.
    local_user: str = "alex"

    # Security — must match rules-service so the same devlogin cookie
    # travels between services without re-auth.
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8001  # 8000 is rules-service; 3000 is the Next.js UI.

    model_config = ConfigDict(
        extra="ignore",
        env_file=FINLYNQ_SERVICE_ENV_FILE,
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def _refuse_dev_secret_in_non_development(self) -> "Settings":
        """Refuse the dev-default ``jwt_secret`` outside development — same
        hardening as ``rules-service/app/config.py``. Prevents a misdeployed
        prod Finlynq from silently accepting tokens forged with the public
        dev secret.
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
