"""
MCP Demo Server for Feature 9: MCP Integration.

Exposes 3 logistics-domain tools over stdio using the official Python MCP SDK.

Deliberately chosen to complement — not duplicate — the built-in tools in
app/agent.py:
  get_carrier_rate_card   → per-lb pricing tiers by carrier
  check_customs_status    → customs hold / cleared state for a shipment
  get_fuel_surcharge      → current fuel surcharge % by region

Run standalone:
    python -m app.mcp_demo_server

The client (app/mcp_client.py) launches this as a subprocess and talks to it
via stdin/stdout. The same server would work with Claude Desktop, Cursor, or
Google ADK's MCPToolset without modification — that's the point of MCP.
"""
import asyncio
import json
import random
from datetime import datetime, timezone

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types as mcp_types
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


# =============================================================================
# Tool implementations — deterministic mocks (seed = arg values)
# =============================================================================

_CARRIERS = {
    "fedex": {"base_per_kg_usd": 4.50, "fuel_surcharge_pct": 8.5},
    "ups": {"base_per_kg_usd": 4.25, "fuel_surcharge_pct": 9.0},
    "dhl": {"base_per_kg_usd": 5.10, "fuel_surcharge_pct": 7.8},
    "usps": {"base_per_kg_usd": 3.75, "fuel_surcharge_pct": 6.5},
}


def _get_carrier_rate_card(carrier: str, weight_kg: float) -> dict:
    key = (carrier or "").strip().lower()
    if key not in _CARRIERS:
        return {"error": f"Unknown carrier '{carrier}'. Known: {sorted(_CARRIERS)}"}

    try:
        weight = float(weight_kg)
    except (TypeError, ValueError):
        return {"error": "weight_kg must be numeric"}

    info = _CARRIERS[key]
    base_cost = round(info["base_per_kg_usd"] * weight, 2)
    fuel = round(base_cost * info["fuel_surcharge_pct"] / 100.0, 2)
    total = round(base_cost + fuel, 2)

    return {
        "carrier": key,
        "weight_kg": weight,
        "base_cost_usd": base_cost,
        "fuel_surcharge_usd": fuel,
        "total_cost_usd": total,
        "rate_per_kg_usd": info["base_per_kg_usd"],
        "source": "mock — replace with carrier API in production",
    }


_CUSTOMS_STATES = ("cleared", "in_review", "hold_documentation", "hold_inspection", "released")


def _check_customs_status(tracking_number: str) -> dict:
    tn = (tracking_number or "").strip().upper()
    if not tn:
        return {"error": "tracking_number is required"}

    rng = random.Random(f"customs-{tn}")
    state = rng.choice(_CUSTOMS_STATES)
    return {
        "tracking_number": tn,
        "customs_state": state,
        "port_of_entry": rng.choice(["Los Angeles, CA", "Newark, NJ", "Miami, FL", "Seattle, WA"]),
        "duties_owed_usd": round(rng.uniform(0, 350), 2) if state != "cleared" else 0.0,
        "notes": {
            "cleared": "Package released for onward transit.",
            "in_review": "Documentation under review. No action required.",
            "hold_documentation": "Missing or incomplete commercial invoice.",
            "hold_inspection": "Random inspection selected. Expect 24-48h delay.",
            "released": "Cleared and handed off to domestic carrier.",
        }[state],
        "source": "mock — replace with CBP / customs broker API in production",
    }


_FUEL_SURCHARGE_BY_REGION = {
    "northeast": 8.2,
    "midwest": 7.6,
    "southeast": 7.9,
    "southwest": 8.4,
    "west": 8.7,
    "international": 12.5,
}


def _get_fuel_surcharge(region: str) -> dict:
    key = (region or "").strip().lower()
    pct = _FUEL_SURCHARGE_BY_REGION.get(key)
    if pct is None:
        return {
            "error": f"Unknown region '{region}'. Known: {sorted(_FUEL_SURCHARGE_BY_REGION)}",
        }

    return {
        "region": key,
        "fuel_surcharge_pct": pct,
        "effective_date": datetime.now(timezone.utc).date().isoformat(),
        "notes": "Applied on top of base freight cost.",
        "source": "mock — replace with carrier fuel-surcharge table in production",
    }


# =============================================================================
# MCP server definition
# =============================================================================

if _MCP_AVAILABLE:
    server = Server("ai-logistics-mcp-demo")

    @server.list_tools()
    async def list_tools() -> list["mcp_types.Tool"]:
        return [
            mcp_types.Tool(
                name="get_carrier_rate_card",
                description=(
                    "Return a pricing quote for a carrier and shipment weight. "
                    "Use this when the user asks how much shipping will cost, "
                    "compares carriers, or needs a rate quote."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "carrier": {"type": "string", "description": "Carrier name: fedex, ups, dhl, usps"},
                        "weight_kg": {"type": "number", "description": "Shipment weight in kilograms"},
                    },
                    "required": ["carrier", "weight_kg"],
                },
            ),
            mcp_types.Tool(
                name="check_customs_status",
                description=(
                    "Return the customs clearance state for an international shipment "
                    "by tracking number. Use this whenever the user asks about customs, "
                    "border holds, duties, or clearance for a shipment."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tracking_number": {"type": "string", "description": "Shipment tracking number"},
                    },
                    "required": ["tracking_number"],
                },
            ),
            mcp_types.Tool(
                name="get_fuel_surcharge",
                description=(
                    "Return the current fuel surcharge percentage for a US shipping region. "
                    "Use this when the user asks about fuel costs, surcharges, or freight "
                    "pricing adjustments."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "description": "US region: northeast, midwest, southeast, southwest, west, international",
                        },
                    },
                    "required": ["region"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list["mcp_types.TextContent"]:
        if name == "get_carrier_rate_card":
            result = _get_carrier_rate_card(arguments.get("carrier", ""), arguments.get("weight_kg", 0))
        elif name == "check_customs_status":
            result = _check_customs_status(arguments.get("tracking_number", ""))
        elif name == "get_fuel_surcharge":
            result = _get_fuel_surcharge(arguments.get("region", ""))
        else:
            result = {"error": f"Unknown tool '{name}'"}
        return [mcp_types.TextContent(type="text", text=json.dumps(result, indent=2))]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

else:
    async def main():
        raise RuntimeError("The 'mcp' package is not installed. Run: pip install mcp")


if __name__ == "__main__":
    asyncio.run(main())
