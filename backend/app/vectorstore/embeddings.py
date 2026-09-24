"""Embeddings for the guideline search.

"ollama" uses a real embedding model. "hashing" is a feature-hashing
bag-of-words that needs nothing installed. It's noticeably dumber than a
real model but it's deterministic, so tests and offline demos use it.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.agent.providers.base import LLMProvider

_TOKEN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+|\d+")


class Embedder(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    def __init__(self, dim: int = 384):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class ProviderEmbedder:
    def __init__(self, provider: LLMProvider, model: str, dim: int):
        self.provider = provider
        self.model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await self.provider.embed(texts, model=self.model)
        if vectors and len(vectors[0]) != self.dim:
            raise ValueError(
                f"{self.model} returns {len(vectors[0])}-d vectors but embeddings.dim is {self.dim}. "
                "Fix EMBEDDINGS__DIM to match the model."
            )
        return vectors


def chunk_text(text: str, *, size: int = 900, overlap: int = 150) -> list[str]:
    """Split on line boundaries into roughly size-char chunks with some overlap,
    so a rule that straddles two chunks still shows up whole in one of them."""
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""
    for line in lines:
        if len(line) > size and current.strip():
            chunks.append(current)
            current = ""
        while len(line) > size:  # one absurdly long line, just hard-split it
            chunks.append(line[:size])
            line = line[size - overlap:]
        if len(current) + len(line) > size and current:
            chunks.append(current)
            current = current[-overlap:] if overlap else ""
        current += line
    if current.strip():
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]
