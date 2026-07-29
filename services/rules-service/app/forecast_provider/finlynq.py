"""Narrow Rules-to-Finlynq B0 adapter; generic state endpoints are forbidden."""
from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.forecasts.canonical_state import CanonicalProjectionState, FinlynqProjectionStateAdapter


class _HttpClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response: ...


class FinlynqProjectionProviderError(RuntimeError):
    """Safe adapter failure; response bodies and financial state are not retained."""


class HttpFinlynqProjectionStateAdapter(FinlynqProjectionStateAdapter):
    """Call exactly the B0 provider endpoint once using existing bearer auth."""

    def __init__(self, *, base_url: str, authorization: str, client: _HttpClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._authorization = authorization
        self._client = client or httpx.Client()

    def load_projection_state(self, *, user_id: str, goal_id: int) -> CanonicalProjectionState:
        if not isinstance(goal_id, int) or goal_id <= 0 or not self._authorization.startswith("Bearer "):
            raise FinlynqProjectionProviderError("projection_state_unavailable")
        response = self._client.get(
            f"{self._base_url}/projection-state/goals/{goal_id}",
            headers={"Authorization": self._authorization},
            timeout=5.0,
        )
        if response.status_code in {401, 404, 422}:
            raise FinlynqProjectionProviderError("projection_state_unavailable")
        if response.status_code != 200:
            raise FinlynqProjectionProviderError("projection_state_unavailable")
        try:
            state = CanonicalProjectionState.model_validate(response.json())
        except Exception as exc:
            raise FinlynqProjectionProviderError("projection_state_unavailable") from None
        if state.user_id != user_id or state.goal_id != goal_id:
            raise FinlynqProjectionProviderError("projection_state_unavailable")
        return state
