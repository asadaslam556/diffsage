"""Vector storage for uploaded guidelines.

Qdrant in docker, talked to over its REST API (no SDK needed). The
in-memory version is for tests. Every point carries user_id in its payload
and every search filters on it; one user can never see another's docs.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass
class VectorHit:
    text: str
    score: float
    filename: str
    document_id: str


class VectorStoreError(Exception):
    pass


class VectorStore(Protocol):
    async def ensure_ready(self) -> None: ...
    async def upsert(self, user_id: str, document_id: str, filename: str, chunks: list[str], vectors: list[list[float]]) -> None: ...
    async def search(self, user_id: str, vector: list[float], limit: int) -> list[VectorHit]: ...
    async def delete_document(self, user_id: str, document_id: str) -> None: ...
    async def health(self) -> tuple[bool, str]: ...


class QdrantStore:
    def __init__(self, base_url: str, collection: str, dim: int, api_key: str | None = None, client: Any = None):
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.dim = dim
        self.headers = {"api-key": api_key} if api_key else {}
        self._client = client
        self._ready = False

    @property
    def client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=10.0)
        return self._client

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        import httpx

        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"qdrant unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise VectorStoreError(f"qdrant {method} {path} -> {response.status_code}: {response.text[:200]}")
        return response.json()

    async def ensure_ready(self) -> None:
        if self._ready:
            return
        import httpx

        try:
            response = await self.client.get(f"/collections/{self.collection}")
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"qdrant unreachable: {exc.__class__.__name__}") from exc
        if response.status_code == 404:
            await self._call("PUT", f"/collections/{self.collection}", json={"vectors": {"size": self.dim, "distance": "Cosine"}})
            # filtering by user on every search, so index it
            await self._call(
                "PUT", f"/collections/{self.collection}/index",
                json={"field_name": "user_id", "field_schema": "keyword"},
            )
            log.info("created qdrant collection %s (dim=%d)", self.collection, self.dim)
        elif response.status_code >= 400:
            raise VectorStoreError(f"qdrant collection check failed: {response.status_code}")
        self._ready = True

    async def upsert(self, user_id: str, document_id: str, filename: str, chunks: list[str], vectors: list[list[float]]) -> None:
        await self.ensure_ready()
        points = [
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{i}")),
                "vector": vec,
                "payload": {"user_id": user_id, "document_id": document_id, "filename": filename, "text": chunk},
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True))
        ]
        await self._call("PUT", f"/collections/{self.collection}/points?wait=true", json={"points": points})

    async def search(self, user_id: str, vector: list[float], limit: int) -> list[VectorHit]:
        await self.ensure_ready()
        data = await self._call(
            "POST", f"/collections/{self.collection}/points/search",
            json={
                "vector": vector,
                "limit": limit,
                "with_payload": True,
                "filter": {"must": [{"key": "user_id", "match": {"value": user_id}}]},
            },
        )
        return [
            VectorHit(p["payload"]["text"], float(p["score"]), p["payload"]["filename"], p["payload"]["document_id"])
            for p in data.get("result", [])
        ]

    async def delete_document(self, user_id: str, document_id: str) -> None:
        await self.ensure_ready()
        await self._call(
            "POST", f"/collections/{self.collection}/points/delete?wait=true",
            json={"filter": {"must": [
                {"key": "user_id", "match": {"value": user_id}},
                {"key": "document_id", "match": {"value": document_id}},
            ]}},
        )

    async def health(self) -> tuple[bool, str]:
        try:
            await self._call("GET", "/collections")
        except VectorStoreError as exc:
            return False, str(exc)
        return True, ""

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


class MemoryVectorStore:
    def __init__(self) -> None:
        self.points: list[dict[str, Any]] = []
        self.healthy = True

    async def ensure_ready(self) -> None:
        return None

    async def upsert(self, user_id: str, document_id: str, filename: str, chunks: list[str], vectors: list[list[float]]) -> None:
        for chunk, vec in zip(chunks, vectors, strict=True):
            self.points.append({"user_id": user_id, "document_id": document_id, "filename": filename, "text": chunk, "vector": vec})

    async def search(self, user_id: str, vector: list[float], limit: int) -> list[VectorHit]:
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b, strict=True))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(y * y for y in b)) or 1.0
            return dot / (na * nb)

        scored = [
            VectorHit(p["text"], cosine(vector, p["vector"]), p["filename"], p["document_id"])
            for p in self.points if p["user_id"] == user_id
        ]
        return sorted(scored, key=lambda h: h.score, reverse=True)[:limit]

    async def delete_document(self, user_id: str, document_id: str) -> None:
        self.points = [p for p in self.points if not (p["user_id"] == user_id and p["document_id"] == document_id)]

    async def health(self) -> tuple[bool, str]:
        return (True, "") if self.healthy else (False, "memory store marked unhealthy")
