"""B20.3 live evidence — approve against a REAL DataHub, then read the audit back.

The offline capture (`scripts/b20_3_approval_audit_run.py`) proves the audit is in the
payload that leaves the process. This proves it is in the CATALOG: it approves against a
live GMS and then asks DataHub, over GraphQL, what it holds — a separate query on the
other side of the write, not an inspection of our own objects.

Requires a running DataHub at $DATAHUB_GMS_URL with $DATAHUB_TOKEN (see .env, gitignored).

  1. emit the synthetic showcase-ecommerce datasets + schema
  2. compute impact, generate fixes, statically verify  -> REVIEW_REQUIRED
  3. dry run -> approval manifest
  4. LIVE `approve(--approver ... --write)`
  5. GraphQL read-back of the six approval-audit properties

Public/synthetic data only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig  # noqa: E402

from autopilot.catalog import load_catalog  # noqa: E402
from autopilot.fixgen import generate_fixes  # noqa: E402
from autopilot.impact import compute_impact  # noqa: E402
from autopilot.schema import ChangeSpec  # noqa: E402
from autopilot.verify import verify_migration  # noqa: E402
from autopilot.writeback import WriteBack  # noqa: E402
from live_datahub_demo import _emit_dataset  # noqa: E402  (reuse, do not duplicate)

GMS = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
TOKEN = os.getenv("DATAHUB_TOKEN", "")
APPROVER = os.getenv("BRA_APPROVER", "reviewer@example.com")
EX = ROOT / "examples" / "showcase-ecommerce"
OUT = ROOT / "out"

AUDIT_KEYS = [
    "blast_radius_approved_by",
    "blast_radius_approved_at",
    "blast_radius_manifest_id",
    "blast_radius_verification_status_at_approval",
    "blast_radius_approved_writes",
    "blast_radius_approved_failures",
]

READ_BACK = """query v($urn:String!){ dataset(urn:$urn){
  structuredProperties{properties{
    structuredProperty{urn}
    values{... on StringValue{stringValue} ... on NumberValue{numberValue}}
  }}
}}"""


def head(text: str) -> None:
    print("\n" + "=" * 88)
    print(f"  {text}")
    print("=" * 88)


def read_back(graph, urn: str) -> dict[str, str]:
    d = graph.execute_graphql(READ_BACK, variables={"urn": urn})["dataset"]
    out = {}
    for p in (d.get("structuredProperties") or {}).get("properties", []):
        key = p["structuredProperty"]["urn"].rsplit(":", 1)[-1]
        vals = p.get("values") or [{}]
        out[key] = str(vals[0].get("stringValue", vals[0].get("numberValue", "")))
    return out


def main() -> int:
    if not TOKEN:
        print("No DATAHUB_TOKEN — set it (see .env.example). Refusing to guess.")
        return 2
    graph = DataHubGraph(DatahubClientConfig(server=GMS, token=TOKEN))
    catalog = load_catalog(EX / "catalog.json")

    head("B20.3 LIVE (1) — emit the synthetic datasets into the running DataHub")
    for ds in catalog.datasets:
        _emit_dataset(graph, ds)
        print(f"   emitted {ds.name}  ({len(ds.schema)} columns)")

    head("B20.3 LIVE (2) — impact + static verification")
    change = ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop")
    report = compute_impact(catalog, change)
    fixes = generate_fixes(catalog, change, report, EX)
    v = verify_migration(change, report, "".join(fx.diff for fx in fixes if fx.diff), EX,
                         catalog=catalog,
                         expected_files=[fx.path for fx in fixes if fx.path] or None)
    print(f"   target      {report.target_urn}")
    print(f"   impact      {report.counts()}")
    print(f"   verdict     {v.status}  ({', '.join(v.reasons)})")
    if v.status != "REVIEW_REQUIRED":
        print("   Expected REVIEW_REQUIRED for this target; aborting rather than "
              "reporting something else as the approval path.")
        return 1

    head("B20.3 LIVE (3) — dry run -> approval manifest")
    dry = WriteBack(dry_run=True, assessment_dir=OUT, manifest_dir=OUT)
    queued, _ = dry.run(report, fixes, verification=v)
    print(f"   manifest    {queued.manifest_path}")
    print(f"   awaiting    {len(queued.queued_for_review)} mutation(s)")

    head(f"B20.3 LIVE (4) — approve against LIVE GMS as {APPROVER}")
    wb = WriteBack(gms_url=GMS, token=TOKEN, dry_run=False,
                   assessment_dir=OUT, manifest_dir=OUT)
    res, _doc = wb.approve(Path(queued.manifest_path), report, fixes, verification=v,
                           approver=APPROVER)
    print(f"   written_human_approved  {len(res.written_human_approved)}")
    print(f"   written_auto            {len(res.written_auto)}")
    print(f"   failed                  {len(res.failed)}")
    print(f"   audit_status            {res.audit_status}")

    head("B20.3 LIVE (5) — GraphQL READ-BACK from DataHub (a separate query, not our object)")
    live = read_back(graph, report.target_urn)
    print(f"   DataHub holds {len(live)} structured propert(ies) on the target\n")
    ok = True
    for key in AUDIT_KEYS:
        got = live.get(key)
        mark = "PASS" if got not in (None, "") else "MISSING"
        ok = ok and mark == "PASS"
        print(f"   [{mark:>7}] {key:<48} {got!r}")
    print()
    expect = {
        "blast_radius_approved_by": APPROVER,
        "blast_radius_manifest_id": res.manifest_id,
        "blast_radius_verification_status_at_approval": "REVIEW_REQUIRED",
        "blast_radius_approved_writes": str(len(res.written_human_approved)),
        "blast_radius_approved_failures": str(len(res.failed)),
    }
    for key, want in expect.items():
        same = live.get(key) == want
        ok = ok and same
        print(f"   [{'PASS' if same else 'FAIL':>7}] {key} == {want!r}   "
              f"(read back {live.get(key)!r})")
    # The assessment must have survived the audit emit.
    for key in ("blast_radius_status", "blast_radius_risk", "blast_radius_breaks",
                "blast_radius_verification_status"):
        present = key in live
        ok = ok and present
        print(f"   [{'PASS' if present else 'FAIL':>7}] base property preserved: {key} = "
              f"{live.get(key)!r}")
    print(f"\n   ALL ASSERTIONS {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
