## Description
<!-- Brief description of what this PR accomplishes -->

Implements Feature X: [Feature Name]

## Changes
<!-- List the key changes -->
- [ ] New endpoint: `POST /api/...`
- [ ] New models: `...`
- [ ] Tests added
- [ ] Documentation updated in README.md

## Feature Checklist
- [ ] Code follows project style
- [ ] All tests pass locally
- [ ] Tested with Ollama (qwen2.5:3b)
- [ ] No secrets or API keys committed
- [ ] .env.example updated if new config added
- [ ] README.md feature checklist updated

## Testing Done
```bash
# Start server
uvicorn app.main:app --reload --port 8000

# Test endpoint
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test message"}'

# Run tests
pytest tests/ -v
```

## Screenshots
<!-- Add screenshots if UI changes -->

## Breaking Changes
<!-- Any breaking API changes? -->
None
