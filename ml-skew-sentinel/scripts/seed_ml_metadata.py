"""Seed an ML system into DataHub and snapshot a training baseline.

Two phases:
  1. Snapshot baseline  — reads the training CSV, records the schema and a
     per-feature value sample to ``baseline.json``. This is what "training time"
     looked like, and it means distribution-drift detection does NOT depend on
     DataHub retaining historical profiles.
  2. Emit ML metadata   — creates an MLModelGroup, MLModel, input Dataset, and a
     training run with lineage (training data -> run -> model) in DataHub. This
     mirrors the official tutorial: https://docs.datahub.com/docs/api/tutorials/ml

Phase 1 always runs (pure pandas). Phase 2 needs a running DataHub + token and
is wrapped so an SDK mismatch never costs you the baseline.

Usage:
    python scripts/seed_ml_metadata.py --training-data data/nyc_taxi_train.csv
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MODEL_ID = "nyc_taxi_fare_predictor"
MODEL_GROUP_ID = "nyc_taxi_models"
PLATFORM = "mlflow"
SAMPLE_PER_FEATURE = 5000  # values kept per numeric feature for PSI/KS


# --------------------------------------------------------------------------- #
# Phase 1: baseline snapshot (pure pandas — always runs)
# --------------------------------------------------------------------------- #
def snapshot_baseline(training_csv: Path, out_path: Path, model_urn: str) -> dict:
    import pandas as pd

    df = pd.read_csv(training_csv)
    schema = {col: str(dtype) for col, dtype in df.dtypes.items()}

    features: dict[str, dict] = {}
    for col in df.select_dtypes(include="number").columns:
        series = df[col].dropna()
        sample = series.sample(min(len(series), SAMPLE_PER_FEATURE), random_state=42)
        features[col] = {
            "count": int(series.count()),
            "mean": float(series.mean()),
            "std": float(series.std()),
            "min": float(series.min()),
            "max": float(series.max()),
            "sample": [float(x) for x in sample.tolist()],
        }

    baseline = {
        "model_urn": model_urn,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_data": str(training_csv),
        "schema": schema,
        "features": features,
    }
    out_path.write_text(json.dumps(baseline, indent=2))
    print(f"[baseline] wrote {out_path} — {len(features)} numeric features, schema {len(schema)} cols")
    return baseline


# --------------------------------------------------------------------------- #
# Phase 2: emit ML metadata into DataHub
# --------------------------------------------------------------------------- #
def emit_ml_metadata(server_url: str, token: str, training_csv: Path) -> str:
    """Create MLModelGroup -> MLModel with training-run lineage from the dataset.

    Mirrors docs.datahub.com/docs/api/tutorials/ml. If your acryl-datahub version
    exposes different imports, copy dh_ai_client.py from the DataHub repo:
    metadata-ingestion/examples/ai/dh_ai_client.py
    """
    from datahub.metadata.urns import DataProcessInstanceUrn, TagUrn
    from datahub.sdk import Dataset, MLModel, MLModelGroup

    # dh_ai_client.py ships in the DataHub examples; vendored copy expected at
    # scripts/dh_ai_client.py. It wraps run creation + dataset-to-run lineage.
    from dh_ai_client import DatahubAIClient

    client = DatahubAIClient(token=token, server_url=server_url)

    group = MLModelGroup(id=MODEL_GROUP_ID, platform=PLATFORM)
    client._emit_mcps(group.as_mcps())

    model = MLModel(id=MODEL_ID, platform=PLATFORM)
    model.add_group(group.urn)
    model.set_custom_properties(
        {"trained_on": training_csv.name, "owner_team": "ml-platform", "status": "production"}
    )
    model.add_tag(TagUrn("production"))
    client._emit_mcps(model.as_mcps())

    # Input training dataset (point platform/name at the real upstream in your graph).
    input_dataset = Dataset(platform="s3", name="nyc_taxi.trips_features")
    client._emit_mcps(input_dataset.as_mcps())

    # Training run, then wire dataset -> run -> model lineage.
    run_id = "nyc_taxi_training_run_v1"
    client.create_training_run(run_id=run_id)
    client.add_input_datasets_to_run(
        run_urn=f"urn:li:dataProcessInstance:{run_id}",
        dataset_urns=[str(input_dataset.urn)],
    )
    model.add_training_job(DataProcessInstanceUrn(run_id))
    client._emit_mcps(model.as_mcps())

    print(f"[datahub] seeded model {model.urn} with lineage from {input_dataset.urn}")
    return str(model.urn)


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed ML metadata + snapshot training baseline.")
    ap.add_argument("--training-data", required=True, type=Path, help="Path to training CSV")
    ap.add_argument("--baseline-out", default=Path("baseline.json"), type=Path)
    ap.add_argument("--skip-datahub", action="store_true", help="Only snapshot the baseline")
    args = ap.parse_args()

    server_url = os.getenv("DATAHUB_FRONTEND_URL", "http://localhost:9002")
    token = os.getenv("DATAHUB_TOKEN", "")
    model_urn = os.getenv(
        "TARGET_MODEL_URN",
        f"urn:li:mlModel:(urn:li:dataPlatform:{PLATFORM},{MODEL_ID},PROD)",
    )

    snapshot_baseline(args.training_data, args.baseline_out, model_urn)

    if args.skip_datahub:
        print("[datahub] skipped (--skip-datahub)")
        return
    if not token:
        print("[datahub] no DATAHUB_TOKEN set — skipping emission. Set it in .env to seed DataHub.")
        return
    try:
        urn = emit_ml_metadata(server_url, token, args.training_data)
        print(f"\nDone. Put this in your .env:\n  TARGET_MODEL_URN={urn}")
    except Exception as exc:  # noqa: BLE001 — never lose the baseline over an SDK hiccup
        print(f"[datahub] emission failed ({exc!r}).")
        print("Baseline is still saved. Verify SDK imports against your acryl-datahub version,")
        print("and ensure scripts/dh_ai_client.py is vendored from the DataHub examples repo.")


if __name__ == "__main__":
    main()
