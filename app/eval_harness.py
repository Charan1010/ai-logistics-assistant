"""
Eval harness for Feature 11 — automated quality checks against a golden set.

LLM outputs are non-deterministic — can't `assert` on them. Instead, run
(question, expected_behaviour) pairs and score each. Framework equivalent:
LangSmith evaluate() / RAGAS evaluate().

Checks:
  query_type_check  — classify_query returns the expected QueryClassification.query_type
  source_check      — routing decision (llm / rag / hybrid) matches expected (skipped if None)
  content_check     — each phrase in expected_answer_contains appears in the answer

A case PASSES when checks_failed is empty.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvalCase(BaseModel):
    id: str = Field(default="")
    question: str
    expected_query_type: Optional[str] = None  # general | domain | professional_document | ambiguous
    expected_source: Optional[str] = None       # llm | rag | hybrid — None = skip
    expected_answer_contains: list[str] = Field(default_factory=list)


class EvalResult(BaseModel):
    case_id: str
    question: str
    passed: bool
    actual_query_type: str
    actual_source: str
    actual_answer: str
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    ran_at: str
    cases: list[EvalResult] = Field(default_factory=list)


_EVAL_SYSTEM = (
    "You are an operations assistant for a logistics and supply chain company. "
    "Answer clearly and concisely in plain English."
)


async def run_eval(
    test_cases: list[EvalCase],
    classify_fn,
    search_fn,
    llm_chat_fn,
    tenant_id: Optional[str] = None,
) -> EvalReport:
    """
    Run every case through classify → route → LLM, score each.

    Takes callables rather than importing from app.main to keep this module
    free of circular imports and testable with mocks.

      classify_fn(message)              → awaits QueryClassification-like object
                                           with .query_type, .needs_retrieval, .confidence
      search_fn(message, top_k, tenant_id) → list of chunk dicts with 'text'
      llm_chat_fn(messages)             → awaits str (final answer)
    """
    results: list[EvalResult] = []

    for case in test_cases:
        case_id = case.id or str(uuid.uuid4())[:8]

        try:
            classification = await classify_fn(case.question)
            actual_query_type = classification.query_type
            needs_retrieval = classification.needs_retrieval
            confidence = classification.confidence
        except Exception as exc:
            logger.warning("eval classify failed for case %s: %s", case_id, exc)
            results.append(EvalResult(
                case_id=case_id, question=case.question, passed=False,
                actual_query_type="error", actual_source="error", actual_answer="",
                checks_failed=[f"classify_error: {exc}"],
            ))
            continue

        # Mirror smart_chat routing logic
        chunks: list[dict[str, Any]] = []
        high_confidence = confidence > 0.6
        if high_confidence and needs_retrieval:
            try:
                chunks = search_fn(case.question, top_k=3, tenant_id=tenant_id) or []
            except Exception:
                chunks = []
            actual_source = "rag"
        elif not high_confidence:
            try:
                chunks = search_fn(case.question, top_k=3, tenant_id=tenant_id) or []
            except Exception:
                chunks = []
            actual_source = "hybrid"
        else:
            actual_source = "llm"

        messages: list[dict] = [{"role": "system", "content": _EVAL_SYSTEM}]
        if chunks:
            ctx = "\n\n".join(c.get("text", "") for c in chunks[:3])
            messages.append({"role": "system", "content": f"Retrieved context:\n{ctx}"})
        messages.append({"role": "user", "content": case.question})

        try:
            actual_answer = await llm_chat_fn(messages)
        except Exception as exc:
            logger.warning("eval LLM failed for case %s: %s", case_id, exc)
            results.append(EvalResult(
                case_id=case_id, question=case.question, passed=False,
                actual_query_type=actual_query_type, actual_source=actual_source,
                actual_answer="",
                checks_failed=[f"llm_error: {exc}"],
            ))
            continue

        checks_passed: list[str] = []
        checks_failed: list[str] = []

        if case.expected_query_type and case.expected_query_type != "ambiguous":
            if actual_query_type == case.expected_query_type:
                checks_passed.append("query_type")
            else:
                checks_failed.append(f"query_type: expected={case.expected_query_type} got={actual_query_type}")

        if case.expected_source is not None:
            if actual_source == case.expected_source:
                checks_passed.append("source")
            else:
                checks_failed.append(f"source: expected={case.expected_source} got={actual_source}")

        for phrase in case.expected_answer_contains:
            if phrase.lower() in actual_answer.lower():
                checks_passed.append(f"contains:{phrase!r}")
            else:
                checks_failed.append(f"missing:{phrase!r}")

        results.append(EvalResult(
            case_id=case_id, question=case.question,
            passed=len(checks_failed) == 0,
            actual_query_type=actual_query_type,
            actual_source=actual_source,
            actual_answer=actual_answer,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        ))

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return EvalReport(
        total=total,
        passed=passed,
        failed=total - passed,
        pass_rate=round(passed / total, 4) if total else 0.0,
        ran_at=datetime.now(timezone.utc).isoformat(),
        cases=results,
    )


def load_default_cases() -> list[EvalCase]:
    """Load the shipped golden cases from tests/eval_cases_logistics.json."""
    path = Path(__file__).parent.parent / "tests" / "eval_cases_logistics.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [EvalCase(**item) for item in raw]
