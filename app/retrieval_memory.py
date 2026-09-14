"""
In-memory retrieval memory for Smart Chat.
"""
from collections import Counter
from datetime import datetime
import uuid

from app.models import KnowledgeDigest, RetrievalLogEntry


class RetrievalMemoryStore:
    """Stores retrieval events and builds lightweight knowledge digests."""

    def __init__(self):
        self._entries: list[RetrievalLogEntry] = []

    def log_retrieval(
        self,
        query: str,
        retrieved_chunks: list[str],
        retrieval_scores: list[float],
        source_used: str,
        session_id: str | None = None,
        tenant_id: str | None = None,
    ) -> RetrievalLogEntry:
        """Persist one retrieval event."""
        entry = RetrievalLogEntry(
            id=str(uuid.uuid4()),
            session_id=session_id,
            tenant_id=tenant_id,
            query=query,
            retrieved_chunks=retrieved_chunks,
            retrieval_scores=retrieval_scores,
            source_used=source_used,
            timestamp=datetime.utcnow(),
        )
        self._entries.append(entry)
        return entry

    def list_entries(self, tenant_id: str | None = None, limit: int = 100) -> list[RetrievalLogEntry]:
        """Return recent retrieval entries, newest first."""
        entries = self._entries
        if tenant_id is not None:
            entries = [entry for entry in entries if entry.tenant_id == tenant_id]
        return sorted(entries, key=lambda entry: entry.timestamp, reverse=True)[:limit]

    def set_feedback(self, entry_id: str, was_helpful: bool, tenant_id: str | None = None) -> RetrievalLogEntry | None:
        """Mark a retrieval as helpful/unhelpful."""
        for entry in self._entries:
            if entry.id == entry_id and (tenant_id is None or entry.tenant_id == tenant_id):
                entry.was_helpful = was_helpful
                return entry
        return None

    def build_digest(self, tenant_id: str | None = None) -> KnowledgeDigest:
        """Build a deterministic retrieval digest from logged events."""
        entries = self.list_entries(tenant_id=tenant_id, limit=500)
        if not entries:
            return KnowledgeDigest(
                generated_at=datetime.utcnow(),
                tenant_id=tenant_id,
                top_chunks=[],
                query_patterns=[],
                coverage_gaps=[],
                summary="No retrievals have been logged yet.",
                retrieval_count=0,
            )

        chunk_counts = Counter(chunk_id for entry in entries for chunk_id in entry.retrieved_chunks)
        low_score_queries = [
            entry.query
            for entry in entries
            if entry.retrieval_scores and max(entry.retrieval_scores) < 0.35
        ]
        unhelpful_queries = [entry.query for entry in entries if entry.was_helpful is False]
        repeated_terms = _top_query_terms([entry.query for entry in entries])

        top_chunks = [chunk_id for chunk_id, _ in chunk_counts.most_common(5)]
        query_patterns = [f"Frequent query term: {term}" for term in repeated_terms]
        coverage_gaps = [f"Low-confidence retrieval: {query}" for query in low_score_queries[:3]]
        coverage_gaps.extend(f"Marked unhelpful: {query}" for query in unhelpful_queries[:3])

        summary = (
            f"Observed {len(entries)} retrieval event(s). "
            f"Most reused chunks: {', '.join(top_chunks) if top_chunks else 'none yet'}. "
            f"Recurring query signals: {', '.join(repeated_terms) if repeated_terms else 'not enough data yet'}."
        )

        return KnowledgeDigest(
            generated_at=datetime.utcnow(),
            tenant_id=tenant_id,
            top_chunks=top_chunks,
            query_patterns=query_patterns,
            coverage_gaps=coverage_gaps,
            summary=summary,
            retrieval_count=len(entries),
        )

    def clear_all(self) -> None:
        """Clear all retrieval memory. Used for tests."""
        self._entries.clear()


def _top_query_terms(queries: list[str]) -> list[str]:
    """Return simple recurring query terms without external NLP dependencies."""
    stop_words = {
        "the", "and", "for", "with", "what", "how", "why", "when", "where",
        "does", "our", "are", "is", "to", "of", "in", "a", "an", "about",
        "uploaded", "document", "documents", "policy",
    }
    terms = []
    for query in queries:
        cleaned = "".join(char.lower() if char.isalnum() else " " for char in query)
        terms.extend(term for term in cleaned.split() if len(term) > 2 and term not in stop_words)
    return [term for term, _ in Counter(terms).most_common(5)]


retrieval_memory_store = RetrievalMemoryStore()
