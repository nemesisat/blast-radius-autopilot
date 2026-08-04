"""Dump raw MCP tool responses so downstream scripts parse the real shape."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ORDERS = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.orders,PROD)"


def _text(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


async def main() -> int:
    server = shutil.which("mcp-server-datahub")
    token = os.getenv("DATAHUB_GMS_TOKEN") or os.getenv("DATAHUB_TOKEN", "")
    env = {**os.environ,
           "DATAHUB_GMS_URL": os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
           "DATAHUB_GMS_TOKEN": token}
    params = StdioServerParameters(command=server, args=["--transport", "stdio"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for label, tool, args in [
                ("search", "search", {"query": "*", "filter": {"entity_type": ["DATASET"]}, "num_results": 3}),
                ("get_lineage", "get_lineage", {"urn": ORDERS, "upstream": False, "max_hops": 2, "max_results": 5}),
                ("get_dataset_queries", "get_dataset_queries", {"urn": ORDERS}),
            ]:
                print(f"\n{'='*20} {label} {'='*20}")
                try:
                    res = await s.call_tool(tool, args)
                    txt = _text(res)
                    print(f"[len={len(txt)}] first 1200 chars:")
                    print(txt[:1200])
                except Exception as exc:  # noqa: BLE001
                    print("ERROR:", type(exc).__name__, exc)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
