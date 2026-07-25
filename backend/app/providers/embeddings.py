"""OpenAI-compatible embedding client (Nebius, OpenAI, …)."""
from __future__ import annotations

from ..core.config import get_settings


class OpenAICompatEmbedding:
    name = "openai"

    def __init__(self) -> None:
        from langchain_openai import OpenAIEmbeddings

        s = get_settings()
        self._emb = OpenAIEmbeddings(
            model=s.embedding_model,
            base_url=s.embedding_base_url,
            api_key=s.embedding_api_key,
            check_embedding_ctx_length=False,
            # A finite request timeout + bounded retries so a stalled provider surfaces as an
            # error (→ keyword fallback) instead of hanging ingestion indefinitely.
            timeout=90,
            max_retries=2,
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return await self._emb.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self._emb.aembed_query(text)
