"""Probe: does the datapack ship REAL SQL (view definitions / custom SQL) for
ORDER_DETAILS' downstreams, reachable over MCP get_entities?

If yes, the impact run can use real datapack SQL instead of a seeded query log.
Read-only.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TARGET = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"


def _text(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


def _find_sql(obj, path="", hits=None):
    """Recursively locate any string field that looks like SQL."""
    if hits is None:
        hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and len(v) > 30:
                low = v.lower()
                if "select" in low and "from" in low:
                    hits.append((f"{path}.{k}", v))
            else:
                _find_sql(v, f"{path}.{k}", hits)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _find_sql(v, f"{path}[{i}]", hits)
    return hits


async def main() -> int:
    token = os.getenv("DATAHUB_GMS_TOKEN") or os.getenv("DATAHUB_TOKEN", "")
    env = {**os.environ,
           "DATAHUB_GMS_URL": os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
           "DATAHUB_GMS_TOKEN": token}
    params = StdioServerParameters(command=shutil.which("mcp-server-datahub"),
                                   args=["--transport", "stdio"], env=env)

    ranking = json.load(open(ROOT / "out" / "mcp_ranking.json"))
    top = next(r for r in ranking if r["urn"] == TARGET)
    downstream_urns = [d["urn"] for d in top["downstream_list"]]

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            print("=== get_dataset_queries on TARGET ===")
            dq = json.loads(_text(await s.call_tool("get_dataset_queries", {"urn": TARGET})))
            print(json.dumps(dq)[:300])

            print("\n=== get_entities on TARGET (looking for viewLogic) ===")
            ge = json.loads(_text(await s.call_tool("get_entities", {"urns": [TARGET]})))
            hits = _find_sql(ge)
            print(f"SQL-looking fields on target: {len(hits)}")
            for p, v in hits[:2]:
                print(f"  {p}  [{len(v)} chars]\n    {v[:300]}...")

            print(f"\n=== get_entities on {len(downstream_urns)} downstreams (batched) ===")
            found = {}
            for i in range(0, len(downstream_urns), 8):
                batch = downstream_urns[i:i + 8]
                raw = json.loads(_text(await s.call_tool("get_entities", {"urns": batch})))
                for p, v in _find_sql(raw):
                    found.setdefault(v[:80], (p, v))
            print(f"distinct SQL-looking blobs across downstreams: {len(found)}")
            for k, (p, v) in list(found.items())[:6]:
                print(f"\n  --- {p} [{len(v)} chars] ---")
                print("  " + v[:400].replace("\n", "\n  "))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
