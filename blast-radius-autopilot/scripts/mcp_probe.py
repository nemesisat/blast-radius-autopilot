"""Preflight probe: connect to mcp-server-datahub over stdio, list its tools and
their input schemas. Read-only; no writes, no core-logic imports.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    server = shutil.which("mcp-server-datahub")
    if not server:
        print("mcp-server-datahub not on PATH", file=sys.stderr)
        return 2
    token = os.getenv("DATAHUB_GMS_TOKEN") or os.getenv("DATAHUB_TOKEN", "")
    env = {
        **os.environ,
        "DATAHUB_GMS_URL": os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
        "DATAHUB_GMS_TOKEN": token,
    }
    params = StdioServerParameters(command=server, args=["--transport", "stdio"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("server:", init.serverInfo.name, init.serverInfo.version)
            tools = (await s.list_tools()).tools
            print(f"\n{len(tools)} MCP tools:\n")
            for t in tools:
                props = list((t.inputSchema or {}).get("properties", {}).keys())
                req = (t.inputSchema or {}).get("required", [])
                print(f"  - {t.name}")
                print(f"      args: {props}")
                print(f"      required: {req}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
