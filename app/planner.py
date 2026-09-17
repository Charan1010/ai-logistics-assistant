"""
Multi-step planner for Feature 8.

Plan-and-Execute pattern:
  1. make_plan()      → LLM decomposes the request into 2–5 concrete steps
  2. execute_plan()   → runs each step through the Feature 7 agent, then
                        asks the LLM to synthesise a final answer

execute_plan() runs as a FastAPI BackgroundTask and updates task_store after
each step so the /api/agent/status endpoint shows live progress.
"""
import json
from typing import Any

from app.agent import run_agent
from app.llm_client import llm_client
from app.session_store import session_store
from app.task_store import task_store


PLANNER_SYSTEM_PROMPT = """You are a task planner for a logistics operations agent.

Break the user's request into 2 to 5 concrete, actionable steps that an AI agent
with these tools can execute in sequence:

- check_shipment_status(tracking_number)
- estimate_delivery(origin, destination, service_level)
- create_shipping_ticket(subject, description, priority)
- lookup_warehouse_info(warehouse)

Each step must be:
- Self-contained and specific (one clear objective)
- Executable by an agent that can call ONE of the tools above
- Written as a plain-English instruction, not a function call

Respond ONLY with a JSON object of the shape:
{"steps": ["Step 1 instruction...", "Step 2 instruction...", ...]}

No preamble, no markdown, no explanation."""


SYNTHESIZER_SYSTEM_PROMPT = """You are a logistics operations agent finishing a multi-step task.

You will be given the user's original request and the results of each step you
already executed. Write a clear, professional summary that:
- Directly answers the original request
- Weaves together key facts from every step's result
- Reads as one natural response, not a step-by-step recap
- Mentions ticket IDs, tracking numbers, and KPIs verbatim when they appear
"""


async def make_plan(message: str) -> list[str]:
    """Ask the LLM to decompose `message` into a list of step instructions."""
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    raw = await llm_client.chat_json(messages, temperature=0.3)

    try:
        parsed: Any = json.loads(raw or "{}")
    except Exception:
        return [message]

    # Model may return a bare list or wrap it under a key.
    if isinstance(parsed, dict):
        for key in ("steps", "plan", "tasks"):
            candidate = parsed.get(key)
            if isinstance(candidate, list):
                parsed = candidate
                break
        else:
            return [message]

    if not isinstance(parsed, list) or not parsed:
        return [message]

    return [str(step).strip() for step in parsed[:5] if str(step).strip()]


async def execute_plan(task_id: str) -> None:
    """
    Run every step in the task's plan through the Feature 7 agent, then
    ask the LLM to synthesise a final answer. Updates task_store after each step.
    """
    task = task_store.get_task(task_id)
    if task is None:
        return

    try:
        task_store.update_task(task_id, status="executing", steps_completed=[])
        steps_completed: list[dict] = []

        for index, step in enumerate(task.plan or []):
            step_output = await run_agent(step, session_id=task.session_id)
            step_record = {
                "step_index": index,
                "step": step,
                "result": step_output.get("result", "") or "",
                "tools_used": step_output.get("tools_used", []) or [],
            }
            steps_completed.append(step_record)
            task_store.update_task(task_id, steps_completed=list(steps_completed))

        step_summary = "\n".join(
            f"Step {rec['step_index'] + 1} ({rec['step']}): {rec['result']}"
            for rec in steps_completed
        )
        synth_messages = [
            {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Original request: {task.message}\n\n"
                    f"Step results:\n{step_summary}"
                ),
            },
        ]
        final_answer = await llm_client.chat(synth_messages)

        task_store.update_task(task_id, status="done", result=final_answer)

        if task.session_id:
            session_store.add_message(task.session_id, "user", task.message)
            session_store.add_message(task.session_id, "assistant", final_answer)

    except Exception as exc:
        task_store.update_task(task_id, status="error", error=str(exc))
