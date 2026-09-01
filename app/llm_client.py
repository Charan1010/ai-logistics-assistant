"""
LLM client for interacting with Ollama.
"""
import httpx
from typing import List, Dict
from app.config import settings


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


# Global LLM client instance
llm_client = LLMClient()
