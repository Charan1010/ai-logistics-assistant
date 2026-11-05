"""
Unit tests for the provider-aware LLM client (dynamic provider selection).

These are pure unit tests - no network calls. They verify that LLMClient wires
up the correct base URL / model / auth depending on settings.llm_provider, and
that tool-call arguments are normalised across provider dialects.
"""
from unittest.mock import patch

from app.llm_client import LLMClient, _coerce_tool_args


def _make_client(**overrides) -> LLMClient:
    """Instantiate LLMClient with patched settings attributes."""
    with patch("app.llm_client.settings") as mock_settings:
        mock_settings.llm_provider = overrides.get("llm_provider", "ollama")
        mock_settings.ollama_base_url = overrides.get("ollama_base_url", "http://localhost:11434")
        mock_settings.ollama_model = overrides.get("ollama_model", "qwen2.5:3b")
        mock_settings.groq_base_url = overrides.get("groq_base_url", "https://api.groq.com/openai/v1")
        mock_settings.groq_model = overrides.get("groq_model", "llama-3.1-8b-instant")
        mock_settings.groq_api_key = overrides.get("groq_api_key", "gsk_test")
        mock_settings.openai_base_url = overrides.get("openai_base_url", "https://api.openai.com/v1")
        mock_settings.openai_model = overrides.get("openai_model", "gpt-4o-mini")
        mock_settings.openai_api_key = overrides.get("openai_api_key", "sk_test")
        return LLMClient()


def test_default_provider_is_ollama():
    client = _make_client(llm_provider="ollama")
    assert client.provider == "ollama"
    assert client.base_url == "http://localhost:11434"
    assert client.model == "qwen2.5:3b"
    assert client._is_openai_compatible is False


def test_provider_switches_to_groq():
    client = _make_client(llm_provider="groq")
    assert client.provider == "groq"
    assert client.base_url == "https://api.groq.com/openai/v1"
    assert client.model == "llama-3.1-8b-instant"
    assert client.api_key == "gsk_test"
    assert client._is_openai_compatible is True


def test_provider_switches_to_openai():
    client = _make_client(llm_provider="openai")
    assert client.provider == "openai"
    assert client.base_url == "https://api.openai.com/v1"
    assert client.model == "gpt-4o-mini"
    assert client.api_key == "sk_test"
    assert client._is_openai_compatible is True


def test_unknown_provider_falls_back_to_ollama():
    client = _make_client(llm_provider="something-unknown")
    assert client.provider == "ollama"
    assert client.base_url == "http://localhost:11434"


def test_provider_name_is_case_insensitive():
    client = _make_client(llm_provider="GROQ")
    assert client.provider == "groq"
    assert client._is_openai_compatible is True


def test_openai_headers_include_bearer_token():
    client = _make_client(llm_provider="groq", groq_api_key="gsk_abc123")
    headers = client._openai_headers()
    assert headers["Authorization"] == "Bearer gsk_abc123"
    assert headers["Content-Type"] == "application/json"


def test_coerce_tool_args_passthrough_dict():
    assert _coerce_tool_args({"a": 1}) == {"a": 1}


def test_coerce_tool_args_parses_json_string():
    # OpenAI/Groq return arguments as a JSON-encoded string.
    assert _coerce_tool_args('{"tracking_number": "TRK-42"}') == {"tracking_number": "TRK-42"}


def test_coerce_tool_args_handles_bad_json():
    assert _coerce_tool_args("not valid json") == {}


def test_coerce_tool_args_handles_non_dict_json():
    # A JSON array is valid JSON but not a dict -> normalise to {}.
    assert _coerce_tool_args("[1, 2, 3]") == {}
