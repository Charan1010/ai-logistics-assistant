"""
CI eval quality gate for Feature 12: Ship It.

Loads the golden logistics eval set, runs it through the real
classify -> route -> LLM pipeline, and exits non-zero if the pass rate
falls below PASS_RATE_THRESHOLD. Run after smoke tests in CI.

    python tests/run_eval_ci.py

Requires a reachable LLM provider. In GitHub Actions this is gated on
GROQ_API_KEY being set (Ollama is not available on CI runners):

    LLM_PROVIDER=groq
    GROQ_API_KEY=<repo secret>
    GROQ_MODEL=llama-3.1-8b-instant
"""
import asyncio
import sys
from pathlib import Path

# Make the repo root importable so `app` resolves when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS_RATE_THRESHOLD = 0.7


async def main() -> int:
    from app.eval_harness import load_default_cases, run_eval
    from app.main import classify_query
    from app.llm_client import llm_client
    from app.vector_store import get_vector_store

    cases = load_default_cases()
    if not cases:
        print("[eval-ci] ERROR: no eval cases found (expected tests/eval_cases_logistics.json)", flush=True)
        return 1

    vector_store = get_vector_store()

    def _search(query: str, top_k: int, tenant_id):
        try:
            return vector_store.search(query, top_k=top_k, tenant_id=tenant_id) or []
        except Exception:
            return []

    print(f"[eval-ci] Running {len(cases)} eval cases ...", flush=True)
    report = await run_eval(
        test_cases=cases,
        classify_fn=classify_query,
        search_fn=_search,
        llm_chat_fn=llm_client.chat,
        tenant_id=None,
    )

    print(f"[eval-ci] Results: {report.passed}/{report.total} passed "
          f"(pass_rate={report.pass_rate:.2f})", flush=True)
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        print(f"  [{status}] {case.case_id}", flush=True)
        for reason in case.checks_failed:
            print(f"         - {reason}", flush=True)

    if report.pass_rate < PASS_RATE_THRESHOLD:
        print(f"\n[eval-ci] FAILED — pass rate {report.pass_rate:.2f} "
              f"is below threshold {PASS_RATE_THRESHOLD:.2f}", flush=True)
        return 1

    print(f"\n[eval-ci] PASSED — pass rate {report.pass_rate:.2f} "
          f"meets threshold {PASS_RATE_THRESHOLD:.2f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
