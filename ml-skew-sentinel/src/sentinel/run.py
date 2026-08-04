"""CLI: read -> detect -> diagnose -> write back.

Offline (default) reads the current schema/values from a serving CSV so you can
demo the whole loop with no DataHub wiring. `--online` pulls schema + freshness
from DataHub via lineage.py. `--write` performs the write-back (otherwise it's a
dry run that prints the intended mutations).

    # offline dry run
    python -m sentinel.run --baseline baseline.json --serving-data data/nyc_taxi_live.csv

    # against DataHub, actually writing the diagnosis back
    python -m sentinel.run --online --write --serving-data data/nyc_taxi_live.csv
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .agent import diagnose, enrich_with_llm
from .detectors import detect_distribution_drift, detect_freshness, detect_schema_drift
from .lineage import feature_values_from_csv, schema_from_csv


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # noqa: BLE001 — dotenv is a convenience, not required
        pass


def _current_schema_and_freshness(args, model_urn):
    """Returns (current_schema, last_modified, upstream_urn)."""
    if args.online:
        from .lineage import DataHubReader

        reader = DataHubReader(os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"), os.getenv("DATAHUB_TOKEN", ""))
        upstreams = reader.upstream_datasets(model_urn)
        upstream = args.upstream_urn or (upstreams[0] if upstreams else "")
        if not upstream:
            raise SystemExit("No upstream dataset found for model; pass --upstream-urn.")
        return reader.dataset_schema(upstream), reader.dataset_last_modified(upstream), upstream

    # offline: derive from the serving CSV
    schema = schema_from_csv(args.serving_data)
    if args.last_modified:
        lm = datetime.fromisoformat(args.last_modified)
    else:
        lm = datetime.fromtimestamp(Path(args.serving_data).stat().st_mtime, tz=timezone.utc)
    return schema, lm, args.upstream_urn or f"file://{args.serving_data}"


def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser(description="ML Skew Sentinel")
    ap.add_argument("--baseline", default="baseline.json", type=Path)
    ap.add_argument("--serving-data", required=True, help="CSV of current/live feature values")
    ap.add_argument("--model-urn", default=os.getenv("TARGET_MODEL_URN", ""))
    ap.add_argument("--upstream-urn", default="")
    ap.add_argument("--online", action="store_true", help="Read schema/freshness from DataHub")
    ap.add_argument("--write", action="store_true", help="Write diagnosis back (default: dry run)")
    ap.add_argument("--max-age-hours", type=float, default=24.0)
    ap.add_argument("--last-modified", default="", help="ISO time override for freshness (offline)")
    args = ap.parse_args()

    baseline = json.loads(Path(args.baseline).read_text())
    model_urn = args.model_urn or baseline.get("model_urn", "urn:li:mlModel:(unknown)")

    current_schema, last_modified, upstream_urn = _current_schema_and_freshness(args, model_urn)

    # 1) schema drift
    schema_res = detect_schema_drift(baseline["schema"], current_schema)

    # 2) distribution drift per numeric feature present in both baseline and serving data
    dist_res = []
    for feature, stats in baseline.get("features", {}).items():
        if feature not in current_schema:
            continue
        try:
            current_vals = feature_values_from_csv(args.serving_data, feature)
        except Exception:  # noqa: BLE001 — feature not in serving CSV; skip
            continue
        if current_vals and stats.get("sample"):
            dist_res.append(detect_distribution_drift(feature, stats["sample"], current_vals))

    # 3) freshness
    fresh_res = detect_freshness(last_modified, max_age_hours=args.max_age_hours) if last_modified else None

    # diagnose + optional LLM narrative
    dx = enrich_with_llm(diagnose(model_urn, schema_res, dist_res, fresh_res, upstream_urn))

    print("\n" + "=" * 70)
    print(dx.report_md)
    print("=" * 70 + "\n")

    # persist the report
    runs = Path("runs")
    runs.mkdir(exist_ok=True)
    report_path = runs / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_report.md"
    report_path.write_text(dx.report_md + "\n")
    print(f"Report written to {report_path}")

    # write back if drift found
    if dx.has_drift:
        from .writeback import WriteBack

        wb = WriteBack(
            gms_url=os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
            token=os.getenv("DATAHUB_TOKEN", ""),
            dry_run=not args.write,
        )
        wb.flag_at_risk(model_urn, dx.drift_score, dx.offending_upstream, dx.report_md)
    else:
        print("No drift detected — nothing to write back.")


if __name__ == "__main__":
    main()
