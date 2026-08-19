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

### Phase 2: Memory (In Progress)
- [x] **Feature 2: Structured Output** - Schema-validated JSON answers for reliable downstream use
- [ ] **Feature 3: Conversation History** - Session management and retrieval

### Phase 3: Knowledge (Planned)
- [ ] **Feature 4: Document Ingestion** - RAG pipeline for company documents
- [ ] **Feature 5: Semantic Search** - Vector-based document retrieval
- [ ] **Feature 6: Smart Routing** - Intent-based query routing

### Phase 4: Intelligence (Planned)
- [ ] **Feature 7: Basic Agent** - Function calling and tool use
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
│   ├── main.py              # FastAPI application + UI routes
│   ├── models.py            # Pydantic models
│   ├── config.py            # Configuration management
│   └── llm_client.py        # Ollama integration
├── ui/
│   └── index.html           # Web chat interface
├── tests/
│   └── test_api.py          # API tests
├── .github/
│   └── workflows/
│       └── ci.yml           # CI/CD pipeline
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
2. **Click example queries** or type your own question
3. **Watch the AI respond** in real-time with typing indicators
4. **Ask follow-up questions** about logistics and supply chain

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
- **Vector DB**: ChromaDB (coming in Phase 3)
- **Testing**: pytest
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

**Current Status**: Feature 2 Complete ✅ (Structured Output) | Next: Feature 3 (Conversation History)
