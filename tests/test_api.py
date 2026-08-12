"""
Tests for Feature 1: Basic Chat endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test the root health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "basic_chat" in data["features"]


def test_chat_endpoint_valid_message():
    """Test chat endpoint with a valid message."""
    response = client.post(
        "/api/chat",
        json={"message": "What are key supply chain metrics?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "model" in data
    assert len(data["response"]) > 0


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
