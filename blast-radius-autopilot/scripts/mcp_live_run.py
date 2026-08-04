"""STEPS 2+3 — run Blast Radius Autopilot end-to-end THROUGH the DataHub MCP server.

Everything about the target and its consumers is pulled over MCP at runtime:

    get_entities         -> target identity (name, platform, qualifiedName)
    list_schema_fields   -> real columns
    get_lineage          -> real downstream consumers
    get_dataset_queries  -> real query history (datapack ships none -> see PROVENANCE)
    get_entities(down)   -> each downstream's REAL SQL (viewProperties.logic)

The impact core (`autopilot.impact`) and the HTML renderer are imported unchanged.

PROVENANCE is tracked and printed explicitly: every query fed to the impact core is
labelled `mcp:view_logic` (real SQL shipped by the datapack, read over MCP) or
`seeded:query_log` (the documented fallback). Nothing is implied to be real that is not.

Usage:
    python scripts/mcp_live_run.py                       # top-ranked target, auto column
    python scripts/mcp_live_run.py --target-urn URN --column order_total
    python scripts/mcp_live_run.py --slug addresses      # names the output files
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from autopilot.impact import compute_impact
from autopilot.report_html import render_html
from autopilot.run import _report_json
from autopilot.schema import Asset, Catalog, ChangeSpec, Dataset, Query

ROOT = Path(__file__).resolve().parents[1]

PLATFORM_TYPE = {
    "dbt": "dbt_model",
    "tableau": "tableau_workbook",
    "powerbi": "powerbi_report",
    "looker": "looker_dashboard",
    "snowflake": "snowflake_table",
}


def _text(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


def _entities(block: dict) -> list[dict]:
    for key in ("searchResults", "results", "entities"):
        if isinstance(block.get(key), list):
            return block[key]
    return []


def _platform_of(urn: str) -> str:
    return urn.split("dataPlatform:")[1].split(",")[0] if "dataPlatform:" in urn else "unknown"


def _sql_name_from_urn(urn: str) -> str:
    """`urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.db.schema.tbl,PROD)`
    -> `db.schema.tbl` (the datapack prefixes a workspace id we must drop)."""
    try:
        path = urn.split(",")[1]
    except IndexError:
        return urn
    parts = path.split(".")
    return ".".join(parts[-3:]) if len(parts) > 3 else path


def _collect_view_logic(entity: dict) -> str | None:
    vp = entity.get("viewProperties") or {}
    logic = vp.get("logic") or vp.get("viewLogic")
    if isinstance(logic, str) and "select" in logic.lower():
        return logic
    return None


async def pull_over_mcp(target_urn: str, max_hops: int) -> dict:
    """Every read in here goes through the MCP server. Returns raw MCP payloads."""
    server = shutil.which("mcp-server-datahub")
    if not server:
        raise SystemExit("mcp-server-datahub not on PATH — pip install mcp-server-datahub")
    token = os.getenv("DATAHUB_GMS_TOKEN") or os.getenv("DATAHUB_TOKEN", "")
    env = {**os.environ,
           "DATAHUB_GMS_URL": os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
           "DATAHUB_GMS_TOKEN": token}
    params = StdioServerParameters(command=server, args=["--transport", "stdio"], env=env)

    calls: list[str] = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            ge = json.loads(_text(await s.call_tool("get_entities", {"urns": [target_urn]})))
            calls.append(f"get_entities(urns=[target]) -> {len(ge) if isinstance(ge, list) else 1} entity")

            sf = json.loads(_text(await s.call_tool("list_schema_fields", {"urn": target_urn, "limit": 500})))
            calls.append(f"list_schema_fields(urn=target) -> {len(sf.get('fields', []))} fields")

            ln = json.loads(_text(await s.call_tool(
                "get_lineage", {"urn": target_urn, "upstream": False,
                                "max_hops": max_hops, "max_results": 50})))
            block = ln.get("downstreams", ln)
            rows = _entities(block)
            calls.append(f"get_lineage(urn=target, upstream=False, max_hops={max_hops}) -> total={block.get('total')}")

            dq = json.loads(_text(await s.call_tool("get_dataset_queries", {"urn": target_urn})))
            calls.append(f"get_dataset_queries(urn=target) -> total={dq.get('total')}")

            down_urns = [((x.get("entity") or x).get("urn", "")) for x in rows]
            down_urns = [u for u in down_urns if u]
            down_entities: list[dict] = []
            for i in range(0, len(down_urns), 8):
                batch = down_urns[i:i + 8]
                raw = json.loads(_text(await s.call_tool("get_entities", {"urns": batch})))
                down_entities.extend(raw if isinstance(raw, list) else [raw])
            calls.append(f"get_entities(urns=[{len(down_urns)} downstreams]) -> {len(down_entities)} entities")

    return {"target_entity": ge, "schema_fields": sf, "lineage": ln,
            "dataset_queries": dq, "downstream_entities": down_entities,
            "downstream_urns": down_urns, "calls": calls}


def build_catalog(pulled: dict, target_urn: str) -> tuple[Catalog, list[dict], dict]:
    """Turn MCP payloads into the universal Catalog primitives. No core changes."""
    ge = pulled["target_entity"]
    tgt_ent = (ge[0] if isinstance(ge, list) and ge else ge) or {}
    props = tgt_ent.get("properties") or {}
    schema = {f["fieldPath"]: f.get("nativeDataType", "") for f in pulled["schema_fields"].get("fields", [])}
    sql_name = props.get("qualifiedName") or _sql_name_from_urn(target_urn)
    if sql_name.count(".") > 2:
        sql_name = ".".join(sql_name.split(".")[-3:])
    name = props.get("name") or sql_name.split(".")[-1]

    target = Dataset(urn=target_urn, name=name, sql_name=sql_name,
                     platform=_platform_of(target_urn), schema=schema)

    queries: list[Query] = []
    assets: list[Asset] = []
    provenance: list[dict] = []
    no_definition: list[dict] = []
    for ent in pulled["downstream_entities"]:
        urn = ent.get("urn", "")
        if not urn:
            continue
        p = _platform_of(urn)
        eprops = ent.get("properties") or {}
        dname = eprops.get("name") or urn.split(",")[-2].split(".")[-1]
        atype = PLATFORM_TYPE.get(p, f"{p}_asset")
        logic = _collect_view_logic(ent)
        if not logic:
            # A real downstream consumer that exposes NO SQL over MCP (PowerBI measures,
            # Looker views, dashboards). Registered with no defining query so the impact
            # core reports it UNKNOWN rather than omitting it — leaving it out would make
            # coverage look complete when it is not.
            assets.append(Asset(urn=urn, name=dname, type=atype, platform=p,
                                defining_query_id=None))
            no_definition.append({"asset": dname, "asset_urn": urn, "platform": p,
                                  "source": "mcp:no_sql_definition"})
            continue
        qid = f"mcp_{re.sub(r'[^a-z0-9]+', '_', dname.lower()).strip('_')}_{len(queries)}"
        queries.append(Query(query_id=qid, sql=logic, platform=p, team=None, runs=1))
        assets.append(Asset(urn=urn, name=dname, type=atype, platform=p, defining_query_id=qid))
        provenance.append({"query_id": qid, "source": "mcp:view_logic", "asset": dname,
                           "asset_urn": urn, "platform": p, "sql_chars": len(logic)})

    catalog = Catalog(name=f"showcase-ecommerce (real datapack, read over MCP) — {name}",
                      datasets=[target], queries=queries, assets=assets,
                      sql_dialect="snowflake")
    meta_extra = {"no_definition": no_definition}
    meta = {"columns": len(schema), "downstreams_total": (pulled["lineage"].get("downstreams", pulled["lineage"]) or {}).get("total"),
            "downstreams_returned": len(pulled["downstream_urns"]),
            "mcp_query_history_total": pulled["dataset_queries"].get("total"),
            "sql_name": sql_name, "target_name": name,
            "no_definition_count": len(no_definition), **meta_extra}
    return catalog, provenance, meta


def pick_column(catalog: Catalog, target: Dataset) -> tuple[str, list[tuple[str, int]]]:
    """Most-referenced real column across the MCP-sourced SQL — discovered, not hardcoded."""
    scores: list[tuple[str, int]] = []
    for col in target.schema:
        pat = re.compile(rf"\b{re.escape(col.lower())}\b")
        n = sum(len(pat.findall(q.sql.lower())) for q in catalog.queries)
        if n:
            scores.append((col, n))
    scores.sort(key=lambda t: (-t[1], t[0]))
    return (scores[0][0] if scores else ""), scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-urn", default=None, help="defaults to top of out/mcp_ranking.json")
    ap.add_argument("--column", default=None, help="defaults to the most-referenced real column")
    ap.add_argument("--op", default="drop", choices=["drop", "rename"])
    ap.add_argument("--new-name", default=None)
    ap.add_argument("--max-hops", type=int, default=2)
    ap.add_argument("--slug", default="mcp_live", help="output basename: out/<slug>_report.{html,json}")
    ap.add_argument("--verify", action="store_true",
                    help="B16: materialise the MCP-read SQL definitions to an inspectable tree, "
                         "generate mechanical fixes, and statically verify them. Nothing is executed.")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:  # noqa: BLE001
        pass

    target_urn = args.target_urn
    if not target_urn:
        ranking = json.load(open(ROOT / "out" / "mcp_ranking.json"))
        target_urn = ranking[0]["urn"]
        print(f"target auto-selected from MCP ranking: {ranking[0]['name']} "
              f"({ranking[0]['downstreams']} downstreams)")

    print(f"\nTARGET  {target_urn}")

    # ---- timed: MCP pull -------------------------------------------------
    t_pull0 = time.perf_counter()
    pulled = asyncio.run(pull_over_mcp(target_urn, args.max_hops))
    t_pull = time.perf_counter() - t_pull0

    print("\nMCP calls:")
    for c in pulled["calls"]:
        print("   ", c)

    catalog, provenance, meta = build_catalog(pulled, target_urn)
    target = catalog.datasets[0]

    print(f"\nCOUNTS  columns={meta['columns']}  downstreams={meta['downstreams_total']}"
          f"  mcp_query_history={meta['mcp_query_history_total']}")
    print(f"        sql_name={meta['sql_name']}")

    # ---- provenance ------------------------------------------------------
    if meta["mcp_query_history_total"] in (0, None):
        print(f"\nPROVENANCE  get_dataset_queries returned "
              f"{meta['mcp_query_history_total']} — the datapack ships NO query history.")
    if not catalog.queries:
        print("PROVENANCE  no downstream carried viewProperties.logic either — "
              "no SQL corpus available for this target. STOPPING.")
        return 3
    print(f"PROVENANCE  impact corpus = {len(catalog.queries)} REAL SQL definitions read over MCP "
          f"from downstream viewProperties.logic (source=mcp:view_logic).")
    print("            No seeded/synthetic SQL used in this run.")
    for p in provenance:
        print(f"              [{p['platform']:9}] {p['asset']:34} {p['sql_chars']:>5} chars  ({p['source']})")
    if meta["no_definition_count"]:
        print(f"PROVENANCE  {meta['no_definition_count']} downstream consumer(s) expose NO SQL over MCP "
              f"and are reported UNASSESSED (UNKNOWN), not safe:")
        for nd in meta["no_definition"][:30]:
            print(f"              [{nd['platform']:9}] {nd['asset']:34} ({nd['source']})")

    # ---- column choice ---------------------------------------------------
    column, scores = pick_column(catalog, target)
    if args.column:
        column = args.column
    if not column:
        print("\nno target column is referenced by any MCP-sourced SQL. STOPPING.")
        return 4
    print(f"\nCOLUMN  '{column}' — references across MCP-sourced SQL: "
          f"{dict(scores[:8])}")

    # ---- timed: sqlglot parse + impact -----------------------------------
    change = ChangeSpec.parse(target.sql_name, column, args.op, args.new_name)
    t_parse0 = time.perf_counter()
    report = compute_impact(catalog, change)
    t_parse = time.perf_counter() - t_parse0

    counts = report.counts()
    risk = report.risk()
    cov = report.coverage()
    print(f"\nIMPACT  {change.describe()}")
    print(f"        {counts}")
    print(f"        risk={risk['level_qualifier']} ({risk['score']}/100)  "
          f"coverage={cov['line']}  review_required={report.review_required()}")
    for v in sorted(report.verdicts, key=lambda v: v.verdict.value):
        print(f"          {v.verdict.value:9} {v.asset_name or v.query_id:34} "
              f"usage={v.usage:6} conf={v.confidence} {','.join(v.clauses)}")
    if report.notes:
        print("        notes:")
        for n in report.notes:
            print("          -", n)

    print(f"\nTIMING  mcp_pull={t_pull:.2f}s  sqlglot_parse+impact={t_parse:.3f}s  "
          f"total={t_pull + t_parse:.2f}s")
    print(f"        (metadata-bound: {meta['columns']} columns + {len(catalog.queries)} SQL defs, "
          f"no table data scanned)")

    # ---- emit ------------------------------------------------------------
    outdir = ROOT / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    html_path = outdir / f"{args.slug}_report.html"
    json_path = outdir / f"{args.slug}_report.json"
    html_path.write_text(render_html(report))
    payload = _report_json(report, [])
    payload["provenance"] = {
        "read_path": "mcp-server-datahub 0.6.0 over stdio",
        "mcp_calls": pulled["calls"],
        "mcp_query_history_total": meta["mcp_query_history_total"],
        "sql_corpus": provenance,
        "seeded_queries_used": 0,
        "no_sql_definition": meta["no_definition"],
        "downstreams_discovered": meta["downstreams_total"],
        "downstreams_with_analysable_sql": len(provenance),
        "downstreams_without_sql_definition": meta["no_definition_count"],
        "timing_seconds": {"mcp_pull": round(t_pull, 3),
                           "sqlglot_parse_and_impact": round(t_parse, 4),
                           "total": round(t_pull + t_parse, 3)},
        "column_reference_scores": scores,
    }
    # ---- B16: static verification over the MCP-read SQL ------------------
    verification = None
    if args.verify:
        from autopilot.fixgen import generate_fixes
        from autopilot.verify import render_verification_md, verification_json, verify_migration

        # The datapack's consumers live in DataHub as view definitions, not as files in a
        # checked-out dbt project. To exercise the patch/verify path we MATERIALISE each
        # MCP-read `viewProperties.logic` to a file tree. Stated plainly: this tree is
        # synthesised from metadata read over MCP — it is NOT a real dbt repository, and
        # a real deployment would patch the actual project.
        matdir = outdir / f"{args.slug}_materialized"
        if matdir.exists():
            shutil.rmtree(matdir)
        (matdir / "models").mkdir(parents=True, exist_ok=True)
        for a in catalog.assets:
            if not a.defining_query_id:
                continue
            q = next((q for q in catalog.queries if q.query_id == a.defining_query_id), None)
            if q is None:
                continue
            rel = f"models/{a.defining_query_id}.sql"
            (matdir / rel).write_text(q.sql if q.sql.endswith("\n") else q.sql + "\n")
            a.dbt_path = rel          # lets fixgen + the verifier find the file
        print(f"\nB16  materialised {len(list((matdir / 'models').glob('*.sql')))} MCP-read SQL "
              f"definition(s) -> {matdir}")
        print("     (synthesised from MCP metadata for verification; NOT a real dbt repo)")

        fixes = generate_fixes(catalog, change, report, matdir)
        applicable = [fx for fx in fixes if fx.diff]
        print(f"B16  generated {len(applicable)} mechanical fix(es)")
        combined = "".join(fx.diff for fx in applicable)
        verification = verify_migration(
            change, report, combined, matdir, catalog=catalog,
            expected_files=[fx.path for fx in applicable if fx.path] or None,
        )
        vd = verification.deltas()
        print(f"B16  VERDICT {verification.status}")
        print(f"     breaks {verification.before.get('breaks', 0)} -> "
              f"{verification.after.get('breaks', 0)} ({vd.get('breaks', 0):+d})  "
              f"degrades {verification.before.get('degrades', 0)} -> "
              f"{verification.after.get('degrades', 0)}  "
              f"unassessed {verification.before.get('unknown', 0)} -> "
              f"{verification.after.get('unknown', 0)}  "
              f"ambiguous {verification.before.get('ambiguous', 0)} -> "
              f"{verification.after.get('ambiguous', 0)}  "
              f"coverage {verification.coverage_after.get('line')}")
        for t in verification.transitions:
            print(f"       {t.describe()}")
        # B17.3 — coverage of the DIFF, printed explicitly.
        print(f"     patched files recomputed: {len(verification.file_query_map)} of "
              f"{len(verification.files_patched)}")
        for u in verification.unmapped_files:
            print(f"       ! {u} could not be mapped to a consumer — impact NOT recomputed")
        for r in verification.reasons:
            print(f"     - {r}")
        print("     scope: STATIC — no queries executed, no warehouse contacted, no data read.")
        (outdir / f"{args.slug}_VERIFICATION.md").write_text(render_verification_md(verification))
        payload["verification"] = verification_json(verification)

    json_path.write_text(json.dumps(payload, indent=2))
    if verification is not None:
        html_path.write_text(render_html(report, verification=verification))
        print(f"wrote {outdir / (args.slug + '_VERIFICATION.md')}")
    print(f"\nwrote {html_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
