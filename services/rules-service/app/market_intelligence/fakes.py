"""Deterministic provider fake for unit tests and local certification."""
from __future__ import annotations

from collections.abc import Mapping

import httpx


class SyntheticMarketTransport(httpx.MockTransport):
    """Route exact paths to synthetic JSON; unknown calls fail closed as 404."""
    def __init__(self, payloads: Mapping[str, object]) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = payloads.get(request.url.path)
            if payload is None:
                return httpx.Response(404, json={"synthetic": "not_found"})
            return httpx.Response(200, json=payload)
        super().__init__(handler)
