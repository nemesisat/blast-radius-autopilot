"""B20 — full GraphQL read-back of a LIVE human-approved write-back.

Reads back EVERYTHING the write-back claims to contribute, as a separate query on the far
side of the write — not an inspection of our own objects:

    structured properties   the blast_radius_* assessment + the B20.3 approval audit
    tags                    pending-schema-change on the target
    institutional memory    the LINK (url + title) to the assessment body
    description             the one-line pending-change footer
    downstream tags         impacted-by-upstream-change + impact-<verdict>

Usage (after the CLI approve run):
    python scripts/b20_live_full_readback.py --approver reviewer@example.com \
        --manifest-id <id> --expect-writes 8
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig  # noqa: E402

from autopilot.catalog import load_catalog  # noqa: E402
from autopilot.impact import compute_impact  # noqa: E402
from autopilot.schema import ChangeSpec  # noqa: E402

AUDIT_KEYS = ["blast_radius_approved_by", "blast_radius_approved_at",
              "blast_radius_manifest_id", "blast_radius_verification_status_at_approval",
              "blast_radius_approved_writes", "blast_radius_approved_failures"]

DATASET_Q = """query v($urn:String!){ dataset(urn:$urn){
  globalTags{tags{tag{urn}}}
  editableProperties{description}
  institutionalMemory{elements{description url}}
  structuredProperties{properties{structuredProperty{urn} values{... on StringValue{stringValue}}}}
}}"""

ANY_Q = """query v($urn:String!){ entity(urn:$urn){
  ... on Dataset { globalTags{tags{tag{urn}}} }
  ... on Dashboard { globalTags{tags{tag{urn}}} }
  ... on Chart { globalTags{tags{tag{urn}}} }
}}"""


def props_of(d) -> dict[str, str]:
    return {p["structuredProperty"]["urn"].rsplit(":", 1)[-1]:
            (p["values"] or [{}])[0].get("stringValue")
            for p in (d.get("structuredProperties") or {}).get("properties", [])}


def tags_of(block) -> list[str]:
    return [t["tag"]["urn"].split(":")[-1]
            for t in ((block or {}).get("globalTags") or {}).get("tags", [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="examples/showcase-ecommerce/catalog.json")
    ap.add_argument("--change", default="drop analytics.fct_orders.customer_zip")
    ap.add_argument("--approver", required=True)
    ap.add_argument("--manifest-id", required=True)
    ap.add_argument("--expect-writes", type=int, required=True)
    ap.add_argument("--expect-verdict", default="REVIEW_REQUIRED")
    args = ap.parse_args()

    token = os.getenv("DATAHUB_TOKEN", "")
    if not token:
        print("No DATAHUB_TOKEN — refusing to guess.")
        return 2
    g = DataHubGraph(DatahubClientConfig(
        server=os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"), token=token))

    op, target = args.change.split(" ", 1)
    dataset, column = target.rsplit(".", 1)
    catalog = load_catalog(ROOT / args.catalog)
    report = compute_impact(catalog, ChangeSpec.parse(dataset, column, op))
    urn = report.target_urn

    print("=" * 88)
    print(f"  LIVE GraphQL READ-BACK — {args.change}")
    print(f"  target {urn}")
    print("=" * 88)

    d = g.execute_graphql(DATASET_Q, variables={"urn": urn})["dataset"]
    props, tags = props_of(d), tags_of(d)
    im = [(e["description"], e["url"]) for e in (d.get("institutionalMemory") or {}).get("elements", [])]
    desc = ((d.get("editableProperties") or {}).get("description") or "")

    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and cond
        print(f"  [{'PASS' if cond else 'FAIL':>4}] {label}" + (f"   {detail}" if detail else ""))

    print(f"\n-- structured properties ({len(props)} on the asset) --")
    for k in sorted(props):
        flag = " <- B20.3 AUDIT" if k in AUDIT_KEYS else ""
        print(f"     {k:<48} {props[k]!r}{flag}")

    print("\n-- assertions: the assessment --")
    check("blast_radius_status == pending-change", props.get("blast_radius_status") == "pending-change")
    check("blast_radius_risk present", bool(props.get("blast_radius_risk")), props.get("blast_radius_risk"))
    check("blast_radius_breaks present", bool(props.get("blast_radius_breaks")), props.get("blast_radius_breaks"))
    check("blast_radius_coverage present", bool(props.get("blast_radius_coverage")), props.get("blast_radius_coverage"))
    check(f"blast_radius_verification_status == {args.expect_verdict}",
          props.get("blast_radius_verification_status") == args.expect_verdict,
          str(props.get("blast_radius_verification_status")))

    print("\n-- assertions: the B20.3 approval audit --")
    for k in AUDIT_KEYS:
        check(f"{k} present", props.get(k) not in (None, ""), repr(props.get(k)))
    check("approved_by == the supplied approver", props.get("blast_radius_approved_by") == args.approver)
    check("manifest_id == the consumed manifest", props.get("blast_radius_manifest_id") == args.manifest_id)
    check(f"verification_status_at_approval == {args.expect_verdict}",
          props.get("blast_radius_verification_status_at_approval") == args.expect_verdict)
    check(f"approved_writes == {args.expect_writes}",
          props.get("blast_radius_approved_writes") == str(args.expect_writes))
    check("approved_failures == 0", props.get("blast_radius_approved_failures") == "0")

    print("\n-- assertions: tags / institutional memory / description --")
    check("tag pending-schema-change", "pending-schema-change" in tags, str(tags))
    check("institutional-memory LINK present", bool(im))
    for title, url in im:
        print(f"        link: {title!r} -> {url}")
    check("the link points at a file that EXISTS",
          any(Path(u.replace("file://", "")).exists() for _t, u in im) if im else False)
    check("description carries the pending-change footer", "⚠️" in desc,
          desc[:90].replace("\n", " "))

    print("\n-- assertions: impacted downstreams tagged --")
    for v in report.assets_impacted():
        try:
            e = g.execute_graphql(ANY_Q, variables={"urn": v.asset_urn})["entity"]
            dt = tags_of(e)
        except Exception as ex:  # noqa: BLE001
            dt = [f"<read error {ex}>"]
        want = f"impact-{v.verdict.value.lower()}"
        check(f"{(v.asset_name or v.asset_urn)[:34]:<34} {want}",
              "impacted-by-upstream-change" in dt and want in dt, str(dt))

    print(f"\n  ALL ASSERTIONS {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
