"""Web-search providers: Exa + You.com."""
from __future__ import annotations

import httpx

from ..core.config import get_settings

# Search API host (see you.com docs). Legacy api.you.com/v1/search returns 405.
_YOUCOM_URL = "https://ydc-index.io/v1/search"


class ExaSearch:
    name = "exa"

    def __init__(self) -> None:
        self.s = get_settings()

    async def search(self, query: str, n: int = 5) -> list[dict]:
        if not self.s.exa_api_key:
            raise RuntimeError("EXA_API_KEY not set")
        headers = {"x-api-key": self.s.exa_api_key, "content-type": "application/json"}
        body = {
            "query": query,
            "numResults": n,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 800}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.exa.ai/search", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        return [
            {"title": x.get("title", ""), "url": x.get("url", ""), "text": x.get("text", "")}
            for x in data.get("results", [])
        ]


class YouComSearch:
    name = "youcom"

    def __init__(self) -> None:
        self.s = get_settings()

    async def search(self, query: str, n: int = 5) -> list[dict]:
        if not self.s.youcom_api_key:
            raise RuntimeError("YOUCOM_API_KEY not set")
        headers = {"X-API-Key": self.s.youcom_api_key}
        params = {"query": query, "count": n}
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.get(_YOUCOM_URL, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
        web = (data.get("results") or {}).get("web") or []
        return [
            {
                "title": item.get("title") or "Result",
                "url": item.get("url") or "",
                "text": (
                    (item.get("snippets") or [None])[0]
                    or item.get("description")
                    or "Educational search result from you.com."
                ),
            }
            for item in web
        ]
