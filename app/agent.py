"""
Logistics Agent for Feature 7.

Implements the two-call tool-calling loop:
  1. Send user message + tool schemas → LLM decides which tools to call
  2. Execute tools locally → send results back → LLM writes final answer

Tools are mocked/deterministic so the loop is testable without external APIs.
"""
import random
import uuid
from typing import Callable

from app.llm_client import llm_client
from app.session_store import session_store


AGENT_SYSTEM_PROMPT = """You are an operations agent for a logistics and supply chain company.

You have access to tools that can look up real shipment data, estimate delivery windows,
create support tickets, and fetch warehouse metrics. Use them whenever the user's request
would benefit from real operational data. Do not guess shipment status, delivery times,
warehouse capacity, or ticket IDs — call the appropriate tool instead.

When you call a tool, wait for its result before responding. Synthesise the tool result
into a clear, professional answer. If a tool returns an error, acknowledge it and offer
a next step. If the user asks something general that no tool covers, answer briefly from
your logistics knowledge."""


# =============================================================================
# Tool 1: Shipment status lookup
# =============================================================================

_SHIPMENT_STATUSES = ("in_transit", "delivered", "delayed", "out_for_delivery", "pending_pickup")


def check_shipment_status(tracking_number: str) -> dict:
    """Return deterministic-mock status for a shipment tracking number."""
    tracking_number = (tracking_number or "").strip().upper()
    if not tracking_number:
        return {"error": "tracking_number is required"}

    rng = random.Random(tracking_number)
    status = rng.choice(_SHIPMENT_STATUSES)
    return {
        "tracking_number": tracking_number,
        "status": status,
        "carrier": rng.choice(["FedEx Ground", "FedEx Freight", "UPS", "DHL"]),
        "last_scan_location": rng.choice(["Memphis, TN", "Chicago, IL", "Dallas, TX", "Newark, NJ"]),
        "estimated_delivery": "within 24 hours" if status == "out_for_delivery" else "in 2 business days",
    }


CHECK_SHIPMENT_STATUS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_shipment_status",
        "description": (
            "Look up the current status of a shipment by tracking number. "
            "Use this whenever the user asks about a shipment, package, tracking number, "
            "delivery status, or where a package is. Returns status, carrier, last-scan "
            "location, and an estimated delivery window."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tracking_number": {
                    "type": "string",
                    "description": "The tracking number the user provided, e.g. 'TRK-12345' or 'FDX999888'.",
                },
            },
            "required": ["tracking_number"],
        },
    },
}


# =============================================================================
# Tool 2: Delivery estimation
# =============================================================================

_LANE_ESTIMATES = {
    ("memphis", "chicago"): (1, 2),
    ("memphis", "dallas"): (1, 2),
    ("chicago", "newark"): (1, 2),
    ("newark", "dallas"): (2, 3),
}


def estimate_delivery(origin: str, destination: str, service_level: str = "ground") -> dict:
    """Return a mock delivery estimate for a lane and service level."""
    origin_key = (origin or "").strip().lower()
    destination_key = (destination or "").strip().lower()
    if not origin_key or not destination_key:
        return {"error": "origin and destination are required"}

    service_level = (service_level or "ground").lower()
    if service_level not in {"ground", "express", "priority_overnight"}:
        service_level = "ground"

    base = _LANE_ESTIMATES.get((origin_key, destination_key), (3, 5))
    if service_level == "express":
        base = (max(1, base[0] - 1), max(1, base[1] - 1))
    elif service_level == "priority_overnight":
        base = (1, 1)

    return {
        "origin": origin,
        "destination": destination,
        "service_level": service_level,
        "estimate_min_days": base[0],
        "estimate_max_days": base[1],
        "notes": "Estimates exclude weekends and customs holds.",
    }


ESTIMATE_DELIVERY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_delivery",
        "description": (
            "Estimate transit time between an origin and destination city. "
            "Use this when the user asks how long a shipment will take, delivery windows "
            "between cities, or the difference between service levels."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Origin city, e.g. 'Memphis'."},
                "destination": {"type": "string", "description": "Destination city, e.g. 'Chicago'."},
                "service_level": {
                    "type": "string",
                    "enum": ["ground", "express", "priority_overnight"],
                    "description": "Requested service level. Defaults to 'ground'.",
                },
            },
            "required": ["origin", "destination"],
        },
    },
}


# =============================================================================
# Tool 3: Support ticket creation
# =============================================================================

def create_shipping_ticket(subject: str, description: str, priority: str = "normal") -> dict:
    """Create a mock shipping-support ticket."""
    if not subject or not description:
        return {"error": "subject and description are required"}

    priority = (priority or "normal").lower()
    if priority not in {"low", "normal", "high"}:
        priority = "normal"

    response_time = {
        "low": "3-5 business days",
        "normal": "1-2 business days",
        "high": "within 4 hours",
    }[priority]

    return {
        "ticket_id": f"LOG-{uuid.uuid4().hex[:8].upper()}",
        "subject": subject,
        "priority": priority,
        "status": "open",
        "estimated_response": response_time,
    }


CREATE_SHIPPING_TICKET_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_shipping_ticket",
        "description": (
            "Open a support ticket for a shipping issue such as damaged goods, missing shipment, "
            "billing dispute, or customs hold. Use this when the user reports a problem that needs "
            "follow-up by the operations team. Returns a ticket ID and estimated response time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Short summary of the issue."},
                "description": {"type": "string", "description": "Detailed description including tracking number if available."},
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high"],
                    "description": "Urgency. Use 'high' for outages, blocking issues, or damaged/lost freight.",
                },
            },
            "required": ["subject", "description"],
        },
    },
}


# =============================================================================
# Tool 4: Warehouse metrics lookup
# =============================================================================

_WAREHOUSE_INFO = {
    "memphis": {
        "warehouse_id": "MEM-01",
        "capacity_utilization_pct": 72,
        "dock_to_stock_hours": 3.4,
        "on_time_delivery_pct": 96.2,
        "hours": "24/7",
    },
    "chicago": {
        "warehouse_id": "ORD-04",
        "capacity_utilization_pct": 84,
        "dock_to_stock_hours": 4.1,
        "on_time_delivery_pct": 94.7,
        "hours": "05:00-23:00 CT",
    },
    "dallas": {
        "warehouse_id": "DFW-02",
        "capacity_utilization_pct": 61,
        "dock_to_stock_hours": 2.8,
        "on_time_delivery_pct": 97.5,
        "hours": "24/7",
    },
    "newark": {
        "warehouse_id": "EWR-03",
        "capacity_utilization_pct": 78,
        "dock_to_stock_hours": 3.9,
        "on_time_delivery_pct": 93.1,
        "hours": "05:00-22:00 ET",
    },
}


def lookup_warehouse_info(warehouse: str) -> dict:
    """Return mock KPI snapshot for a warehouse."""
    key = (warehouse or "").strip().lower()
    if not key:
        return {"error": "warehouse is required"}

    info = _WAREHOUSE_INFO.get(key)
    if not info:
        return {"error": f"No warehouse metrics available for '{warehouse}'."}

    return {"warehouse": warehouse, **info}


LOOKUP_WAREHOUSE_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_warehouse_info",
        "description": (
            "Return current KPI snapshot for a named warehouse, including capacity utilization, "
            "dock-to-stock cycle time, on-time delivery percentage, and operating hours. Use this "
            "whenever the user asks about warehouse metrics, throughput, capacity, or facility hours."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "warehouse": {
                    "type": "string",
                    "description": "Warehouse city or code, e.g. 'Memphis', 'Chicago', 'Dallas', 'Newark'.",
                },
            },
            "required": ["warehouse"],
        },
    },
}


# =============================================================================
# Tool registry
# =============================================================================

TOOLS_REGISTRY: dict[str, tuple[Callable[..., dict], dict]] = {
    "check_shipment_status": (check_shipment_status, CHECK_SHIPMENT_STATUS_SCHEMA),
    "estimate_delivery": (estimate_delivery, ESTIMATE_DELIVERY_SCHEMA),
    "create_shipping_ticket": (create_shipping_ticket, CREATE_SHIPPING_TICKET_SCHEMA),
    "lookup_warehouse_info": (lookup_warehouse_info, LOOKUP_WAREHOUSE_INFO_SCHEMA),
}


def _tool_schemas() -> list[dict]:
    return [schema for _, schema in TOOLS_REGISTRY.values()]


def _history_from_session(session_id: str | None) -> list[dict]:
    if not session_id:
        return []
    session = session_store.get_session(session_id)
    if not session:
        return []
    return [{"role": msg.role, "content": msg.content} for msg in session.messages[-20:]]


async def run_agent(message: str, session_id: str | None = None) -> dict:
    """
    Run the two-call agent loop.

    Returns:
        {
          "result": str,
          "steps": [{"tool": str, "args": dict, "result": dict}, ...],
          "tools_used": [str, ...],
        }
    """
    history = _history_from_session(session_id)
    messages: list[dict] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": message},
    ]

    first = await llm_client.chat_with_tools(messages=messages, tools=_tool_schemas())

    steps: list[dict] = []
    tools_used: list[str] = []

    if not first.tool_calls:
        answer = first.content or ""
        return {"result": answer, "steps": steps, "tools_used": tools_used}

    # Assistant message that requested the tool calls; passed back to the model for context.
    tool_call_message = {
        "role": "assistant",
        "content": first.content or "",
        "tool_calls": [
            {
                "id": call.call_id or f"call_{index}",
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for index, call in enumerate(first.tool_calls)
        ],
    }
    messages.append(tool_call_message)

    for index, call in enumerate(first.tool_calls):
        tool_entry = TOOLS_REGISTRY.get(call.name)
        if tool_entry is None:
            tool_result = {"error": f"Unknown tool '{call.name}'"}
        else:
            fn, _ = tool_entry
            try:
                tool_result = fn(**call.arguments)
                if not isinstance(tool_result, dict):
                    tool_result = {"result": tool_result}
            except Exception as exc:
                tool_result = {"error": f"Tool execution failed: {exc}"}

        steps.append({"tool": call.name, "args": call.arguments, "result": tool_result})
        tools_used.append(call.name)

        messages.append({
            "role": "tool",
            "name": call.name,
            "tool_call_id": call.call_id or f"call_{index}",
            "content": _stringify_tool_result(tool_result),
        })

    second = await llm_client.chat_with_tools(messages=messages)
    final_answer = second.content or ""
    return {"result": final_answer, "steps": steps, "tools_used": tools_used}


def _stringify_tool_result(payload: dict) -> str:
    import json as _json
    try:
        return _json.dumps(payload, default=str)
    except Exception:
        return str(payload)
