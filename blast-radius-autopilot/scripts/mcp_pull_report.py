"""Pull the flagship asset's schema + downstream lineage from DataHub **over the MCP
server** (mcp-server-datahub), then build the Blast Radius HTML report from that
MCP-sourced data. Reads go through MCP, not GraphQL. No core-logic changes.

Prereqs:
  pip install mcp-server-datahub            # the official DataHub MCP server
  export DATAHUB_GMS_URL=http://localhost:8080
  export DATAHUB_GMS_TOKEN=<token>          # (or DATAHUB_TOKEN; see .env)

Run:
  python scripts/mcp_pull_report.py         # -> out/mcp_report.html

MCP calls made: list_schema_fields, get_lineage, get_dataset_queries. Because the
datapack ships no query history (get_dataset_queries returns 0), the impact math uses
the seeded query log against the REAL columns (documented fallback). Public/synthetic
sample data only.
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

from autopilot.impact import compute_impact
from autopilot.report_html import render_html
from autopilot.schema import Asset, Catalog, ChangeSpec, Dataset, Query

ROOT = Path(__file__).resolve().parents[1]
ORDERS = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.orders,PROD)"
# seeded query_id -> (substring identifying the MCP-discovered downstream URN, asset type)
LINK = {
    "q_order_details": ("snowflake,b2fd91.order_entry_db.analytics.order_details,", "snowflake_table"),
    "q_customer_analytics": ("Customer_Analytics_Measures", "powerbi_report"),
    "q_essential_kpi": ("Essential_KPI_Measures", "powerbi_report"),
    "q_geographic": ("Geographic_Measures", "powerbi_report"),
    "q_time_intelligence": ("Time_Inteligence_Measures", "powerbi_report"),
}


def _text(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


async def _pull():
    server = shutil.which("mcp-server-datahub")
    if not server:
        print("mcp-server-datahub not on PATH — `pip install mcp-server-datahub`", file=sys.stderr)
        raise SystemExit(2)
    token = os.getenv("DATAHUB_GMS_TOKEN") or os.getenv("DATAHUB_TOKEN", "")
    env = {**os.environ, "DATAHUB_GMS_URL": os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
           "DATAHUB_GMS_TOKEN": token}
    params = StdioServerParameters(command=server, args=["--transport", "stdio"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            print("MCP tools:", tools)
            sf = json.loads(_text(await s.call_tool("list_schema_fields", {"urn": ORDERS})))
            ln = json.loads(_text(await s.call_tool("get_lineage", {"urn": ORDERS, "upstream": False, "max_hops": 2, "max_results": 40})))
            dq = json.loads(_text(await s.call_tool("get_dataset_queries", {"urn": ORDERS})))
    return sf, ln, dq


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:  # noqa: BLE001
        pass
    sf, ln, dq = asyncio.run(_pull())

    schema = {f["fieldPath"]: f.get("nativeDataType", "") for f in sf["fields"]}
    print(f"MCP list_schema_fields -> {len(schema)} columns")
    block = ln.get("downstreams", ln)
    results = block.get("searchResults") or block.get("results") or []
    down = [((r.get("entity") or r).get("urn", ""), ((r.get("entity") or r).get("properties") or {}).get("name", "")) for r in results]
    print(f"MCP get_lineage -> {block.get('total')} downstreams")
    print(f"MCP get_dataset_queries -> total={dq.get('total')} (empty -> seeded query log)")

    target = Dataset(urn=ORDERS, name="orders", sql_name="order_entry.orders", platform="snowflake", schema=schema)
    assets = []
    for qid, (key, typ) in LINK.items():
        match = next((u for (u, _n) in down if key in u), None)
        if match:
            assets.append(Asset(urn=match, name=match.split(",")[-2].split(".")[-1], type=typ,
                                platform=typ.split("_")[0], defining_query_id=qid))
    qlog = json.load(open(ROOT / "examples/showcase-ecommerce-live/query_log.json"))
    queries = [Query(query_id=q["query_id"], sql=q["sql"], platform=q.get("platform", "unknown"),
                     team=q.get("team"), runs=int(q.get("runs", 1))) for q in qlog]
    catalog = Catalog(name="showcase-ecommerce (real datapack, via MCP)", datasets=[target],
                      queries=queries, assets=assets, sql_dialect="snowflake")
    report = compute_impact(catalog, ChangeSpec.parse("order_entry.orders", "promotion_id", "drop"))
    print("IMPACT:", report.counts(), "risk", report.risk()["level"])
    out = ROOT / "out" / "mcp_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(report))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
