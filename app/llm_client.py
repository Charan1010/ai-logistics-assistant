"""
LLM client for interacting with Ollama.
"""
import httpx
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from app.config import settings


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


class LLMClient:
    """Client for making requests to Ollama API."""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Send chat messages to Ollama and get response.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            str: Assistant's response text
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                }
            )
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]

    async def chat_with_tools(
        self,
        messages: List[Dict],
        tools: Optional[List[dict]] = None,
    ) -> LLMResponse:
        """
        Send chat messages with optional tool schemas and return a structured response.

        Ollama returns tool_calls under message.tool_calls when the model chooses to call a tool.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        message = data.get("message", {}) or {}
        content = message.get("content") or ""

        tool_calls: List[ToolCall] = []
        for entry in message.get("tool_calls") or []:
            function = entry.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            raw_args = function.get("arguments", {}) or {}
            if isinstance(raw_args, str):
                try:
                    import json as _json
                    raw_args = _json.loads(raw_args) if raw_args else {}
                except Exception:
                    raw_args = {}
            if not isinstance(raw_args, dict):
                raw_args = {}
            tool_calls.append(ToolCall(name=name, arguments=raw_args, call_id=entry.get("id")))

        return LLMResponse(content=content, tool_calls=tool_calls)

    async def chat_json(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
        """
        Send chat messages with Ollama's JSON output mode enabled.

        Ollama's `format: "json"` forces the model to emit valid JSON. Used by the
        Feature 8 planner where we need a parseable list of steps.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]


# Global LLM client instance
llm_client = LLMClient()
