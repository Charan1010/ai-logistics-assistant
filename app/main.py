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
from fastapi import FastAPI, HTTPException, UploadFile, File
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
)
from app.llm_client import llm_client
from app.config import settings
from app.session_store import session_store
from app.document_processor import get_document_processor
from app.embeddings import get_embedding_model
from app.vector_store import get_vector_store

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
        "features": ["basic_chat", "structured_output", "conversation_history", "document_ingestion", "semantic_search"],
        "model": llm_client.model
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with optional session support.

    If session_id is provided, conversation history is maintained.
    Otherwise, each request is independent (stateless).
    """
    try:
        # Build messages with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # If session ID provided, load conversation history
        if request.session_id:
            session = session_store.get_session(request.session_id)
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail=f"Session {request.session_id} not found"
                )

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
async def create_session(request: SessionCreate):
    """Create a new conversation session."""
    session = session_store.create_session(metadata=request.metadata)
    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
        metadata=session.metadata
    )


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(limit: int = 100):
    """List all active sessions."""
    sessions = session_store.list_sessions(limit=limit)
    return SessionListResponse(
        sessions=[
            SessionResponse(
                session_id=s.session_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=len(s.messages),
                metadata=s.metadata
            )
            for s in sessions
        ],
        total=len(sessions)
    )


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get details for a specific session."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
        metadata=session.metadata
    )


@app.get("/api/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(session_id: str, limit: Optional[int] = None):
    """Get conversation history for a session."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
async def delete_session(session_id: str):
    """Delete a session and its history."""
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
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and process a document.

    Supported formats: PDF, TXT, DOCX
    """
    try:
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
            upload_date=datetime.now()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}"
        )


@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents():
    """List all uploaded documents."""
    try:
        vector_store = get_vector_store()
        documents = vector_store.list_documents()

        return DocumentListResponse(
            documents=[
                DocumentResponse(
                    document_id=doc["document_id"],
                    filename=doc["filename"],
                    upload_date=doc["upload_date"],
                    total_chunks=doc["total_chunks"]
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
async def get_vector_store_stats():
    """Get vector store statistics."""
    try:
        vector_store = get_vector_store()
        stats = vector_store.get_stats()

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
async def get_document(document_id: str):
    """Get details for a specific document."""
    try:
        vector_store = get_vector_store()
        documents = vector_store.list_documents()

        doc = next((d for d in documents if d["document_id"] == document_id), None)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse(
            document_id=doc["document_id"],
            filename=doc["filename"],
            upload_date=doc["upload_date"],
            total_chunks=doc["total_chunks"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving document: {str(e)}"
        )


@app.get("/api/documents/{document_id}/chunks", response_model=DocumentChunksResponse)
async def get_document_chunks(document_id: str):
    """Get all chunks for a specific document."""
    try:
        vector_store = get_vector_store()
        chunks = vector_store.get_document_chunks(document_id)

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
async def delete_document(document_id: str):
    """Delete a document and all its chunks."""
    try:
        vector_store = get_vector_store()
        chunks_deleted = vector_store.delete_document(document_id)

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
async def search_documents(request: SearchRequest):
    """
    Semantic search across indexed document chunks.

    Embeds the query with the same model used during ingestion, then finds the
    top_k most similar chunks by vector distance. Optionally scoped to a single
    document via document_id. Returns a similarity score (0.0-1.0) per result —
    a high score means the text is close in meaning, not a guarantee it answers
    the question.
    """
    try:
        embedding_model = get_embedding_model()
        query_embedding = embedding_model.embed_text(request.query)

        vector_store = get_vector_store()
        ranked = vector_store.search_ranked(
            query_embedding,
            n_results=request.top_k,
            document_id=request.document_id,
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
async def search_stats():
    """Vector store statistics — total indexed chunks/documents (alias of /api/documents/stats)."""
    try:
        vector_store = get_vector_store()
        stats = vector_store.get_stats()

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
