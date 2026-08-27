"""
Tests for Feature 1: Basic Chat endpoint.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.session_store import session_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear all sessions before each test."""
    session_store.clear_all()
    yield
    session_store.clear_all()


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


# Feature 3: Conversation History Tests

def test_create_session():
    """Test creating a new session."""
    response = client.post("/api/sessions", json={})
    
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert data["message_count"] == 0
    assert "created_at" in data
    assert "updated_at" in data


def test_create_session_with_metadata():
    """Test creating a session with metadata."""
    response = client.post(
        "/api/sessions",
        json={"metadata": {"user": "test_user", "department": "logistics"}}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["metadata"]["user"] == "test_user"
    assert data["metadata"]["department"] == "logistics"


def test_list_sessions():
    """Test listing all sessions."""
    # Create a few sessions
    client.post("/api/sessions", json={})
    client.post("/api/sessions", json={})
    
    response = client.get("/api/sessions")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2


def test_get_session():
    """Test getting session details."""
    # Create a session
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    
    # Get session details
    response = client.get(f"/api/sessions/{session_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["message_count"] == 0


def test_get_nonexistent_session():
    """Test getting a session that doesn't exist."""
    response = client.get("/api/sessions/nonexistent-id")
    assert response.status_code == 404


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_chat_with_session(mock_chat):
    """Test chat endpoint with session support."""
    mock_chat.return_value = "Delivery times depend on several factors..."
    
    # Create a session
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    
    # Send a message with session
    response = client.post(
        "/api/chat",
        json={"message": "What affects delivery times?", "session_id": session_id}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    
    # Verify message was stored in session
    history_response = client.get(f"/api/sessions/{session_id}/history")
    history = history_response.json()
    assert history["total"] == 2  # user message + assistant response
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][1]["role"] == "assistant"


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_multi_turn_conversation(mock_chat):
    """Test multi-turn conversation with session."""
    mock_chat.side_effect = [
        "First response",
        "Second response that references context"
    ]
    
    # Create session
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    
    # First message
    client.post(
        "/api/chat",
        json={"message": "What are KPIs?", "session_id": session_id}
    )
    
    # Second message (should have context from first)
    client.post(
        "/api/chat",
        json={"message": "Give me examples", "session_id": session_id}
    )
    
    # Verify both exchanges are in history
    history_response = client.get(f"/api/sessions/{session_id}/history")
    history = history_response.json()
    assert history["total"] == 4  # 2 user + 2 assistant messages


def test_chat_with_nonexistent_session():
    """Test chat with invalid session ID."""
    response = client.post(
        "/api/chat",
        json={"message": "Test", "session_id": "nonexistent"}
    )
    assert response.status_code == 404


def test_get_session_history():
    """Test getting conversation history."""
    # Create session and add messages
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    
    # Manually add some messages to session for testing
    from app.session_store import session_store
    session_store.add_message(session_id, "user", "Hello")
    session_store.add_message(session_id, "assistant", "Hi there!")
    
    # Get history
    response = client.get(f"/api/sessions/{session_id}/history")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["messages"][0]["content"] == "Hello"
    assert data["messages"][1]["content"] == "Hi there!"


def test_get_history_with_limit():
    """Test getting limited conversation history."""
    # Create session
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    
    # Add multiple messages
    from app.session_store import session_store
    for i in range(5):
        session_store.add_message(session_id, "user", f"Message {i}")
    
    # Get limited history
    response = client.get(f"/api/sessions/{session_id}/history?limit=2")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # Only last 2 messages


def test_delete_session():
    """Test deleting a session."""
    # Create session
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    
    # Delete it
    response = client.delete(f"/api/sessions/{session_id}")
    assert response.status_code == 204
    
    # Verify it's gone
    get_response = client.get(f"/api/sessions/{session_id}")
    assert get_response.status_code == 404


def test_delete_nonexistent_session():
    """Test deleting a session that doesn't exist."""
    response = client.delete("/api/sessions/nonexistent")
    assert response.status_code == 404


# Feature 4: Document Ingestion Tests

@pytest.fixture
def cleanup_documents():
    """Clean up test documents after tests."""
    yield
    # Clean up vector store and uploaded files
    from app.vector_store import get_vector_store
    from pathlib import Path
    
    vector_store = get_vector_store()
    docs = vector_store.list_documents()
    for doc in docs:
        vector_store.delete_document(doc["document_id"])
    
    # Clean up uploaded files
    upload_dir = Path("./data/uploads")
    if upload_dir.exists():
        for file in upload_dir.glob("*"):
            if file.is_file():
                file.unlink()


def test_upload_txt_document(cleanup_documents):
    """Test uploading a text document."""
    # Create a test text file
    test_content = b"This is a test document about logistics. It contains information about supply chain management and warehouse operations."
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", test_content, "text/plain")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "document_id" in data
    assert data["filename"] == "test.txt"
    assert data["file_type"] == "txt"
    assert data["chunks_created"] > 0


def test_upload_unsupported_file_type(cleanup_documents):
    """Test uploading an unsupported file type."""
    test_content = b"fake image content"
    
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.jpg", test_content, "image/jpeg")}
    )
    
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_list_documents(cleanup_documents):
    """Test listing all documents."""
    # Upload a document first
    test_content = b"Test document content for listing."
    client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", test_content, "text/plain")}
    )
    
    # List documents
    response = client.get("/api/documents")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["documents"]) >= 1
    assert "document_id" in data["documents"][0]
    assert "filename" in data["documents"][0]


def test_get_document_details(cleanup_documents):
    """Test getting details for a specific document."""
    # Upload a document
    test_content = b"Test document for retrieval."
    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", test_content, "text/plain")}
    )
    document_id = upload_response.json()["document_id"]
    
    # Get document details
    response = client.get(f"/api/documents/{document_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["filename"] == "test.txt"
    assert data["total_chunks"] > 0


def test_get_nonexistent_document():
    """Test getting a document that doesn't exist."""
    response = client.get("/api/documents/nonexistent-id")
    assert response.status_code == 404


def test_get_document_chunks(cleanup_documents):
    """Test getting chunks for a document."""
    # Upload a document
    test_content = b"Test document with multiple sentences. This is the second sentence. And this is the third one."
    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", test_content, "text/plain")}
    )
    document_id = upload_response.json()["document_id"]
    
    # Get chunks
    response = client.get(f"/api/documents/{document_id}/chunks")
    
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["total"] > 0
    assert len(data["chunks"]) > 0
    assert "text" in data["chunks"][0]
    assert "chunk_index" in data["chunks"][0]


def test_delete_document(cleanup_documents):
    """Test deleting a document."""
    # Upload a document
    test_content = b"Test document for deletion."
    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", test_content, "text/plain")}
    )
    document_id = upload_response.json()["document_id"]
    
    # Delete it
    response = client.delete(f"/api/documents/{document_id}")
    assert response.status_code == 204
    
    # Verify it's gone
    get_response = client.get(f"/api/documents/{document_id}")
    assert get_response.status_code == 404


def test_delete_nonexistent_document():
    """Test deleting a document that doesn't exist."""
    response = client.delete("/api/documents/nonexistent-id")
    assert response.status_code == 404


def test_vector_store_stats(cleanup_documents):
    """Test getting vector store statistics."""
    # Upload a document
    test_content = b"Test document for stats."
    client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", test_content, "text/plain")}
    )
    
    # Get stats
    response = client.get("/api/documents/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert "total_documents" in data
    assert "total_chunks" in data
    assert "collection_name" in data
    assert data["total_documents"] >= 1
