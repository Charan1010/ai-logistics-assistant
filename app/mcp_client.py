"""
MCP Client for Feature 9.

Connects to configured MCP servers (currently just the local demo server)
over stdio, discovers their tools, and calls them on behalf of the agent.

Each `list_mcp_tools()` and `call_mcp_tool()` spawns a fresh subprocess for
the target server, performs the MCP handshake, and shuts it down. Slower than
in-process calls but matches the pattern used by Claude Desktop / Cursor /
Google ADK MCPToolset — the same server code works with all of them.

Tool schemas are cached after first discovery so we don't re-spawn on every
agent turn.
"""
import json
import os
import sys
from typing import Optional

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None


def _build_server_registry() -> list[dict]:
    """Return the list of MCP servers the agent knows about."""
    return [
        {
            "name": "demo",
            "command": [sys.executable, "-m", "app.mcp_demo_server"],
            "enabled": os.getenv("ENABLE_MCP", "true").lower() == "true",
            "transport": "stdio",
            "description": "Logistics demo server — rate card, customs, fuel surcharge (mock data)",
        },
    ]


SERVER_REGISTRY: list[dict] = _build_server_registry()
_tool_cache: dict[str, list[dict]] = {}


def reset_cache() -> None:
    """Clear the tool cache. Useful in tests."""
    _tool_cache.clear()


async def _list_tools_from_server(server_entry: dict) -> list[dict]:
    """Spawn the server subprocess, list its tools, and shut it down."""
    if not _MCP_AVAILABLE:
        raise ImportError("The 'mcp' package is not installed. Run: pip install mcp")

    params = StdioServerParameters(
        command=server_entry["command"][0],
        args=server_entry["command"][1:],
    )
    tools: list[dict] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema or {"type": "object", "properties": {}},
                    "server": server_entry["name"],
                })
    return tools


async def list_mcp_tools(use_cache: bool = True) -> list[dict]:
    """Return the combined list of tools from all enabled MCP servers."""
    if not _MCP_AVAILABLE:
        return []

    all_tools: list[dict] = []
    for entry in SERVER_REGISTRY:
        if not entry.get("enabled"):
            continue

        if use_cache and entry["name"] in _tool_cache:
            all_tools.extend(_tool_cache[entry["name"]])
            continue

        try:
            tools = await _list_tools_from_server(entry)
            _tool_cache[entry["name"]] = tools
            all_tools.extend(tools)
        except Exception as exc:
            print(
                f"[mcp_client] Failed to list tools from server '{entry['name']}': {exc}",
                file=sys.stderr,
            )

    return all_tools


async def _call_tool_on_server(server_entry: dict, tool_name: str, arguments: dict) -> dict:
    """Spawn the server subprocess, call one tool, and shut it down."""
    if not _MCP_AVAILABLE:
        raise ImportError("The 'mcp' package is not installed. Run: pip install mcp")

    params = StdioServerParameters(
        command=server_entry["command"][0],
        args=server_entry["command"][1:],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.content:
                raw = result.content[0].text
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, AttributeError):
                    return {"result": str(raw)}
            return {"result": None}


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Invoke a named MCP tool and return its JSON result."""
    if not _MCP_AVAILABLE:
        return {"error": "The 'mcp' package is not installed."}

    if not _tool_cache:
        await list_mcp_tools()

    owner_name: Optional[str] = None
    for server_name, tools in _tool_cache.items():
        if any(t["name"] == tool_name for t in tools):
            owner_name = server_name
            break

    if owner_name is None:
        return {"error": f"Tool '{tool_name}' not found in any connected MCP server."}

    server_entry = next((s for s in SERVER_REGISTRY if s["name"] == owner_name), None)
    if server_entry is None:
        return {"error": f"Server '{owner_name}' not found in registry."}

    try:
        return await _call_tool_on_server(server_entry, tool_name, arguments)
    except Exception as exc:
        return {"error": str(exc)}


async def get_mcp_tool_schemas() -> list[dict]:
    """Return OpenAI-format function schemas for every MCP tool."""
    tools = await list_mcp_tools()
    schemas = []
    for tool in tools:
        schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": f"[MCP:{tool['server']}] {tool['description']}",
                "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
            },
        })
    return schemas


def get_server_registry() -> list[dict]:
    """Return sanitised registry entries for the /api/mcp/servers endpoint."""
    return [
        {
            "name": entry["name"],
            "enabled": entry.get("enabled", False),
            "transport": entry.get("transport", "stdio"),
            "description": entry.get("description", ""),
        }
        for entry in SERVER_REGISTRY
    ]
