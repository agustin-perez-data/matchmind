"""MCP server exposing the match-state tools over streamable HTTP.

Mounted by the FastAPI app at /mcp so any MCP client (GitHub Copilot, another
Agent Framework agent, the MCP inspector) can query live match state.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from matchmind.tools.registry import LiveStateRegistry, MatchTools

INSTRUCTIONS = (
    "MatchMind match-state tools. All matches are synthetic (fictional clubs and players). "
    "Workload metrics are decision support, not medical advice. Call list_matches first to get match ids."
)


def build_mcp_server(registry: LiveStateRegistry) -> FastMCP:
    tools = MatchTools(registry)
    server = FastMCP(
        "matchmind",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",  # the FastAPI app mounts this ASGI app at "/"
        # DNS-rebinding protection only makes sense for localhost-only servers; this one
        # is a public, read-only demo endpoint served under an Azure domain.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for fn in tools.as_functions():
        server.add_tool(fn)
    return server
