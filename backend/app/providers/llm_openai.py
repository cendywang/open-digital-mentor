"""OpenAI-compatible streaming chat adapter.

Works against anything that speaks `/chat/completions` with SSE: DeepSeek,
阿里云百炼, 火山方舟, OpenAI, Ollama, vLLM, LiteLLM, an internal gateway.
That is the whole point of choosing this shape — one adapter covers the
providers a user is realistically going to have a key for.

The API key stays server-side and is never sent to the browser.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.models import Message

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class OpenAICompatibleLLM:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout_s: float = 60.0,
    ) -> None:
        if not base_url:
            raise LLMError("base_url is required")
        if not model:
            raise LLMError("model is required")

        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=10.0),
        )

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
        }

        try:
            async with self._client.stream("POST", self._url, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")[:400]
                    raise LLMError(f"upstream returned {response.status_code}: {body}")

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    delta = _extract_delta(data)
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


def _extract_delta(data: str) -> str:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        log.debug("skipping unparseable SSE chunk")
        return ""

    choices = payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else ""
