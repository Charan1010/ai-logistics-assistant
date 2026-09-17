"""
In-memory store for multi-step agent tasks (Feature 8).

Mirrors the session_store pattern: create → update → get, with TTL cleanup.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class AgentTask:
    """A multi-step agent task with plan, live progress, and final result."""
    task_id: str
    message: str
    status: str = "planning"  # planning | executing | done | error
    plan: List[str] = field(default_factory=list)
    steps_completed: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TaskStore:
    """In-memory store for AgentTask objects."""

    def __init__(self, max_tasks: int = 1000, ttl_hours: int = 24):
        self._tasks: Dict[str, AgentTask] = {}
        self.max_tasks = max_tasks
        self.ttl_hours = ttl_hours

    def create_task(
        self,
        message: str,
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> AgentTask:
        if len(self._tasks) >= self.max_tasks:
            self._cleanup_expired()

        task_id = str(uuid.uuid4())
        task = AgentTask(
            task_id=task_id,
            message=message,
            session_id=session_id,
            tenant_id=tenant_id,
        )
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **fields: Any) -> Optional[AgentTask]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.utcnow()
        return task

    def _cleanup_expired(self) -> None:
        cutoff = datetime.utcnow() - timedelta(hours=self.ttl_hours)
        expired = [tid for tid, t in self._tasks.items() if t.updated_at < cutoff]
        for tid in expired:
            del self._tasks[tid]


task_store = TaskStore()
