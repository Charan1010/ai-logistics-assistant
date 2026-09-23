"""
AI Logistics Assistant - Feature 1: Basic Chat
A stateless AI chatbot with logistics domain expertise.
"""
import httpx
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.models import (
    ChatRequest,
    ChatResponse,
    StructuredAnswer,
    StructuredChatRequest,
    StructuredChatResponse,
    SessionCreate,
    SessionResponse,
    SessionListResponse,
    HistoryResponse,
    MessageResponse,
    DocumentUploadResponse,
    DocumentResponse,
    DocumentListResponse,
    ChunkResponse,
    DocumentChunksResponse,
    VectorStoreStatsResponse,
    SearchRequest,
    SearchResult,
    SearchResponse,
    QueryClassification,
    KnowledgeDigest,
    RetrievalFeedbackRequest,
    RetrievalLogEntry,
    SmartChatRequest,
    SmartChatResponse,
    AgentRequest,
    AgentResponse,
    AgentStep,
    PlanRequest,
    PlanResponse,
    PlanStepResult,
    AgentTaskResponse,
    MCPServerInfo,
    MCPToolInfo,
    MCPServersResponse,
    MCPToolsResponse,
    MCPExecuteRequest,
    MCPExecuteResponse,
)
from app.llm_client import llm_client
from app.config import settings
from app.session_store import session_store
from app.document_processor import get_document_processor
from app.embeddings import get_embedding_model
from app.retrieval_memory import retrieval_memory_store
from app.vector_store import get_vector_store
from app.agent import run_agent, TOOLS_REGISTRY
from app.planner import make_plan, execute_plan
from app.task_store import task_store
from app.mcp_client import (
    call_mcp_tool,
    get_server_registry,
    list_mcp_tools,
)

app = FastAPI(
    title=settings.app_name,
    description="Intelligent AI assistant for logistics and supply chain operations",
    version="0.1.0"
)

# CORS middleware for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get UI directory path
UI_DIR = Path(__file__).parent.parent / "ui"

# Mount static files if UI directory exists
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


# System prompt for logistics domain
SYSTEM_PROMPT = """You are an expert AI assistant for logistics and supply chain operations.

Your expertise includes:
- Supply chain optimization and efficiency metrics
- Transportation and fleet management
- Warehouse operations and inventory control
- Last-mile delivery strategies
- International shipping and customs
- Real-time tracking and visibility
- Risk management and disruption handling

Respond in a professional, executive-level tone. Provide actionable insights with specific recommendations when possible. If you don't know something, be honest and suggest where the user might find that information.

Keep responses concise but comprehensive."""


STRUCTURED_OUTPUT_PROMPT = """You are an expert AI assistant for logistics and supply chain operations.

Return ONLY valid JSON with this exact schema:
{
  "summary": "string",
  "key_points": ["string", "string"],
  "recommendations": ["string", "string"],
  "risks": ["string", "string"],
  "confidence": 0.0
}

Rules:
- No markdown.
- No extra keys.
- confidence must be between 0 and 1.
- Keep key_points/recommendations/risks concise and actionable.
"""


QUERY_CLASSIFICATION_PROMPT = """You are a routing classifier for a logistics AI assistant.

Decide whether the user's question needs uploaded document context before answering.

Return ONLY valid JSON with this exact schema:
{
    "needs_retrieval": true,
    "confidence": 0.0,
    "query_type": "general"
}

query_type must be exactly one of:
- "general": common knowledge or broad logistics concepts that do not require uploaded documents
- "domain": asks about company/domain-specific policies, metrics, uploaded procedures, contracts, rates, or operational details
- "professional_document": asks about a financial, legal, compliance, regulatory, or complex technical document
- "ambiguous": unclear whether uploaded documents are needed

Rules:
- Use needs_retrieval=false for general knowledge questions.
- Use needs_retrieval=true for questions about uploaded documents, internal policies, specific company data, or named files.
- Use query_type="ambiguous" with low confidence if the request is vague.
- confidence must be between 0 and 1.
- No markdown. No extra keys.
"""


def _extract_json_object(raw_text: str) -> dict:
    """Extract and parse the first JSON object from model output."""
    text = raw_text.strip()

    # Fast path when response is already plain JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")

    candidate = text[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Structured output is not a JSON object")
    return parsed


def _fallback_structured_answer(raw_text: str) -> StructuredAnswer:
    """Return a safe structured fallback when strict JSON parsing fails."""
    cleaned = raw_text.strip()
    short = cleaned[:500] if cleaned else "Unable to parse structured output from model response."
    return StructuredAnswer(
        summary=short,
        key_points=[],
        recommendations=[],
        risks=["Response format mismatch from model"],
        confidence=0.4,
    )


def _fallback_query_classification() -> QueryClassification:
    """Return the conservative route when classification fails."""
    return QueryClassification(
        needs_retrieval=True,
        confidence=0.3,
        query_type="ambiguous",
    )


def _tenant_from_header(x_tenant_id: str | None) -> str | None:
    """Return active tenant or reject missing tenant when isolation is enabled."""
    if not settings.enable_multi_tenant:
        return None

    tenant_id = (x_tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required when multi-tenant mode is enabled")
    return tenant_id


def _assert_session_access(session_id: str, tenant_id: str | None):
    """Return a session after enforcing tenant ownership when enabled."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if settings.enable_multi_tenant and session.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Session belongs to a different tenant")
    return session


async def classify_query(message: str) -> QueryClassification:
    """Classify whether a user question needs retrieved document context."""
    messages = [
        {"role": "system", "content": QUERY_CLASSIFICATION_PROMPT},
        {"role": "user", "content": message},
    ]

    try:
        response_text = await llm_client.chat(messages)
        payload = _extract_json_object(response_text)
        return QueryClassification.model_validate(payload)
    except Exception:
        return _fallback_query_classification()


def _format_retrieved_context(results: list[SearchResult]) -> str:
    """Format retrieved chunks for the answer-generation prompt."""
    if not results:
        return "No relevant document chunks were found."

    sections = []
    for index, result in enumerate(results, start=1):
        sections.append(
            f"[Chunk {index} | file={result.filename} | score={result.score}]\n{result.text}"
        )
    return "\n\n".join(sections)


def _format_knowledge_digest(digest: KnowledgeDigest) -> str:
    """Format retrieval memory for prompt injection."""
    if digest.retrieval_count == 0:
        return ""

    parts = [
        "\n\nRetrieval memory digest:",
        digest.summary,
    ]
    if digest.query_patterns:
        parts.append("Recurring query patterns: " + "; ".join(digest.query_patterns))
    if digest.coverage_gaps:
        parts.append("Known coverage gaps: " + "; ".join(digest.coverage_gaps))
    return "\n".join(parts)


def _append_knowledge_digest(prompt: str, tenant_id: str | None) -> str:
    """Append retrieval memory when long-term context is enabled."""
    if not settings.enable_long_term_context:
        return prompt

    digest = retrieval_memory_store.build_digest(tenant_id=tenant_id)
    formatted = _format_knowledge_digest(digest)
    return prompt + formatted if formatted else prompt


def _history_messages_for_session(session_id: str | None, tenant_id: str | None = None) -> list[dict]:
    """Return prior session turns in chat-message format."""
    if not session_id:
        return []

    session = _assert_session_access(session_id, tenant_id)

    return [
        {"role": msg.role, "content": msg.content}
        for msg in session.messages[-20:]
    ]


def _is_session_memory_question(message: str) -> bool:
    """Detect questions that should be answered from conversation history."""
    text = message.lower()
    memory_terms = (
        "last question",
        "previous question",
        "what did i ask",
        "what was my question",
        "what was my last",
        "earlier in this chat",
        "earlier in this session",
        "this conversation",
        "our conversation",
        "we discussed",
    )
    return any(term in text for term in memory_terms)


def _answer_session_memory_question(message: str, history_messages: list[dict]) -> str:
    """Answer simple memory questions directly from stored prior turns."""
    text = message.lower()
    prior_user_messages = [
        msg["content"]
        for msg in history_messages
        if msg.get("role") == "user" and msg.get("content")
    ]

    if not prior_user_messages:
        return "I do not have any earlier user question in this selected session yet."

    if "last question" in text or "previous question" in text or "what did i ask" in text or "what was my question" in text or "what was my last" in text:
        return f'Your last question was: "{prior_user_messages[-1]}"'

    return "Earlier in this session, you asked: " + "; ".join(
        f'"{content}"' for content in prior_user_messages[-3:]
    )


def _search_document_context(message: str, top_k: int, document_id: str | None, tenant_id: str | None = None) -> list[SearchResult]:
    """Run vector retrieval and return API-shaped search results."""
    embedding_model = get_embedding_model()
    query_embedding = embedding_model.embed_text(message)
    vector_store = get_vector_store()
    ranked = vector_store.search_ranked(
        query_embedding,
        n_results=top_k,
        document_id=document_id,
        tenant_id=tenant_id,
    )

    return [
        SearchResult(
            chunk_id=r["chunk_id"],
            text=r["text"],
            score=r["score"],
            document_id=r["metadata"].get("document_id", ""),
            filename=r["metadata"].get("filename", ""),
            chunk_index=r["metadata"].get("chunk_index", 0),
        )
        for r in ranked
    ]


@app.get("/")
async def root():
    """Serve the web UI."""
    ui_file = UI_DIR / "index.html"
    if ui_file.exists():
        return FileResponse(ui_file)
    return {
        "status": "online",
        "app": settings.app_name,
        "version": "0.1.0",
        "features": ["basic_chat"],
        "model": llm_client.model
    }


@app.get("/api/status")
async def status():
    """API status endpoint."""
    return {
        "status": "online",
        "app": settings.app_name,
        "version": "0.1.0",
        "features": ["basic_chat", "structured_output", "conversation_history", "document_ingestion", "semantic_search", "smart_router", "retrieval_memory", "agent_tools"],
        "model": llm_client.model,
        "multi_tenant": settings.enable_multi_tenant,
        "long_term_context": settings.enable_long_term_context,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, x_tenant_id: str | None = Header(default=None)):
    """
    Chat endpoint with optional session support.

    If session_id is provided, conversation history is maintained.
    Otherwise, each request is independent (stateless).
    """
    try:
        tenant_id = _tenant_from_header(x_tenant_id) if request.session_id else None
        # Build messages with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # If session ID provided, load conversation history
        if request.session_id:
            session = _assert_session_access(request.session_id, tenant_id)

            # Add previous messages from session
            for msg in session.messages:
                messages.append({"role": msg.role, "content": msg.content})

        # Add current user message
        messages.append({"role": "user", "content": request.message})

        # Get LLM response
        response_text = await llm_client.chat(messages)

        # Store messages in session if session_id provided
        if request.session_id:
            session_store.add_message(request.session_id, "user", request.message)
            session_store.add_message(request.session_id, "assistant", response_text)

        return ChatResponse(
            response=response_text,
            model=llm_client.model
        )

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.post("/api/chat/structured", response_model=StructuredChatResponse)
async def chat_structured(request: StructuredChatRequest):
    """Structured chat endpoint that returns schema-validated JSON output."""
    try:
        messages = [
            {"role": "system", "content": STRUCTURED_OUTPUT_PROMPT},
            {"role": "user", "content": request.message},
        ]

        response_text = await llm_client.chat(messages)

        try:
            payload = _extract_json_object(response_text)
            structured = StructuredAnswer.model_validate(payload)
        except Exception:
            structured = _fallback_structured_answer(response_text)

        return StructuredChatResponse(output=structured, model=llm_client.model)

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Session Management Endpoints

@app.post("/api/sessions", response_model=SessionResponse, status_code=201)
async def create_session(request: SessionCreate, x_tenant_id: str | None = Header(default=None)):
    """Create a new conversation session."""
    tenant_id = _tenant_from_header(x_tenant_id)
    session = session_store.create_session(metadata=request.metadata, tenant_id=tenant_id)
    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
        metadata=session.metadata,
        tenant_id=session.tenant_id,
    )


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(limit: int = 100, x_tenant_id: str | None = Header(default=None)):
    """List all active sessions."""
    tenant_id = _tenant_from_header(x_tenant_id)
    sessions = session_store.list_sessions(limit=limit, tenant_id=tenant_id)
    return SessionListResponse(
        sessions=[
            SessionResponse(
                session_id=s.session_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=len(s.messages),
                metadata=s.metadata,
                tenant_id=s.tenant_id,
            )
            for s in sessions
        ],
        total=len(sessions)
    )


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, x_tenant_id: str | None = Header(default=None)):
    """Get details for a specific session."""
    tenant_id = _tenant_from_header(x_tenant_id)
    session = _assert_session_access(session_id, tenant_id)

    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
        metadata=session.metadata,
        tenant_id=session.tenant_id,
    )


@app.get("/api/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(session_id: str, limit: Optional[int] = None, x_tenant_id: str | None = Header(default=None)):
    """Get conversation history for a session."""
    tenant_id = _tenant_from_header(x_tenant_id)
    _assert_session_access(session_id, tenant_id)

    messages = session_store.get_history(session_id, limit=limit)
    return HistoryResponse(
        session_id=session_id,
        messages=[
            MessageResponse(
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp
            )
            for msg in messages
        ],
        total=len(messages)
    )


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, x_tenant_id: str | None = Header(default=None)):
    """Delete a session and its history."""
    tenant_id = _tenant_from_header(x_tenant_id)
    _assert_session_access(session_id, tenant_id)
    deleted = session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return None


# Document Management Endpoints

# Create upload directory
UPLOAD_DIR = Path("./data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Supported file types
SUPPORTED_FILE_TYPES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


@app.post("/api/documents/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(file: UploadFile = File(...), x_tenant_id: str | None = Header(default=None)):
    """
    Upload and process a document.

    Supported formats: PDF, TXT, DOCX
    """
    try:
        tenant_id = _tenant_from_header(x_tenant_id)

        # Validate file type
        if file.content_type not in SUPPORTED_FILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Supported: PDF, TXT, DOCX"
            )

        file_type = SUPPORTED_FILE_TYPES[file.content_type]

        # Generate unique document ID
        document_id = str(uuid.uuid4())

        # Save uploaded file temporarily
        file_path = UPLOAD_DIR / f"{document_id}_{file.filename}"
        content = await file.read()
        file_size = len(content)

        with open(file_path, "wb") as f:
            f.write(content)

        # Parse document
        doc_processor = get_document_processor()
        text = doc_processor.parse_file(file_path, file_type)

        if not text or len(text.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Document is empty or could not be parsed"
            )

        # Chunk document
        metadata = {
            "filename": file.filename,
            "file_type": file_type,
            "file_size": file_size,
        }
        if tenant_id:
            metadata["tenant_id"] = tenant_id
        chunks = doc_processor.chunk_text(text, metadata=metadata)

        # Generate embeddings
        embedding_model = get_embedding_model()
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = embedding_model.embed_batch(chunk_texts)

        # Store in vector database
        vector_store = get_vector_store()
        chunks_added = vector_store.add_document(
            document_id=document_id,
            filename=file.filename,
            chunks=chunk_texts,
            embeddings=embeddings,
            metadata=metadata
        )

        return DocumentUploadResponse(
            document_id=document_id,
            filename=file.filename,
            file_type=file_type,
            file_size=file_size,
            chunks_created=chunks_added,
            upload_date=datetime.now(),
            tenant_id=tenant_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}"
        )


@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents(x_tenant_id: str | None = Header(default=None)):
    """List all uploaded documents."""
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        vector_store = get_vector_store()
        documents = vector_store.list_documents(tenant_id=tenant_id)

        return DocumentListResponse(
            documents=[
                DocumentResponse(
                    document_id=doc["document_id"],
                    filename=doc["filename"],
                    upload_date=doc["upload_date"],
                    total_chunks=doc["total_chunks"],
                    tenant_id=doc.get("tenant_id"),
                )
                for doc in documents
            ],
            total=len(documents)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing documents: {str(e)}"
        )


@app.get("/api/documents/stats", response_model=VectorStoreStatsResponse)
async def get_vector_store_stats(x_tenant_id: str | None = Header(default=None)):
    """Get vector store statistics."""
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        vector_store = get_vector_store()
        stats = vector_store.get_stats(tenant_id=tenant_id)

        return VectorStoreStatsResponse(
            total_documents=stats["total_documents"],
            total_chunks=stats["total_chunks"],
            collection_name=stats["collection_name"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving stats: {str(e)}"
        )


@app.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, x_tenant_id: str | None = Header(default=None)):
    """Get details for a specific document."""
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        vector_store = get_vector_store()
        documents = vector_store.list_documents(tenant_id=tenant_id)

        doc = next((d for d in documents if d["document_id"] == document_id), None)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse(
            document_id=doc["document_id"],
            filename=doc["filename"],
            upload_date=doc["upload_date"],
            total_chunks=doc["total_chunks"],
            tenant_id=doc.get("tenant_id"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving document: {str(e)}"
        )


@app.get("/api/documents/{document_id}/chunks", response_model=DocumentChunksResponse)
async def get_document_chunks(document_id: str, x_tenant_id: str | None = Header(default=None)):
    """Get all chunks for a specific document."""
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        vector_store = get_vector_store()
        chunks = vector_store.get_document_chunks(document_id, tenant_id=tenant_id)

        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentChunksResponse(
            document_id=document_id,
            chunks=[
                ChunkResponse(
                    chunk_id=chunk["id"],
                    text=chunk["text"],
                    chunk_index=chunk["metadata"].get("chunk_index", 0),
                    metadata=chunk["metadata"]
                )
                for chunk in chunks
            ],
            total=len(chunks)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chunks: {str(e)}"
        )


@app.delete("/api/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, x_tenant_id: str | None = Header(default=None)):
    """Delete a document and all its chunks."""
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        vector_store = get_vector_store()
        chunks_deleted = vector_store.delete_document(document_id, tenant_id=tenant_id)

        if chunks_deleted == 0:
            raise HTTPException(status_code=404, detail="Document not found")

        # Clean up uploaded file if it exists
        for file in UPLOAD_DIR.glob(f"{document_id}_*"):
            file.unlink()

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting document: {str(e)}"
        )


# Semantic Search Endpoints (Feature 5)

@app.post("/api/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest, x_tenant_id: str | None = Header(default=None)):
    """
    Semantic search across indexed document chunks.

    Embeds the query with the same model used during ingestion, then finds the
    top_k most similar chunks by vector distance. Optionally scoped to a single
    document via document_id. Returns a similarity score (0.0-1.0) per result —
    a high score means the text is close in meaning, not a guarantee it answers
    the question.
    """
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        embedding_model = get_embedding_model()
        query_embedding = embedding_model.embed_text(request.query)

        vector_store = get_vector_store()
        ranked = vector_store.search_ranked(
            query_embedding,
            n_results=request.top_k,
            document_id=request.document_id,
            tenant_id=tenant_id,
        )

        results = [
            SearchResult(
                chunk_id=r["chunk_id"],
                text=r["text"],
                score=r["score"],
                document_id=r["metadata"].get("document_id", ""),
                filename=r["metadata"].get("filename", ""),
                chunk_index=r["metadata"].get("chunk_index", 0),
            )
            for r in ranked
        ]

        return SearchResponse(query=request.query, results=results, total=len(results))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error performing search: {str(e)}"
        )


@app.get("/api/search/stats", response_model=VectorStoreStatsResponse)
async def search_stats(x_tenant_id: str | None = Header(default=None)):
    """Vector store statistics — total indexed chunks/documents (alias of /api/documents/stats)."""
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        vector_store = get_vector_store()
        stats = vector_store.get_stats(tenant_id=tenant_id)

        return VectorStoreStatsResponse(
            total_documents=stats["total_documents"],
            total_chunks=stats["total_chunks"],
            collection_name=stats["collection_name"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving stats: {str(e)}"
        )


# Smart Router Endpoint (Feature 6)

@app.post("/api/chat/smart", response_model=SmartChatResponse)
async def smart_chat(request: SmartChatRequest, x_tenant_id: str | None = Header(default=None)):
    """
    Route a question through LLM-only, RAG, or hybrid answering.

    The router first classifies the query. Confident general questions skip
    retrieval; confident document-dependent questions use RAG; uncertain cases
    use hybrid retrieval so the LLM can use context if it helps.
    """
    try:
        tenant_id = _tenant_from_header(x_tenant_id)
        history_messages = _history_messages_for_session(request.session_id, tenant_id=tenant_id)

        if history_messages and _is_session_memory_question(request.message):
            classification = QueryClassification(
                needs_retrieval=False,
                confidence=1.0,
                query_type="general",
            )
            source = "llm"
            retrieval_method = "Session memory: answered from the selected conversation history, no document retrieval used."
        else:
            classification = await classify_query(request.message)

            if classification.confidence > 0.6 and not classification.needs_retrieval:
                source = "llm"
            elif classification.confidence > 0.6 and classification.needs_retrieval:
                source = "rag"
            else:
                source = "hybrid"

        retrieved_results: list[SearchResult] = []
        retrieval_log_id = None
        if source in ("rag", "hybrid"):
            retrieved_results = _search_document_context(
                request.message,
                top_k=request.top_k,
                document_id=request.document_id,
                tenant_id=tenant_id,
            )
            retrieval_log = retrieval_memory_store.log_retrieval(
                query=request.message,
                retrieved_chunks=[result.chunk_id for result in retrieved_results],
                retrieval_scores=[result.score for result in retrieved_results],
                source_used=source,
                session_id=request.session_id,
                tenant_id=tenant_id,
            )
            retrieval_log_id = retrieval_log.id

        if history_messages and _is_session_memory_question(request.message):
            answer = _answer_session_memory_question(request.message, history_messages)

            if request.session_id:
                session_store.add_message(request.session_id, "user", request.message)
                session_store.add_message(request.session_id, "assistant", answer)

            return SmartChatResponse(
                answer=answer,
                source="llm",
                chunks_used=0,
                confidence=classification.confidence,
                retrieval_method=retrieval_method,
                classification=classification,
                model=llm_client.model,
            )

        if source == "llm":
            generation_system_prompt = f"""{SYSTEM_PROMPT}

Conversation history may be included after this system message as prior user/assistant turns.
If the user asks what they asked previously, what their last question was, or what was discussed earlier, answer directly from those prior user turns. Do not ask them to repeat information that is already present in the conversation history."""
            if not history_messages or not _is_session_memory_question(request.message):
                retrieval_method = "LLM direct: router classified this as answerable without uploaded documents."
        else:
            context = _format_retrieved_context(retrieved_results)
            path_label = "RAG" if source == "rag" else "Hybrid"
            generation_system_prompt = f"""{SYSTEM_PROMPT}

Use the retrieved document context below when it directly helps answer the user.
If the context does not contain the answer, say what is missing and answer only from general logistics knowledge where appropriate.

Retrieved context:
{context}"""
            retrieval_method = (
                f"{path_label}: router confidence={classification.confidence:.2f}; "
                f"retrieved {len(retrieved_results)} chunk(s) using vector similarity."
            )

        generation_system_prompt = _append_knowledge_digest(generation_system_prompt, tenant_id=tenant_id)

        messages = [{"role": "system", "content": generation_system_prompt}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": request.message})

        answer = await llm_client.chat(messages)

        if request.session_id:
            session_store.add_message(request.session_id, "user", request.message)
            session_store.add_message(request.session_id, "assistant", answer)

        return SmartChatResponse(
            answer=answer,
            source=source,
            chunks_used=len(retrieved_results),
            confidence=classification.confidence,
            retrieval_method=retrieval_method,
            classification=classification,
            model=llm_client.model,
            retrieval_log_id=retrieval_log_id,
        )

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error in smart router: {str(e)}"
        )


# Retrieval Memory Endpoints (Feature 6 Part C)

@app.get("/api/retrieval-logs", response_model=list[RetrievalLogEntry])
async def list_retrieval_logs(limit: int = 100, x_tenant_id: str | None = Header(default=None)):
    """Return recent retrieval-memory log entries."""
    tenant_id = _tenant_from_header(x_tenant_id)
    return retrieval_memory_store.list_entries(tenant_id=tenant_id, limit=limit)


@app.get("/api/knowledge-digest", response_model=KnowledgeDigest)
async def knowledge_digest(x_tenant_id: str | None = Header(default=None)):
    """Return the current retrieval-memory digest."""
    tenant_id = _tenant_from_header(x_tenant_id)
    return retrieval_memory_store.build_digest(tenant_id=tenant_id)


@app.post("/api/retrieval-logs/{entry_id}/feedback", response_model=RetrievalLogEntry)
async def retrieval_feedback(entry_id: str, request: RetrievalFeedbackRequest, x_tenant_id: str | None = Header(default=None)):
    """Mark a retrieval-memory log entry as helpful or unhelpful."""
    tenant_id = _tenant_from_header(x_tenant_id)
    entry = retrieval_memory_store.set_feedback(entry_id, request.was_helpful, tenant_id=tenant_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Retrieval log entry not found")
    return entry


# Agent Endpoints (Feature 7)

@app.get("/api/agent/tools")
async def list_agent_tools():
    """Return the tool schemas the agent can invoke."""
    return {
        "tools": [
            {
                "name": name,
                "description": schema["function"]["description"],
                "parameters": schema["function"]["parameters"],
            }
            for name, (_, schema) in TOOLS_REGISTRY.items()
        ],
        "total": len(TOOLS_REGISTRY),
    }


@app.post("/api/agent/run", response_model=AgentResponse)
async def agent_run(request: AgentRequest, x_tenant_id: str | None = Header(default=None)):
    """
    Run one agent turn: LLM chooses tools, we execute them, LLM synthesises answer.
    """
    try:
        tenant_id = _tenant_from_header(x_tenant_id) if request.session_id else None
        if request.session_id:
            _assert_session_access(request.session_id, tenant_id)

        agent_output = await run_agent(request.message, session_id=request.session_id)

        if request.session_id:
            session_store.add_message(request.session_id, "user", request.message)
            session_store.add_message(request.session_id, "assistant", agent_output["result"])

        return AgentResponse(
            result=agent_output["result"],
            steps=[AgentStep(**step) for step in agent_output["steps"]],
            tools_used=agent_output["tools_used"],
            model=llm_client.model,
        )

    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


# Multi-Step Agent Endpoints (Feature 8)

def _task_to_response(task) -> AgentTaskResponse:
    return AgentTaskResponse(
        task_id=task.task_id,
        status=task.status,
        message=task.message,
        plan=task.plan or [],
        steps_completed=[PlanStepResult(**step) for step in task.steps_completed or []],
        result=task.result,
        error=task.error,
        session_id=task.session_id,
    )


@app.post("/api/agent/plan", response_model=PlanResponse)
async def agent_plan(
    request: PlanRequest,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None),
):
    """
    Decompose the request into steps and start executing them in the background.
    Client polls /api/agent/status/{task_id} for progress.
    """
    try:
        tenant_id = _tenant_from_header(x_tenant_id) if request.session_id else None
        if request.session_id:
            _assert_session_access(request.session_id, tenant_id)

        task = task_store.create_task(
            message=request.message,
            session_id=request.session_id,
            tenant_id=tenant_id,
        )

        plan = await make_plan(request.message)
        task_store.update_task(task.task_id, plan=plan, status="executing")

        background_tasks.add_task(execute_plan, task.task_id)

        return PlanResponse(
            task_id=task.task_id,
            status="executing",
            plan=plan,
            session_id=request.session_id,
        )

    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planner error: {str(e)}")


@app.get("/api/agent/status/{task_id}", response_model=AgentTaskResponse)
async def agent_status(task_id: str, x_tenant_id: str | None = Header(default=None)):
    """Poll a multi-step task's live progress."""
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    if task.tenant_id is not None:
        tenant_id = _tenant_from_header(x_tenant_id)
        if tenant_id != task.tenant_id:
            raise HTTPException(status_code=403, detail="Cross-tenant task access denied")

    return _task_to_response(task)


# MCP Endpoints (Feature 9)

@app.get("/api/mcp/servers", response_model=MCPServersResponse)
async def list_mcp_servers():
    """List configured MCP servers and whether they are enabled."""
    entries = get_server_registry()
    return MCPServersResponse(
        servers=[MCPServerInfo(**e) for e in entries],
        total=len(entries),
    )


@app.get("/api/mcp/tools", response_model=MCPToolsResponse)
async def list_all_mcp_tools():
    """Discover and return every tool exposed by enabled MCP servers."""
    try:
        tools = await list_mcp_tools()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MCP discovery failed: {e}")

    return MCPToolsResponse(
        tools=[MCPToolInfo(**t) for t in tools],
        total=len(tools),
    )


@app.post("/api/mcp/execute", response_model=MCPExecuteResponse)
async def execute_mcp_tool(request: MCPExecuteRequest):
    """Directly invoke an MCP tool. Bypasses the LLM — useful for debugging."""
    try:
        result = await call_mcp_tool(request.tool_name, request.arguments)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MCP execution failed: {e}")

    return MCPExecuteResponse(tool_name=request.tool_name, result=result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
