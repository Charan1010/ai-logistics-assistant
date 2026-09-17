"""
Tests for Feature 1: Basic Chat endpoint.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.models import QueryClassification, SearchResult
from app.retrieval_memory import retrieval_memory_store
from app.session_store import session_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear all sessions before each test."""
    original_multi_tenant = settings.enable_multi_tenant
    original_long_term_context = settings.enable_long_term_context
    settings.enable_multi_tenant = False
    settings.enable_long_term_context = False
    session_store.clear_all()
    retrieval_memory_store.clear_all()
    yield
    session_store.clear_all()
    retrieval_memory_store.clear_all()
    settings.enable_multi_tenant = original_multi_tenant
    settings.enable_long_term_context = original_long_term_context


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


# Feature 5: Semantic Search Tests

def test_search_returns_ranked_results(cleanup_documents):
    """Test that search returns semantically relevant chunks with scores."""
    test_content = (
        b"On-time delivery rate is a key supply chain KPI. "
        b"Warehouse throughput measures efficiency of storage operations."
    )
    client.post(
        "/api/documents/upload",
        files={"file": ("kpis.txt", test_content, "text/plain")}
    )

    response = client.post(
        "/api/search",
        json={"query": "What metrics matter for shipping performance?", "top_k": 3}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "What metrics matter for shipping performance?"
    assert data["total"] >= 1
    assert len(data["results"]) >= 1

    top_result = data["results"][0]
    assert "text" in top_result
    assert "chunk_id" in top_result
    assert "document_id" in top_result
    assert "filename" in top_result
    assert 0.0 <= top_result["score"] <= 1.0


def test_search_scoped_to_document(cleanup_documents):
    """Test that document_id scopes search results to a single document."""
    upload_a = client.post(
        "/api/documents/upload",
        files={"file": ("doc_a.txt", b"Warehouse automation reduces picking errors.", "text/plain")}
    )
    client.post(
        "/api/documents/upload",
        files={"file": ("doc_b.txt", b"Ocean freight rates fluctuate with fuel costs.", "text/plain")}
    )
    doc_a_id = upload_a.json()["document_id"]

    response = client.post(
        "/api/search",
        json={"query": "warehouse", "top_k": 5, "document_id": doc_a_id}
    )

    assert response.status_code == 200
    data = response.json()
    for result in data["results"]:
        assert result["document_id"] == doc_a_id


def test_search_empty_query_returns_422():
    """Test that an empty query is rejected by validation."""
    response = client.post("/api/search", json={"query": "", "top_k": 3})
    assert response.status_code == 422


def test_search_with_no_documents_returns_empty(cleanup_documents):
    """Test that searching with an empty vector store returns no results (not an error)."""
    response = client.post("/api/search", json={"query": "anything at all", "top_k": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["results"] == []


def test_search_stats_endpoint(cleanup_documents):
    """Test the /api/search/stats alias endpoint."""
    client.post(
        "/api/documents/upload",
        files={"file": ("stats_doc.txt", b"Freight consolidation lowers per-unit shipping cost.", "text/plain")}
    )

    response = client.get("/api/search/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["total_documents"] >= 1
    assert data["total_chunks"] >= 1


# Feature 6: Smart Router Tests

@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_classify_query_fallback_on_invalid_json(mock_chat):
    """Classifier should fall back to conservative retrieval when JSON parsing fails."""
    from app.main import classify_query
    import asyncio

    mock_chat.return_value = "not json"

    result = asyncio.run(classify_query("Tell me about the policy"))

    assert result.needs_retrieval is True
    assert result.confidence == 0.3
    assert result.query_type == "ambiguous"


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_smart_chat_routes_general_question_to_llm(mock_chat, mock_search, mock_classify):
    """Confident general questions should skip retrieval."""
    mock_classify.return_value = QueryClassification(
        needs_retrieval=False,
        confidence=0.92,
        query_type="general",
    )
    mock_chat.return_value = "A logistics KPI measures operational performance."

    response = client.post(
        "/api/chat/smart",
        json={"message": "What is a KPI?"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "llm"
    assert data["chunks_used"] == 0
    assert data["confidence"] == 0.92
    assert data["answer"] == "A logistics KPI measures operational performance."
    mock_search.assert_not_called()


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_smart_chat_routes_document_question_to_rag(mock_chat, mock_search, mock_classify):
    """Confident document-dependent questions should retrieve context."""
    mock_classify.return_value = QueryClassification(
        needs_retrieval=True,
        confidence=0.84,
        query_type="domain",
    )
    mock_search.return_value = [
        SearchResult(
            chunk_id="chunk-1",
            text="The on-time delivery target is 97%.",
            score=0.88,
            document_id="doc-1",
            filename="kpi-policy.txt",
            chunk_index=0,
        )
    ]
    mock_chat.return_value = "The target is 97% on-time delivery."

    response = client.post(
        "/api/chat/smart",
        json={"message": "What is the uploaded on-time delivery target?", "top_k": 2}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "rag"
    assert data["chunks_used"] == 1
    assert "retrieved 1 chunk" in data["retrieval_method"]
    mock_search.assert_called_once_with(
        "What is the uploaded on-time delivery target?",
        top_k=2,
        document_id=None,
        tenant_id=None,
    )


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_smart_chat_routes_low_confidence_to_hybrid(mock_chat, mock_search, mock_classify):
    """Low-confidence classifications should use hybrid retrieval."""
    mock_classify.return_value = QueryClassification(
        needs_retrieval=False,
        confidence=0.42,
        query_type="ambiguous",
    )
    mock_search.return_value = []
    mock_chat.return_value = "I need more context, but here is the likely answer."

    response = client.post(
        "/api/chat/smart",
        json={"message": "Tell me about the policy"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "hybrid"
    assert data["chunks_used"] == 0
    assert data["classification"]["query_type"] == "ambiguous"
    mock_search.assert_called_once()


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_smart_chat_with_session_persists_history(mock_chat, mock_search, mock_classify):
    """Smart chat should persist user and assistant turns when session_id is provided."""
    mock_classify.return_value = QueryClassification(
        needs_retrieval=False,
        confidence=0.9,
        query_type="general",
    )
    mock_chat.return_value = "Safety stock protects against demand variation."

    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]

    response = client.post(
        "/api/chat/smart",
        json={"message": "What is safety stock?", "session_id": session_id}
    )

    assert response.status_code == 200
    history_response = client.get(f"/api/sessions/{session_id}/history")
    history = history_response.json()
    assert history["total"] == 2
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][1]["role"] == "assistant"
    mock_search.assert_not_called()


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_smart_chat_answers_memory_question_from_selected_session(mock_chat, mock_search, mock_classify):
    """Smart chat should use prior turns when the user asks about session history."""
    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]
    session_store.add_message(session_id, "user", "How can we reduce warehouse dwell time?")
    session_store.add_message(session_id, "assistant", "Focus on dock scheduling and staging discipline.")

    response = client.post(
        "/api/chat/smart",
        json={"message": "What was my last question?", "session_id": session_id}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "llm"
    assert data["chunks_used"] == 0
    assert data["confidence"] == 1.0
    assert "Session memory" in data["retrieval_method"]
    assert data["answer"] == 'Your last question was: "How can we reduce warehouse dwell time?"'
    mock_classify.assert_not_called()
    mock_search.assert_not_called()
    mock_chat.assert_not_called()


# Feature 6 Part B: Multi-Tenant Isolation Tests

def test_multitenant_requires_tenant_header():
    """Tenant-scoped endpoints should reject missing X-Tenant-ID when enabled."""
    settings.enable_multi_tenant = True

    response = client.post("/api/sessions", json={})

    assert response.status_code == 400
    assert "X-Tenant-ID" in response.json()["detail"]


def test_multitenant_sessions_are_isolated():
    """A session created by one tenant must not be readable by another tenant."""
    settings.enable_multi_tenant = True

    create_response = client.post("/api/sessions", json={}, headers={"X-Tenant-ID": "tenant-alpha"})
    session_id = create_response.json()["session_id"]

    allowed = client.get(f"/api/sessions/{session_id}", headers={"X-Tenant-ID": "tenant-alpha"})
    blocked = client.get(f"/api/sessions/{session_id}", headers={"X-Tenant-ID": "tenant-beta"})

    assert allowed.status_code == 200
    assert allowed.json()["tenant_id"] == "tenant-alpha"
    assert blocked.status_code == 403


def test_multitenant_document_listing_is_isolated(cleanup_documents):
    """Each tenant should only see its own uploaded documents."""
    settings.enable_multi_tenant = True

    client.post(
        "/api/documents/upload",
        files={"file": ("alpha.txt", b"Alpha tenant warehouse policy.", "text/plain")},
        headers={"X-Tenant-ID": "tenant-alpha"},
    )
    client.post(
        "/api/documents/upload",
        files={"file": ("beta.txt", b"Beta tenant ocean freight policy.", "text/plain")},
        headers={"X-Tenant-ID": "tenant-beta"},
    )

    alpha_docs = client.get("/api/documents", headers={"X-Tenant-ID": "tenant-alpha"}).json()["documents"]
    beta_docs = client.get("/api/documents", headers={"X-Tenant-ID": "tenant-beta"}).json()["documents"]

    assert {doc["filename"] for doc in alpha_docs} == {"alpha.txt"}
    assert {doc["filename"] for doc in beta_docs} == {"beta.txt"}


def test_multitenant_search_is_filtered_at_vector_store(cleanup_documents):
    """Search should use the tenant filter so one tenant cannot retrieve another tenant's chunks."""
    settings.enable_multi_tenant = True

    client.post(
        "/api/documents/upload",
        files={"file": ("alpha.txt", b"Alpha tenant has a 97 percent premium delivery target.", "text/plain")},
        headers={"X-Tenant-ID": "tenant-alpha"},
    )
    client.post(
        "/api/documents/upload",
        files={"file": ("beta.txt", b"Beta tenant tracks cold chain exceptions daily.", "text/plain")},
        headers={"X-Tenant-ID": "tenant-beta"},
    )

    response = client.post(
        "/api/search",
        json={"query": "premium delivery target", "top_k": 5},
        headers={"X-Tenant-ID": "tenant-beta"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert all(result["filename"] == "beta.txt" for result in data["results"])


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_multitenant_smart_chat_blocks_cross_tenant_session(mock_chat, mock_classify):
    """Smart chat must reject session access from the wrong tenant before answering."""
    settings.enable_multi_tenant = True
    mock_classify.return_value = QueryClassification(
        needs_retrieval=False,
        confidence=0.9,
        query_type="general",
    )
    mock_chat.return_value = "This should not be returned."

    create_response = client.post("/api/sessions", json={}, headers={"X-Tenant-ID": "tenant-alpha"})
    session_id = create_response.json()["session_id"]

    response = client.post(
        "/api/chat/smart",
        json={"message": "What is safety stock?", "session_id": session_id},
        headers={"X-Tenant-ID": "tenant-beta"},
    )

    assert response.status_code == 403
    mock_chat.assert_not_called()


@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_multitenant_normal_chat_blocks_cross_tenant_session(mock_chat):
    """Plain chat with session_id must also enforce tenant ownership."""
    settings.enable_multi_tenant = True
    mock_chat.return_value = "This should not be returned."

    create_response = client.post("/api/sessions", json={}, headers={"X-Tenant-ID": "tenant-alpha"})
    session_id = create_response.json()["session_id"]

    response = client.post(
        "/api/chat",
        json={"message": "Can I use this session?", "session_id": session_id},
        headers={"X-Tenant-ID": "tenant-beta"},
    )

    assert response.status_code == 403
    mock_chat.assert_not_called()


# Feature 6 Part C: Retrieval Memory Tests

@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_retrieval_memory_logs_rag_retrieval(mock_chat, mock_search, mock_classify):
    """RAG/Hybrid Smart Chat should log retrieved chunks for long-term context."""
    mock_classify.return_value = QueryClassification(
        needs_retrieval=True,
        confidence=0.81,
        query_type="domain",
    )
    mock_search.return_value = [
        SearchResult(
            chunk_id="chunk-a",
            text="Premium delivery target is 97%.",
            score=0.91,
            document_id="doc-a",
            filename="alpha-policy.txt",
            chunk_index=0,
        )
    ]
    mock_chat.return_value = "Premium delivery target is 97%."

    response = client.post(
        "/api/chat/smart",
        json={"message": "What is the premium delivery target?"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["retrieval_log_id"] is not None

    logs = client.get("/api/retrieval-logs").json()
    assert len(logs) == 1
    assert logs[0]["query"] == "What is the premium delivery target?"
    assert logs[0]["retrieved_chunks"] == ["chunk-a"]
    assert logs[0]["retrieval_scores"] == [0.91]
    assert logs[0]["source_used"] == "rag"


def test_knowledge_digest_summarizes_retrieval_memory():
    """Knowledge digest should aggregate top chunks and query patterns."""
    retrieval_memory_store.log_retrieval(
        query="premium delivery target",
        retrieved_chunks=["chunk-a"],
        retrieval_scores=[0.91],
        source_used="rag",
    )
    retrieval_memory_store.log_retrieval(
        query="premium delivery exception",
        retrieved_chunks=["chunk-a", "chunk-b"],
        retrieval_scores=[0.88, 0.22],
        source_used="hybrid",
    )

    response = client.get("/api/knowledge-digest")

    assert response.status_code == 200
    data = response.json()
    assert data["retrieval_count"] == 2
    assert data["top_chunks"][0] == "chunk-a"
    assert data["query_patterns"]
    assert "Observed 2 retrieval event" in data["summary"]


def test_retrieval_feedback_marks_log_entry():
    """Feedback endpoint should mark retrieval logs as helpful or not helpful."""
    entry = retrieval_memory_store.log_retrieval(
        query="warehouse dwell time",
        retrieved_chunks=["chunk-dwell"],
        retrieval_scores=[0.41],
        source_used="hybrid",
    )

    response = client.post(
        f"/api/retrieval-logs/{entry.id}/feedback",
        json={"was_helpful": False},
    )

    assert response.status_code == 200
    assert response.json()["was_helpful"] is False

    digest = client.get("/api/knowledge-digest").json()
    assert "Marked unhelpful: warehouse dwell time" in digest["coverage_gaps"]


def test_multitenant_retrieval_logs_are_isolated():
    """Retrieval memory should be scoped by tenant when multi-tenant mode is enabled."""
    settings.enable_multi_tenant = True
    retrieval_memory_store.log_retrieval(
        query="alpha delivery target",
        retrieved_chunks=["alpha-chunk"],
        retrieval_scores=[0.9],
        source_used="rag",
        tenant_id="tenant-alpha",
    )
    retrieval_memory_store.log_retrieval(
        query="beta cold chain exception",
        retrieved_chunks=["beta-chunk"],
        retrieval_scores=[0.8],
        source_used="rag",
        tenant_id="tenant-beta",
    )

    alpha_logs = client.get("/api/retrieval-logs", headers={"X-Tenant-ID": "tenant-alpha"}).json()
    beta_digest = client.get("/api/knowledge-digest", headers={"X-Tenant-ID": "tenant-beta"}).json()

    assert [entry["retrieved_chunks"] for entry in alpha_logs] == [["alpha-chunk"]]
    assert beta_digest["tenant_id"] == "tenant-beta"
    assert beta_digest["top_chunks"] == ["beta-chunk"]


@patch("app.main.classify_query", new_callable=AsyncMock)
@patch("app.main._search_document_context")
@patch("app.llm_client.llm_client.chat", new_callable=AsyncMock)
def test_long_term_context_digest_is_injected_when_enabled(mock_chat, mock_search, mock_classify):
    """When enabled, Smart Chat should include retrieval-memory digest in the generation prompt."""
    settings.enable_long_term_context = True
    retrieval_memory_store.log_retrieval(
        query="premium delivery target",
        retrieved_chunks=["chunk-a"],
        retrieval_scores=[0.91],
        source_used="rag",
    )
    mock_classify.return_value = QueryClassification(
        needs_retrieval=False,
        confidence=0.9,
        query_type="general",
    )
    mock_chat.return_value = "Here is an answer with learned context."

    response = client.post(
        "/api/chat/smart",
        json={"message": "What should we watch next?"}
    )

    assert response.status_code == 200
    final_messages = mock_chat.call_args[0][0]
    assert "Retrieval memory digest:" in final_messages[0]["content"]
    assert "premium" in final_messages[0]["content"]
    mock_search.assert_not_called()


# Feature 7: Logistics Agent Tests

def test_agent_tools_endpoint_lists_all_tools():
    """/api/agent/tools should expose all four logistics tools."""
    response = client.get("/api/agent/tools")

    assert response.status_code == 200
    data = response.json()
    tool_names = {tool["name"] for tool in data["tools"]}
    assert tool_names == {
        "check_shipment_status",
        "estimate_delivery",
        "create_shipping_ticket",
        "lookup_warehouse_info",
    }
    assert data["total"] == 4


@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
def test_agent_returns_direct_answer_when_no_tool_calls(mock_chat_with_tools):
    """When the LLM answers directly, no tools should be executed."""
    from app.llm_client import LLMResponse

    mock_chat_with_tools.return_value = LLMResponse(content="Delivery windows depend on lane and mode.", tool_calls=[])

    response = client.post(
        "/api/agent/run",
        json={"message": "What is a delivery window?"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "Delivery windows depend on lane and mode."
    assert data["steps"] == []
    assert data["tools_used"] == []
    # Only one LLM call is needed when no tools are used.
    assert mock_chat_with_tools.call_count == 1


@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
def test_agent_executes_shipment_status_tool(mock_chat_with_tools):
    """Agent should execute the tool the model chose and synthesise an answer."""
    from app.llm_client import LLMResponse, ToolCall

    mock_chat_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="check_shipment_status", arguments={"tracking_number": "TRK-42"})],
        ),
        LLMResponse(content="Your shipment TRK-42 is currently in transit.", tool_calls=[]),
    ]

    response = client.post(
        "/api/agent/run",
        json={"message": "Where is my shipment TRK-42?"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tools_used"] == ["check_shipment_status"]
    assert data["steps"][0]["tool"] == "check_shipment_status"
    assert data["steps"][0]["args"] == {"tracking_number": "TRK-42"}
    assert data["steps"][0]["result"]["tracking_number"] == "TRK-42"
    assert "in transit" in data["result"].lower()
    assert mock_chat_with_tools.call_count == 2


@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
def test_agent_reports_unknown_tool_gracefully(mock_chat_with_tools):
    """If the LLM invents a tool name, the agent should report an error step rather than crash."""
    from app.llm_client import LLMResponse, ToolCall

    mock_chat_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="teleport_shipment", arguments={"foo": "bar"})],
        ),
        LLMResponse(content="I could not complete that action.", tool_calls=[]),
    ]

    response = client.post(
        "/api/agent/run",
        json={"message": "Teleport my shipment"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tools_used"] == ["teleport_shipment"]
    assert "Unknown tool" in data["steps"][0]["result"]["error"]


@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
def test_agent_persists_messages_when_session_provided(mock_chat_with_tools):
    """Agent turns should be saved in session history when session_id is provided."""
    from app.llm_client import LLMResponse

    mock_chat_with_tools.return_value = LLMResponse(content="Recorded.", tool_calls=[])

    create_response = client.post("/api/sessions", json={})
    session_id = create_response.json()["session_id"]

    response = client.post(
        "/api/agent/run",
        json={"message": "Log a note about the Chicago dock.", "session_id": session_id}
    )

    assert response.status_code == 200
    history = client.get(f"/api/sessions/{session_id}/history").json()
    assert history["total"] == 2
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][1]["role"] == "assistant"


@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
def test_agent_blocks_cross_tenant_session(mock_chat_with_tools):
    """Agent must enforce tenant ownership before running any tools."""
    from app.llm_client import LLMResponse

    settings.enable_multi_tenant = True
    mock_chat_with_tools.return_value = LLMResponse(content="should not be returned", tool_calls=[])

    create_response = client.post("/api/sessions", json={}, headers={"X-Tenant-ID": "tenant-alpha"})
    session_id = create_response.json()["session_id"]

    response = client.post(
        "/api/agent/run",
        json={"message": "Track my shipment", "session_id": session_id},
        headers={"X-Tenant-ID": "tenant-beta"},
    )

    assert response.status_code == 403
    mock_chat_with_tools.assert_not_called()


# ---------------------------------------------------------------------------
# Feature 8: Multi-Step Agent (Plan-and-Execute)
# ---------------------------------------------------------------------------

@patch("app.planner.llm_client.chat", new_callable=AsyncMock)
@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
@patch("app.planner.llm_client.chat_json", new_callable=AsyncMock)
def test_agent_plan_creates_task_and_executes_all_steps(mock_plan_json, mock_chat_with_tools, mock_synth):
    """/api/agent/plan should return a plan, execute every step, and populate final result."""
    from app.llm_client import LLMResponse, ToolCall

    mock_plan_json.return_value = (
        '{"steps": ["Check shipment TRK-42", "Look up KPIs for the Chicago warehouse"]}'
    )
    mock_chat_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="check_shipment_status", arguments={"tracking_number": "TRK-42"})],
        ),
        LLMResponse(content="TRK-42 is currently in transit.", tool_calls=[]),
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="lookup_warehouse_info", arguments={"warehouse": "Chicago"})],
        ),
        LLMResponse(content="Chicago warehouse is at 84% capacity.", tool_calls=[]),
    ]
    mock_synth.return_value = "TRK-42 is in transit and Chicago is at 84% capacity."

    response = client.post(
        "/api/agent/plan",
        json={"message": "Check TRK-42 then Chicago KPIs"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "executing"
    assert len(data["plan"]) == 2
    assert data["task_id"]

    status = client.get(f"/api/agent/status/{data['task_id']}").json()
    assert status["status"] == "done"
    assert len(status["steps_completed"]) == 2
    assert status["steps_completed"][0]["tools_used"] == ["check_shipment_status"]
    assert status["steps_completed"][1]["tools_used"] == ["lookup_warehouse_info"]
    assert status["result"] == "TRK-42 is in transit and Chicago is at 84% capacity."
    assert mock_synth.call_count == 1


@patch("app.planner.llm_client.chat", new_callable=AsyncMock)
@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
@patch("app.planner.llm_client.chat_json", new_callable=AsyncMock)
def test_agent_plan_falls_back_to_single_step_on_bad_json(mock_plan_json, mock_chat_with_tools, mock_synth):
    """When the planner returns malformed JSON, the plan should fall back to a single step."""
    from app.llm_client import LLMResponse

    mock_plan_json.return_value = "this is not valid json"
    mock_chat_with_tools.return_value = LLMResponse(content="handled", tool_calls=[])
    mock_synth.return_value = "final answer"

    response = client.post("/api/agent/plan", json={"message": "Do something"})
    assert response.status_code == 200
    data = response.json()
    assert data["plan"] == ["Do something"]


@patch("app.planner.llm_client.chat", new_callable=AsyncMock)
@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
@patch("app.planner.llm_client.chat_json", new_callable=AsyncMock)
def test_agent_plan_reports_error_status_when_step_fails(mock_plan_json, mock_chat_with_tools, mock_synth):
    """If an executor step raises, the task should transition to status='error'."""
    mock_plan_json.return_value = '{"steps": ["Step one"]}'
    mock_chat_with_tools.side_effect = RuntimeError("ollama down")

    response = client.post("/api/agent/plan", json={"message": "trigger failure"})
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    status = client.get(f"/api/agent/status/{task_id}").json()
    assert status["status"] == "error"
    assert "ollama down" in status["error"]
    mock_synth.assert_not_called()


def test_agent_status_returns_404_for_unknown_task():
    response = client.get("/api/agent/status/does-not-exist")
    assert response.status_code == 404


@patch("app.planner.llm_client.chat", new_callable=AsyncMock)
@patch("app.agent.llm_client.chat_with_tools", new_callable=AsyncMock)
@patch("app.planner.llm_client.chat_json", new_callable=AsyncMock)
def test_agent_status_blocks_cross_tenant_access(mock_plan_json, mock_chat_with_tools, mock_synth):
    """Multi-step task created under tenant-alpha must not be readable by tenant-beta."""
    from app.llm_client import LLMResponse

    settings.enable_multi_tenant = True
    mock_plan_json.return_value = '{"steps": ["do the thing"]}'
    mock_chat_with_tools.return_value = LLMResponse(content="done", tool_calls=[])
    mock_synth.return_value = "final"

    session_id = client.post(
        "/api/sessions", json={}, headers={"X-Tenant-ID": "tenant-alpha"}
    ).json()["session_id"]

    plan_response = client.post(
        "/api/agent/plan",
        json={"message": "Do something", "session_id": session_id},
        headers={"X-Tenant-ID": "tenant-alpha"},
    )
    assert plan_response.status_code == 200
    task_id = plan_response.json()["task_id"]

    cross = client.get(f"/api/agent/status/{task_id}", headers={"X-Tenant-ID": "tenant-beta"})
    assert cross.status_code == 403

    same = client.get(f"/api/agent/status/{task_id}", headers={"X-Tenant-ID": "tenant-alpha"})
    assert same.status_code == 200
