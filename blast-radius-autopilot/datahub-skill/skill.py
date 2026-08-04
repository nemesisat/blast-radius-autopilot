"""column-impact-from-queries — a reusable DataHub Skill.

Thin, agent-friendly wrapper over Blast Radius Autopilot's impact core: emits the
column-level blast radius as JSON for a proposed change. Runnable offline (catalog
JSON) or online (live DataHub). Apache-2.0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _load_catalog(args):
    if args.online:
        from autopilot.catalog import DataHubCatalogReader
        from autopilot.schema import Catalog

        reader = DataHubCatalogReader(os.getenv("DATAHUB_GMS_URL"), os.getenv("DATAHUB_TOKEN"))
        target = reader.dataset(args.target_urn)
        queries = list(reader.dataset_queries(args.target_urn))
        for d in reader.downstream_urns(args.target_urn):
            queries += reader.dataset_queries(d)
        return Catalog(name=target.name, datasets=[target], queries=queries, assets=[])
    from autopilot.catalog import load_catalog

    return load_catalog(args.catalog)


def main() -> int:
    ap = argparse.ArgumentParser(description="DataHub Skill: column-level impact from query history")
    ap.add_argument("--catalog")
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--target-urn")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--column", required=True)
    ap.add_argument("--op", default="drop", choices=["drop", "rename"])
    ap.add_argument("--new-name")
    args = ap.parse_args()

    try:
        from autopilot.impact import compute_impact
        from autopilot.schema import ChangeSpec
    except ModuleNotFoundError:
        print("Install the package first:  pip install blast-radius-autopilot", file=sys.stderr)
        return 2

    catalog = _load_catalog(args)
    change = ChangeSpec.parse(args.dataset, args.column, args.op, args.new_name)
    report = compute_impact(catalog, change)

    out = {
        "change": report.change.describe(),
        "catalog": report.catalog,
        "counts": report.counts(),
        "risk": report.risk(),
        "teams_impacted": report.teams_impacted(),
        "verdicts": [
            {
                "query_id": v.query_id,
                "verdict": v.verdict.value,
                "usage": v.usage,
                "confidence": v.confidence,
                "team": v.team,
                "runs": v.runs,
                "asset": v.asset_name,
                "reason": v.reason,
            }
            for v in report.verdicts
        ],
        "notes": report.notes,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
