"""STEP 1 — over MCP, enumerate the datapack's datasets and rank them by DOWNSTREAM
lineage count, so the blast-radius target is discovered, not hardcoded.

Uses only MCP tools: `search` (enumerate datasets) + `get_lineage` (count downstreams).
Read-only. Writes out/mcp_ranking.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
MAX_HOPS = 2
CONCURRENCY = 6


def _text(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


def _entities(block: dict) -> list[dict]:
    """Normalise the various shapes search/get_lineage can return."""
    for key in ("searchResults", "results", "entities"):
        if isinstance(block.get(key), list):
            return block[key]
    return []


def _urn_name(row: dict) -> tuple[str, str]:
    ent = row.get("entity") or row
    props = ent.get("properties") or {}
    return ent.get("urn", ""), props.get("name") or props.get("qualifiedName") or ""


async def _lineage_count(session, urn: str, sem: asyncio.Semaphore) -> tuple[str, int, list]:
    async with sem:
        try:
            raw = json.loads(_text(await session.call_tool(
                "get_lineage",
                {"urn": urn, "upstream": False, "max_hops": MAX_HOPS, "max_results": 50},
            )))
        except Exception as exc:  # noqa: BLE001
            return urn, -1, [f"ERROR {exc}"]
    block = raw.get("downstreams", raw)
    rows = _entities(block)
    total = block.get("total")
    if not isinstance(total, int):
        total = len(rows)
    return urn, total, [_urn_name(r) for r in rows]


async def main() -> int:
    server = shutil.which("mcp-server-datahub")
    if not server:
        print("mcp-server-datahub not on PATH", file=sys.stderr)
        return 2
    token = os.getenv("DATAHUB_GMS_TOKEN") or os.getenv("DATAHUB_TOKEN", "")
    env = {**os.environ,
           "DATAHUB_GMS_URL": os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
           "DATAHUB_GMS_TOKEN": token}
    params = StdioServerParameters(command=server, args=["--transport", "stdio"], env=env)

    t0 = time.perf_counter()
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # search caps num_results at 50 -> paginate via offset
            rows, offset, total = [], 0, None
            while True:
                page = json.loads(_text(await s.call_tool(
                    "search",
                    {"query": "*", "filter": "entity_type = dataset",
                     "num_results": 50, "offset": offset},
                )))
                if total is None:
                    total = page.get("total")
                got = _entities(page)
                rows.extend(got)
                offset += len(got)
                if not got or (isinstance(total, int) and offset >= total):
                    break
            print(f"MCP search -> total={total} returned={len(rows)}")
            datasets = [(u, n) for (u, n) in (_urn_name(x) for x in rows) if u]
            print(f"datasets to rank: {len(datasets)}")

            sem = asyncio.Semaphore(CONCURRENCY)
            results = await asyncio.gather(
                *[_lineage_count(s, u, sem) for (u, _n) in datasets]
            )
    elapsed = time.perf_counter() - t0

    names = dict(datasets)
    ranked = sorted(results, key=lambda t: t[1], reverse=True)
    print(f"\nranked {len(ranked)} datasets in {elapsed:.1f}s (MCP get_lineage x{len(ranked)})\n")
    print(f"{'#downstream':>11}  name")
    for urn, total, _d in ranked[:15]:
        print(f"{total:>11}  {names.get(urn) or urn.split(',')[-2]}")

    payload = [{"urn": u, "name": names.get(u, ""), "downstreams": t,
                "downstream_list": [{"urn": du, "name": dn} for (du, dn) in d if isinstance(d, tuple) or True]
                if all(isinstance(x, tuple) for x in d) else d}
               for (u, t, d) in ranked]
    out = ROOT / "out" / "mcp_ranking.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print("\nwrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
