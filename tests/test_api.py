"""
Tests for Feature 1: Basic Chat endpoint.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint_returns_ui():
    """Test that root endpoint serves the UI HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert b"AI Logistics Assistant" in response.content


def test_api_status_endpoint():
    """Test the API status endpoint."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["app"] == "AI Logistics Assistant"
    assert "basic_chat" in data["features"]
    assert "structured_output" in data["features"]
    assert "model" in data


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_chat_endpoint_valid_message(mock_chat):
    """Test chat endpoint with a valid message (mocked LLM)."""
    # Mock the LLM response
    mock_chat.return_value = "This is a test response about supply chain metrics."
    
    response = client.post(
        "/api/chat",
        json={"message": "What are key supply chain metrics?"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "model" in data
    assert data["response"] == "This is a test response about supply chain metrics."
    
    # Verify LLM was called with correct structure
    mock_chat.assert_called_once()
    call_args = mock_chat.call_args[0][0]
    assert len(call_args) == 2  # System prompt + user message
    assert call_args[0]["role"] == "system"
    assert call_args[1]["role"] == "user"
    assert call_args[1]["content"] == "What are key supply chain metrics?"


def test_chat_endpoint_empty_message():
    """Test chat endpoint with empty message."""
    response = client.post(
        "/api/chat",
        json={"message": ""}
    )
    assert response.status_code == 422  # Validation error


def test_chat_endpoint_missing_message():
    """Test chat endpoint with missing message field."""
    response = client.post(
        "/api/chat",
        json={}
    )
    assert response.status_code == 422  # Validation error


def test_chat_endpoint_invalid_json():
    """Test chat endpoint with invalid JSON."""
    response = client.post(
        "/api/chat",
        data="not json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_chat_endpoint_long_message(mock_chat):
    """Test chat endpoint with a long message."""
    mock_chat.return_value = "Response to long message."
    
    long_message = "How can I optimize " + "operations " * 100
    response = client.post(
        "/api/chat",
        json={"message": long_message}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_structured_chat_endpoint_valid_json(mock_chat):
    """Structured endpoint should return parsed JSON from the model."""
    mock_chat.return_value = (
        '{"summary":"Inventory is stable.",'
        '"key_points":["Fill rate is 98%","Backorders are low"],'
        '"recommendations":["Increase safety stock for SKU-19"],'
        '"risks":["Supplier lead-time volatility"],'
        '"confidence":0.86}'
    )

    response = client.post(
        "/api/chat/structured",
        json={"message": "Give me a logistics status summary"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model"]
    assert data["output"]["summary"] == "Inventory is stable."
    assert data["output"]["confidence"] == 0.86
    assert "Fill rate is 98%" in data["output"]["key_points"]


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_structured_chat_endpoint_fallback_on_invalid_json(mock_chat):
    """Structured endpoint should provide fallback output when model format is invalid."""
    mock_chat.return_value = "Here is your answer in plain text without JSON."

    response = client.post(
        "/api/chat/structured",
        json={"message": "Summarize delivery risk"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["summary"]
    assert data["output"]["confidence"] == 0.4
    assert "Response format mismatch from model" in data["output"]["risks"]
