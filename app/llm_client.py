"""
Provider-aware LLM client.

Supports two API shapes selected by ``settings.llm_provider``:

* ``ollama``  -> local Ollama server (``/api/chat``).
* ``groq`` / ``openai`` -> OpenAI-compatible chat completions
  (``/chat/completions`` with a Bearer token).

The public interface (``chat``, ``chat_with_tools``, ``chat_json`` and the
``model`` attribute) is identical across providers so the rest of the app and
the test suite are provider-agnostic.
"""
import asyncio
import json
import logging
import httpx
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Retry behavior for transient errors (429 rate limits, 5xx). Applies to the
# OpenAI-compatible providers (Groq/OpenAI) where rapid eval loops can trip
# free-tier rate limits.
_MAX_RETRIES = 5
_BASE_BACKOFF_SECONDS = 2.0


@dataclass
class ToolCall:
    """One tool invocation requested by the model."""
    name: str
    arguments: dict = field(default_factory=dict)
    call_id: Optional[str] = None


@dataclass
class LLMResponse:
    """Structured response supporting both plain text and tool calls."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)


# Providers that speak the OpenAI chat-completions dialect.
_OPENAI_COMPATIBLE = {"groq", "openai"}


def _coerce_tool_args(raw_args) -> dict:
    """Normalise tool-call arguments to a dict.

    Ollama returns a dict; OpenAI/Groq return a JSON-encoded string.
    """
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args) if raw_args else {}
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


class LLMClient:
    """Client for making chat requests to the configured LLM provider."""

    def __init__(self):
        self.provider = (settings.llm_provider or "ollama").lower()

        if self.provider in _OPENAI_COMPATIBLE:
            if self.provider == "groq":
                self.base_url = settings.groq_base_url.rstrip("/")
                self.model = settings.groq_model
                self.api_key = settings.groq_api_key
            else:  # openai
                self.base_url = settings.openai_base_url.rstrip("/")
                self.model = settings.openai_model
                self.api_key = settings.openai_api_key
        else:  # ollama (default)
            self.provider = "ollama"
            self.base_url = settings.ollama_base_url.rstrip("/")
            self.model = settings.ollama_model
            self.api_key = ""

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @property
    def _is_openai_compatible(self) -> bool:
        return self.provider in _OPENAI_COMPATIBLE

    def _openai_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise on HTTP error, including the response body in the message.

        Providers like Groq/OpenAI return the real reason (e.g. a decommissioned
        model) in the JSON body; the default ``raise_for_status`` hides it behind
        a bare status line. Surfacing the body makes CI/eval failures diagnosable.
        """
        if response.is_error:
            body = ""
            try:
                body = response.text[:500]
            except Exception:
                body = "<unreadable response body>"
            raise httpx.HTTPStatusError(
                f"{response.status_code} {response.reason_phrase} from "
                f"{response.request.url}: {body}",
                request=response.request,
                response=response,
            )

    async def _post_with_retry(self, client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
        """POST with exponential backoff on 429 / 5xx transient errors.

        Honors the ``Retry-After`` header when present (Groq/OpenAI send it on
        429). Retries only transient statuses; 4xx like 401/404 fail fast since
        retrying won't help. On the final attempt the response is returned as-is
        so the caller's ``_raise_for_status`` surfaces the real error body.
        """
        transient = {429, 500, 502, 503, 504}
        for attempt in range(_MAX_RETRIES):
            response = await client.post(url, **kwargs)
            if response.status_code not in transient or attempt == _MAX_RETRIES - 1:
                return response

            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = _BASE_BACKOFF_SECONDS * (2 ** attempt)
            else:
                delay = _BASE_BACKOFF_SECONDS * (2 ** attempt)

            logger.warning(
                "LLM request got %s; retrying in %.1fs (attempt %d/%d)",
                response.status_code, delay, attempt + 1, _MAX_RETRIES,
            )
            await asyncio.sleep(delay)
        return response  # unreachable, but keeps type checkers happy

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Send chat messages and return the assistant's text response."""
        if self._is_openai_compatible:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await self._post_with_retry(client,
                    f"{self.base_url}/chat/completions",
                    headers=self._openai_headers(),
                    json={"model": self.model, "messages": messages},
                )
                self._raise_for_status(response)
                result = response.json()
                return result["choices"][0]["message"]["content"] or ""

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await self._post_with_retry(client,
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
            )
            self._raise_for_status(response)
            result = response.json()
            return result["message"]["content"]

    async def chat_with_tools(
        self,
        messages: List[Dict],
        tools: Optional[List[dict]] = None,
    ) -> LLMResponse:
        """Send chat messages with optional tool schemas; return a structured response."""
        if self._is_openai_compatible:
            payload: Dict = {"model": self.model, "messages": messages}
            if tools:
                payload["tools"] = tools
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await self._post_with_retry(client,
                    f"{self.base_url}/chat/completions",
                    headers=self._openai_headers(),
                    json=payload,
                )
                self._raise_for_status(response)
                data = response.json()

            message = (data.get("choices") or [{}])[0].get("message", {}) or {}
            content = message.get("content") or ""
            tool_calls: List[ToolCall] = []
            for entry in message.get("tool_calls") or []:
                function = entry.get("function") or {}
                name = function.get("name")
                if not name:
                    continue
                tool_calls.append(
                    ToolCall(
                        name=name,
                        arguments=_coerce_tool_args(function.get("arguments", {})),
                        call_id=entry.get("id"),
                    )
                )
            return LLMResponse(content=content, tool_calls=tool_calls)

        # Ollama
        payload = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await self._post_with_retry(client, f"{self.base_url}/api/chat", json=payload)
            self._raise_for_status(response)
            data = response.json()

        message = data.get("message", {}) or {}
        content = message.get("content") or ""
        tool_calls = []
        for entry in message.get("tool_calls") or []:
            function = entry.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            tool_calls.append(
                ToolCall(
                    name=name,
                    arguments=_coerce_tool_args(function.get("arguments", {})),
                    call_id=entry.get("id"),
                )
            )
        return LLMResponse(content=content, tool_calls=tool_calls)

    async def chat_json(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
        """Send chat messages in JSON output mode; return the raw JSON string."""
        if self._is_openai_compatible:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await self._post_with_retry(client,
                    f"{self.base_url}/chat/completions",
                    headers=self._openai_headers(),
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    },
                )
                self._raise_for_status(response)
                result = response.json()
                return result["choices"][0]["message"]["content"] or ""

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await self._post_with_retry(client,
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": temperature},
                },
            )
            self._raise_for_status(response)
            result = response.json()
            return result["message"]["content"]


# Global LLM client instance
llm_client = LLMClient()
