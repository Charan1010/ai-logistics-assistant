"""
In-memory session store for conversation history.
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Session:
    """A conversation session with message history."""
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    messages: List[Message] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


class SessionStore:
    """In-memory store for managing conversation sessions."""

    def __init__(self, max_sessions: int = 1000, ttl_hours: int = 24):
        self._sessions: Dict[str, Session] = {}
        self.max_sessions = max_sessions
        self.ttl_hours = ttl_hours

    def create_session(self, metadata: Optional[Dict[str, str]] = None) -> Session:
        """Create a new session with a unique ID."""
        # Clean up old sessions if we're at the limit
        if len(self._sessions) >= self.max_sessions:
            self._cleanup_old_sessions()

        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            metadata=metadata or {}
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self, limit: int = 100) -> List[Session]:
        """List all active sessions, most recent first."""
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True
        )
        return sessions[:limit]

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """Add a message to a session. Returns True if successful."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        message = Message(role=role, content=content)
        session.messages.append(message)
        session.updated_at = datetime.utcnow()
        return True

    def get_history(self, session_id: str, limit: Optional[int] = None) -> List[Message]:
        """Get message history for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return []

        if limit:
            return session.messages[-limit:]
        return session.messages

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if session existed."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def _cleanup_old_sessions(self):
        """Remove sessions older than TTL."""
        cutoff = datetime.utcnow() - timedelta(hours=self.ttl_hours)
        expired = [
            sid for sid, session in self._sessions.items()
            if session.updated_at < cutoff
        ]
        for sid in expired:
            del self._sessions[sid]

    def clear_all(self):
        """Clear all sessions. Used for testing."""
        self._sessions.clear()


# Global session store instance
session_store = SessionStore()
