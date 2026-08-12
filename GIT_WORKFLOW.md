# Git Workflow Guide

## 📋 Overview

This project follows a **feature branch workflow** with conventional commits and PR-based reviews.

## 🌳 Branch Strategy

```
main (protected, production-ready)
  ├── feature/basic-chat
  ├── feature/session-memory
  ├── feature/document-rag
  └── hotfix/bug-description
```

## 🔄 Development Workflow

### 1. Start a New Feature

```bash
# Make sure you're on main and up to date
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/session-memory
```

### 2. Make Changes

Work on your feature, test thoroughly locally.

### 3. Commit with Conventional Commits

```bash
git add .
git commit -m "feat: add session memory support

- Implemented in-memory session store
- Added UUID-based session IDs
- Created session management endpoints
- Tested multi-turn conversations"
```

**Commit Types:**
- `feat:` New feature (triggers version bump)
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code formatting (no logic change)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance (dependencies, config)

### 4. Push and Create PR

```bash
# Push your branch
git push -u origin feature/session-memory

# Go to GitHub and create Pull Request
# - Fill out the PR template
# - Wait for CI checks to pass
# - Request review if working with others
```

### 5. After PR Approval

```bash
# Merge on GitHub (use "Squash and merge" for clean history)

# Update local main
git checkout main
git pull origin main

# Delete feature branch
git branch -d feature/session-memory
git push origin --delete feature/session-memory
```

## ✅ Pre-Commit Checklist

Before committing, make sure:
- [ ] Code runs without errors
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] No secrets in code (no API keys!)
- [ ] .env.example updated if you added new config
- [ ] README.md updated if you added a feature

## 📝 Commit Message Examples

### Good ✅

```
feat: implement session-based chat memory

- Added session store with create/get/add_message functions
- Modified chat endpoint to accept session_id
- Maintains conversation history with context window
- Updated README with Feature 2 completion
```

```
fix: handle empty responses from LLM gracefully

- Added try/except around LLM client calls
- Return user-friendly error message
- Added test case for LLM timeout scenario
```

### Bad ❌

```
updated stuff
```

```
fixed bugs
```

```
changes
```

## 🚀 Quick Commands Reference

```bash
# Check current status
git status

# View commit history (pretty)
git log --oneline --graph --decorate --all

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Discard all uncommitted changes
git checkout .

# Update feature branch with latest main
git checkout feature/my-branch
git rebase main
```

## 🔍 CI/CD Pipeline

Every push and PR triggers automated checks:

✅ **Code Quality**
- Linting with ruff
- Import validation

✅ **Security**
- Secret scanning (no API keys allowed!)
- .env.example presence check

✅ **Testing**
- Unit tests run
- Basic import checks

✅ **PR Validation**
- Conventional commit format
- PR size warnings (>500 lines)

See `.github/workflows/ci.yml` for full pipeline details.

## 🎯 Best Practices

1. **Small, Focused PRs**: One feature per PR. Easier to review!
2. **Test Before Push**: Always run tests locally first
3. **Descriptive Commits**: Future you will thank you
4. **Keep Main Stable**: Never push directly to main
5. **Update Often**: Rebase from main frequently to avoid conflicts

## 🆘 Common Issues

### "Permission denied" when pushing

You need to authenticate with GitHub. Use:
- Personal Access Token (classic)
- SSH key
- GitHub CLI (`gh auth login`)

### Merge conflicts

```bash
# Update your branch with main
git checkout feature/my-branch
git fetch origin
git rebase origin/main

# Resolve conflicts in files
# Then:
git add .
git rebase --continue
```

### Accidentally committed to main

```bash
# Create feature branch from current state
git checkout -b feature/my-feature

# Reset main to remote
git checkout main
git reset --hard origin/main
```

---

**Remember**: Every feature should have its own branch and PR. This keeps the project history clean and makes it easy to review changes!
