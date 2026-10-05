"""How the agent's tools call back into the platform.

This is the "agent may call again" arrow in the architecture diagram. Tools
don't reach into the database directly; they go back through the gateway
with a short-lived token scoped to the user, so the same auth, routing and
rate limits apply to the agent as to the browser. A fresh token is minted
for every call: a review on a slow CPU can run longer than any one token.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.core.logging import request_id_var

if TYPE_CHECKING:
    import httpx

log = logging.getLogger(__name__)


class GatewayCallError(Exception):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class GatewayClient:
    def __init__(
        self, base_url: str, mint_token: Callable[[], str], *,
        transport: "httpx.AsyncBaseTransport | None" = None, timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.mint_token = mint_token
        self.transport = transport
        self.timeout = timeout

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        import httpx

        headers = {
            "authorization": f"Bearer {self.mint_token()}",
            # keep the parent request id so the internal hop shows up in the same log trail
            "x-request-id": request_id_var.get(),
        }
        try:
            async with httpx.AsyncClient(base_url=self.base_url, transport=self.transport, timeout=self.timeout) as client:
                response = await client.get(path, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise GatewayCallError(None, f"gateway unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text[:200]
            raise GatewayCallError(response.status_code, message)
        return response.json()
