"""OpenAI-compatible LLM client for lesson generation and structured JSON calls."""
from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from ..core.config import get_settings
from ..core.tracing import llm_traceable

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_RETRY_STATUS = {429, 500, 502, 503, 504}
_BACKOFF = [5, 15, 30, 60]  # seconds between attempts; len+1 total tries
_MAX_CONTINUATIONS = 2

# (endpoint, model) routes that reject any non-default `temperature` with a 400 —
# once seen, every later payload for that route omits the parameter.
_TEMPERATURE_UNSUPPORTED: set[tuple[str, str]] = set()


def _json_placeholder(ann):
    """A neutral value for a field annotation (used to build a minimal valid instance)."""
    import types as _t
    from typing import Literal, Union, get_args, get_origin

    from pydantic import BaseModel as _BM

    if ann is str:
        return ""
    if ann is bool:
        return False
    if ann is int:
        return 0
    if ann is float:
        return 0.0
    origin = get_origin(ann)
    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    if origin is Literal:
        return get_args(ann)[0]
    if origin is Union or origin is getattr(_t, "UnionType", None):
        args = get_args(ann)
        if type(None) in args:
            return None
        return _json_placeholder(args[0]) if args else None
    if isinstance(ann, type) and issubclass(ann, _BM):
        return minimal_json_instance(ann).model_dump()
    return None


def minimal_json_instance(schema):
    """Structurally-valid, semantically-neutral Pydantic instance (used when JSON calls fail)."""
    data = {}
    for fname, finfo in schema.model_fields.items():
        if finfo.is_required():
            data[fname] = _json_placeholder(finfo.annotation)
    return schema.model_validate(data)


class OpenAICompatLLM:
    name = "openai"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.s = get_settings()
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    @property
    def base_url(self) -> str:
        return self._base_url or self.s.llm_base_url

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else self.s.llm_api_key

    @property
    def model(self) -> str:
        return self._model or self.s.llm_model

    def _headers(self) -> dict:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY not set")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _chat_payload(
        self, messages: list[dict], *, temperature: float, max_tokens: int, stream: bool = False
    ) -> dict:
        payload: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        if (self.base_url, self.model) not in _TEMPERATURE_UNSUPPORTED:
            payload["temperature"] = temperature
        if stream:
            payload["stream"] = True
        return payload

    def _mark_temperature_unsupported(self, status_code: int, body: str) -> bool:
        """Some router model routes reject any non-default `temperature` with a 400.

        Records the (endpoint, model) pair so every later call omits the parameter, and
        returns True when the caller should retry this request immediately without it.
        """
        key = (self.base_url, self.model)
        if status_code == 400 and "temperature" in body and key not in _TEMPERATURE_UNSUPPORTED:
            _TEMPERATURE_UNSUPPORTED.add(key)
            logger.info("model %s rejects `temperature` — retrying without it", self.model)
            return True
        return False

    @llm_traceable(
        "openai_chat",
        tags=["agent:coursegen", "coursegen"],
        metadata={"agent": "coursegen"},
    )
    async def _chat(self, messages: list[dict], *, temperature: float, max_tokens: int) -> dict:
        """POST to /chat/completions, retrying transient rate-limit/5xx responses.

        Traced inputs are messages/temperature/max_tokens (no Authorization headers).
        """
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=600) as client:
            for attempt in range(len(_BACKOFF) + 1):
                payload = self._chat_payload(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
                try:
                    r = await client.post(url, headers=headers, json=payload)
                    if self._mark_temperature_unsupported(r.status_code, r.text):
                        continue  # retry immediately with the parameter stripped
                    if r.status_code in _RETRY_STATUS and attempt < len(_BACKOFF):
                        await asyncio.sleep(_retry_after(r) or _BACKOFF[attempt])
                        continue
                    r.raise_for_status()
                    return r.json()
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    if exc.response.status_code in _RETRY_STATUS and attempt < len(_BACKOFF):
                        await asyncio.sleep(_retry_after(exc.response) or _BACKOFF[attempt])
                        continue
                    raise
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    if attempt < len(_BACKOFF):
                        await asyncio.sleep(_BACKOFF[attempt])
                        continue
                    raise
        if last_exc:
            raise last_exc
        raise RuntimeError("LLM request failed without a response")

    async def _chat_stream(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        on_delta,
    ) -> tuple[str, str | None]:
        """Stream one /chat/completions call, invoking ``on_delta(text)`` per token chunk.

        Total function: never raises. Returns ``(content_so_far, finish_reason)`` where
        finish_reason is ``"error"`` on any failure (connect or mid-stream) so the caller
        can fall back to the buffered path / continuation without losing streamed text.
        """
        url = f"{self.base_url}/chat/completions"
        content = ""
        try:
            headers = self._headers()
            async with httpx.AsyncClient(timeout=600) as client:
                for _ in range(2):  # at most one temperature-strip retry
                    payload = self._chat_payload(
                        messages, temperature=temperature, max_tokens=max_tokens, stream=True
                    )
                    async with client.stream("POST", url, headers=headers, json=payload) as r:
                        if r.status_code == 400:
                            body = (await r.aread()).decode("utf-8", errors="ignore")
                            if self._mark_temperature_unsupported(r.status_code, body):
                                continue
                        r.raise_for_status()
                        return await self._consume_stream(r, on_delta)
            return content, "error"
        except Exception as exc:  # noqa: BLE001 — streaming is best-effort theater
            logger.warning("LLM stream interrupted after %d chars: %s", len(content), exc)
            return content, "error"

    async def _consume_stream(self, r, on_delta) -> tuple[str, str | None]:
        content = ""
        finish: str | None = None
        try:
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    chunk = json.loads(raw)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content") or ""
                if delta:
                    content += delta
                    if on_delta is not None:
                        res = on_delta(delta)
                        if asyncio.iscoroutine(res):
                            await res
                finish = choices[0].get("finish_reason") or finish
        except Exception as exc:  # noqa: BLE001 — streaming is best-effort theater
            logger.warning("LLM stream interrupted after %d chars: %s", len(content), exc)
            return content, "error"
        return content, finish

    @llm_traceable(
        "generate_html",
        tags=["agent:coursegen", "coursegen"],
        metadata={"agent": "coursegen"},
    )
    async def generate_html(self, system: str, user: str, on_delta=None) -> str:
        """Return one complete HTML document, continuing past the token ceiling if needed.

        With ``on_delta`` (sync or async ``fn(text)``), tokens stream as they generate
        (fast_gen §4.3). Every streamed delta is a prefix-consistent piece of the returned
        document; stream failures resume through the buffered continuation path.
        """
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        content = ""
        for _ in range(_MAX_CONTINUATIONS + 1):
            chunk = ""
            finish: str | None = None
            if on_delta is not None:
                chunk, finish = await self._chat_stream(
                    messages,
                    temperature=0.6,
                    max_tokens=self.s.llm_max_tokens,
                    on_delta=on_delta,
                )
                if finish == "error" and chunk:
                    # Mid-stream drop: keep the streamed prefix and continue below,
                    # exactly like a token-ceiling stop.
                    finish = "length"
            if (finish is None and not chunk) or finish == "error":
                data = await self._chat(
                    messages, temperature=0.6, max_tokens=self.s.llm_max_tokens
                )
                choice = data["choices"][0]
                chunk = choice["message"]["content"] or ""
                finish = choice.get("finish_reason")
                if chunk and on_delta is not None:
                    res = on_delta(chunk)
                    if asyncio.iscoroutine(res):
                        await res
            content += chunk
            if finish != "length":
                break
            if "</html>" in content.lower():
                break
            messages.append({"role": "assistant", "content": chunk})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Continue exactly where you stopped. Do not repeat earlier content. "
                        "Finish the HTML document with </body></html>."
                    ),
                }
            )
        return content

    @llm_traceable(
        "generate_json",
        tags=["agent:coursegen", "coursegen", "json"],
        metadata={"agent": "coursegen"},
    )
    async def generate_json(self, system: str, user: str, schema):
        schema_json = json.dumps(schema.model_json_schema())
        data = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"{system}\n\nRespond with ONLY a JSON object matching this JSON Schema "
                        f"(no prose, no markdown fences):\n{schema_json}"
                    ),
                },
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=min(self.s.llm_max_tokens, 8192),
        )
        content = (data["choices"][0]["message"]["content"] or "").strip()
        content = _FENCE_RE.sub("", content).strip()
        try:
            return schema.model_validate_json(content)
        except Exception:
            m = _JSON_RE.search(content)
            if not m:
                raise
            logger.debug("Strict JSON parse failed for %s; recovered embedded JSON object", schema.__name__)
            return schema.model_validate_json(m.group(0))


def _retry_after(resp: httpx.Response) -> float | None:
    val = resp.headers.get("retry-after")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None
