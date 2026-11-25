"""
CER-Intent MCP server
=====================
    python -m cer_intent.mcp                          # stdio (local MCP clients)
    python -m cer_intent.mcp --transport streamable-http --host 0.0.0.0 --port 8765

Works with the MCP Python SDK 1.x (FastMCP) and 2.x (MCPServer). Once the
TeraFlowSDN fork is rebased on upstream, the same tools can be added to
TeraFlowSDN's own MCP server with ``cer_intent.mcp.tools.register(server)``.
"""
from __future__ import annotations

import argparse
from cer_intent.mcp.tools import mcp_mode, register

INSTRUCTIONS = (
    "Tools of CER-Intent, the AI-native transport slice controller for Ceragon wireless transport. "
    "preview_network_slice shows how an RFC 9543 request would be realized (L2VPN/L3VPN on TeraFlowSDN). "
    "create_network_slice, delete_network_slice and submit_intent change the network only when the server "
    "runs with CER_INTENT_MCP_MODE=act; otherwise they return a preview. run_what_if answers from the digital "
    "twin: its results are simulated."
)


def _server_class():
    try:  # MCP Python SDK 2.x
        from mcp.server.mcpserver import MCPServer
        return MCPServer, 2
    except ImportError:  # 1.x
        from mcp.server.fastmcp import FastMCP
        return FastMCP, 1


def build_server(name: str = "cer-intent", host: str = "127.0.0.1", port: int = 8765):
    server_class, major = _server_class()
    if major == 1:  # 1.x takes the HTTP address at construction
        server = server_class(name, instructions=INSTRUCTIONS, host=host, port=port)
    else:
        server = server_class(name, instructions=INSTRUCTIONS)
    register(server)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="CER-Intent MCP server")
    parser.add_argument("--transport", choices=("stdio", "streamable-http", "sse"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = build_server(host=args.host, port=args.port)
    if args.transport == "stdio":
        server.run(transport="stdio")
        return
    print(f"CER-Intent MCP server: {mcp_mode()} mode, {args.transport} on {args.host}:{args.port}", flush=True)
    if _server_class()[1] == 1:
        server.run(transport=args.transport)
    else:
        server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
