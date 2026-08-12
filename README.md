# AI Logistics Assistant 🚚🤖

An intelligent AI assistant for logistics and supply chain operations, built progressively to demonstrate modern AI engineering practices.

## 🎯 Project Vision

Executive-level AI assistant that understands logistics operations, provides real-time insights, and assists with supply chain decision-making.

## ✨ Features (Progressive Implementation)

### Phase 1: Foundation ✅
- [x] **Feature 1: Basic Chat** - Stateless AI conversation with logistics domain knowledge

### Phase 2: Memory (In Progress)
- [ ] **Feature 2: Session Memory** - Multi-turn conversations with context retention
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
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic models
│   └── config.py            # Configuration management
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

# 6. Test the API
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the key metrics for supply chain efficiency?"}'
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

**Current Status**: Feature 1 Complete ✅ | Next: Feature 2 (Session Memory)
