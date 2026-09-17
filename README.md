# AI Logistics Assistant 🚚🤖

An intelligent AI assistant for logistics and supply chain operations, built progressively to demonstrate modern AI engineering practices.

## 🎯 Project Vision

Executive-level AI assistant that understands logistics operations, provides real-time insights, and assists with supply chain decision-making.

## ✨ Features (Progressive Implementation)

### Phase 1: Foundation ✅
- [x] **Feature 1: Basic Chat** - Stateless AI conversation with logistics domain knowledge
  - Beautiful web UI with real-time chat
  - REST API endpoint for programmatic access
  - Typing indicators and smooth animations
  - Example queries for quick start

### Phase 2: Memory ✅
- [x] **Feature 2: Structured Output** - Schema-validated JSON answers for reliable downstream use
- [x] **Feature 3: Conversation History** - Session management and multi-turn conversations

### Phase 3: Knowledge ✅ (in progress)
- [x] **Feature 4: Document Ingestion** - Upload PDF/TXT/DOCX, sentence-aware chunking, local embeddings, ChromaDB storage
- [x] **Feature 5: Semantic Search** - Vector similarity search over indexed chunks with 0.0-1.0 relevance scores
- [x] **Feature 6: Smart Routing** - LLM/RAG/hybrid route selection with transparent audit trail
  - Optional multi-tenant isolation with `X-Tenant-ID` scoped sessions, documents, and searches
  - Optional retrieval memory digest that learns from prior RAG/hybrid retrievals

### Phase 4: Intelligence (in progress)
- [x] **Feature 7: Basic Agent** - Tool calling with 4 logistics tools and transparent audit trail
- [ ] **Feature 8: Multi-Step Agent** - Complex task decomposition
- [ ] **Feature 9: MCP Integration** - Model Context Protocol for external tools

### Phase 5: Production (Planned)
- [ ] **Feature 10: Multimodal AI** - Image/document understanding
- [ ] **Feature 11: Production Design** - Error handling, monitoring, rate limiting
- [ ] **Feature 12: Containerization** - Docker deployment ready

## 🏗️ Architecture

```
ai-logistics-assistant/
├── app/
│   ├── main.py                # FastAPI application + UI routes
│   ├── models.py              # Pydantic models
│   ├── config.py              # Configuration management
│   ├── llm_client.py          # Ollama integration
│   ├── session_store.py       # In-memory conversation history (Feature 3)
│   ├── document_processor.py  # PDF/TXT/DOCX parsing + sentence-aware chunking (Feature 4)
│   ├── embeddings.py          # Local sentence-transformers embedding model (Feature 4/5)
│   ├── retrieval_memory.py    # Retrieval log + knowledge digest (Feature 6 Part C)
│   └── vector_store.py        # ChromaDB storage + ranked similarity search (Feature 4/5)
├── ui/
│   └── index.html             # Tabbed web UI: Chat, Structured, Smart, Documents, Search, Memory
├── tests/
│   ├── conftest.py            # Offline/SSL env setup for tests
│   └── test_api.py            # API tests (52 tests across all features)
├── data/
│   ├── chroma/                # Persisted vector DB (gitignored)
│   └── uploads/                # Uploaded source files (gitignored)
├── .github/
│   └── workflows/
│       └── ci.yml             # CI/CD pipeline
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Charan1010/ai-logistics-assistant.git
cd ai-logistics-assistant

# 2. Set up Python virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your settings (uses local Ollama by default)

# 5. Start the server
uvicorn app.main:app --reload --port 8000

# 6. Open the web UI
# Visit http://localhost:8000 in your browser
```

### Using the Web UI 🌐

1. **Open your browser** and go to `http://localhost:8000`
2. **Chat tab** - ask questions, sessions are tracked automatically; use History to revisit past conversations
3. **Structured tab** - get a schema-validated summary/key-points/recommendations/risks/confidence breakdown
4. **Smart tab** - ask a question and let the router choose LLM-only, RAG, or hybrid with an audit trail
5. **Documents tab** - drag-and-drop or click to upload PDF/TXT/DOCX files; view live chunk/document counts
6. **Search tab** - ask a question and get ranked, scored chunks from your uploaded documents (optionally scoped to one document)
7. **Memory tab** - inspect retrieval logs, top chunks, query patterns, coverage gaps, and mark retrievals helpful/unhelpful
8. **Agent tab** - ask the logistics agent to check shipments, estimate delivery, open tickets, or look up warehouse KPIs — see the audit trail of every tool it calls

When `ENABLE_MULTI_TENANT=true`, the top bar shows tenant mode as `isolated`. Type a tenant name like `tenant-alpha`, click **Switch**, and the UI reloads sessions/documents/search filters for that tenant. Recently used tenants appear in the tenant dropdown; the backend does not expose a global tenant registry, so this list is stored locally in your browser.

### Using the API 🔌

```bash
# Test with curl
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the key metrics for supply chain efficiency?"}'

# Structured output endpoint
curl -X POST http://localhost:8000/api/chat/structured \
  -H "Content-Type: application/json" \
  -d '{"message": "Summarize current logistics performance and risks"}'

# Create a conversation session
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{}'

# Chat with session (multi-turn conversation)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are supply chain KPIs?", "session_id": "<session-id>"}'

# Get conversation history
curl http://localhost:8000/api/sessions/<session-id>/history

# Upload a document (Feature 4)
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@company_handbook.pdf"

# List indexed documents
curl http://localhost:8000/api/documents

# Semantic search over indexed documents (Feature 5)
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our on-time delivery target?", "top_k": 5}'

# Vector store stats
curl http://localhost:8000/api/documents/stats

# Smart routed chat (Feature 6)
curl -X POST http://localhost:8000/api/chat/smart \
  -H "Content-Type: application/json" \
  -d '{"message": "Does this question need our uploaded documents?", "top_k": 3}'

# Multi-tenant mode (Feature 6 Part B)
# First set ENABLE_MULTI_TENANT=true in .env, then send X-Tenant-ID.
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant-alpha" \
  -d '{}'

curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant-alpha" \
  -d '{"query": "premium delivery target", "top_k": 5}'

# Retrieval memory (Feature 6 Part C)
curl http://localhost:8000/api/knowledge-digest \
  -H "X-Tenant-ID: tenant-alpha"

curl http://localhost:8000/api/retrieval-logs \
  -H "X-Tenant-ID: tenant-alpha"

curl -X POST http://localhost:8000/api/retrieval-logs/<entry-id>/feedback \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant-alpha" \
  -d '{"was_helpful": false}'

# Logistics agent with tool calling (Feature 7)
curl http://localhost:8000/api/agent/tools

curl -X POST http://localhost:8000/api/agent/run \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant-alpha" \
  -d '{"message": "Where is my shipment TRK-42?"}'
```

Agent response shape:

```json
{
  "result": "Your shipment TRK-42 is in transit with FedEx Freight...",
  "steps": [
    {
      "tool": "check_shipment_status",
      "args": {"tracking_number": "TRK-42"},
      "result": {"status": "in_transit", "carrier": "FedEx Freight", "..." : "..."}
    }
  ],
  "tools_used": ["check_shipment_status"],
  "model": "qwen2.5:3b"
}
```

Structured response shape:

```json
{
  "output": {
    "summary": "...",
    "key_points": ["..."],
    "recommendations": ["..."],
    "risks": ["..."],
    "confidence": 0.0
  },
  "model": "qwen2.5:3b"
}
```

Smart response shape:

```json
{
  "answer": "...",
  "source": "llm | rag | hybrid | pageindex",
  "chunks_used": 0,
  "confidence": 0.0,
  "retrieval_method": "...",
  "classification": {
    "needs_retrieval": true,
    "confidence": 0.0,
    "query_type": "general | domain | professional_document | ambiguous"
  },
  "retrieval_log_id": "optional-log-id-when-retrieval-ran",
  "model": "qwen2.5:3b"
}
```

Retrieval memory digest shape:

```json
{
  "generated_at": "2026-09-09T00:00:00",
  "tenant_id": "tenant-alpha",
  "top_chunks": ["chunk-id"],
  "query_patterns": ["Frequent query term: delivery"],
  "coverage_gaps": ["Low-confidence retrieval: ..."],
  "summary": "Observed retrieval patterns...",
  "retrieval_count": 3
}
```

## 🧪 Testing

```bash
# Run tests
pytest tests/ -v

# Test with coverage
pytest tests/ --cov=app --cov-report=html
```

## 🛠️ Tech Stack

- **Framework**: FastAPI (Python 3.11+)
- **LLM**: Ollama (qwen2.5:3b - local, privacy-first)
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2, local/offline)
- **Vector DB**: ChromaDB (persisted locally under `data/chroma`)
- **Document parsing**: pypdf, python-docx
- **Testing**: pytest (52 tests, mocked LLM calls)
- **CI/CD**: GitHub Actions

## 📚 Learning Path

This project demonstrates:
- ✅ Clean code architecture with separation of concerns
- ✅ Progressive feature development with proper git workflow
- ✅ Test-driven development practices
- ✅ CI/CD automation
- ✅ Professional documentation
- ✅ Privacy-first AI (local Ollama deployment)

Each feature is developed in a separate branch with proper PR review before merging to main.

## 🤝 Contributing

This is a personal learning project, but suggestions are welcome! See [GIT_WORKFLOW.md](GIT_WORKFLOW.md) for development practices.

## 📝 License

MIT License - See LICENSE file for details

## 🎓 Acknowledgments

Built as part of AI Engineering learning journey focusing on:
- LLM application development
- RAG (Retrieval Augmented Generation)
- AI agents and tool use
- Production-ready AI systems

---

**Current Status**: Features 1-5 Complete ✅ (Chat, Structured Output, Memory, Document Ingestion, Semantic Search) | Next: Feature 6 (Smart Routing)
