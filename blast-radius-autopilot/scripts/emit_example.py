"""Thin --online wrapper: emit an example catalog into a live DataHub, then run the
agent's write-back online. Reuses the package's load_catalog + compute_impact +
WriteBack + the SDK emit pattern from live_datahub_demo.py. No core-logic changes.

Emits real schemas so assets are browsable (not blank):
  - every catalog dataset  -> DatasetProperties + SchemaMetadata (types from the catalog)
  - dataset-platform assets (e.g. dbt models) -> schema synthesised from the columns
    their defining query projects (so downstream models are browsable too)
Then computes impact for the given change and writes back (gated by the catalog's
require_review flag). Public/synthetic sample data only.

Usage:
  python scripts/emit_example.py examples/nyc-taxi/catalog.json \
         --change "drop nyc.trips.trip_distance" --write
"""

from __future__ import annotations

import argparse
import os
import sys

import sqlglot
from sqlglot import exp

import datahub.emitter.mce_builder as builder
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig
from datahub.metadata.schema_classes import (
    DatasetPropertiesClass,
    NumberTypeClass,
    OtherSchemaClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StringTypeClass,
)

from autopilot.catalog import load_catalog
from autopilot.impact import compute_impact
from autopilot.schema import ChangeSpec
from autopilot.writeback import WriteBack


def _field(name: str, native: str) -> SchemaFieldClass:
    t = NumberTypeClass() if native.upper().startswith(("NUMBER", "FLOAT", "INT", "DOUBLE")) else StringTypeClass()
    return SchemaFieldClass(fieldPath=name, type=SchemaFieldDataTypeClass(type=t), nativeDataType=native)


def _emit_dataset(graph, urn, name, platform, schema: dict, description: str = "") -> None:
    graph.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=DatasetPropertiesClass(name=name, description=description or None)))
    if schema:
        graph.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=SchemaMetadataClass(
            schemaName=name, platform=builder.make_data_platform_urn(platform), version=0, hash="",
            platformSchema=OtherSchemaClass(rawSchema=""), fields=[_field(c, t) for c, t in schema.items()])))


def _projected_cols(sql: str, dialect: str) -> dict:
    try:
        expr = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return {}
    cols = {}
    for sel in expr.find_all(exp.Select):
        for proj in sel.expressions:
            name = proj.alias_or_name
            if name and name != "*":
                cols[name] = "STRING"
        break
    return cols


def main() -> int:
    ap = argparse.ArgumentParser(description="Emit an example catalog into DataHub + write back")
    ap.add_argument("catalog")
    ap.add_argument("--change", required=True, help='e.g. "drop nyc.trips.trip_distance"')
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    gms = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
    token = os.getenv("DATAHUB_TOKEN", "")
    graph = DataHubGraph(DatahubClientConfig(server=gms, token=token))
    catalog = load_catalog(args.catalog)

    # 1) emit target datasets (real schemas from the catalog)
    for ds in catalog.datasets:
        _emit_dataset(graph, ds.urn, ds.name, ds.platform, ds.schema, f"{ds.platform} table (synthetic example).")
    # 2) emit dataset-platform assets (e.g. dbt models) with schema from their defining query
    q_by_id = {q.query_id: q for q in catalog.queries}
    for a in catalog.assets:
        if ":dataset:" in a.urn:
            q = q_by_id.get(a.defining_query_id or "")
            schema = _projected_cols(q.sql, catalog.sql_dialect) if q else {}
            _emit_dataset(graph, a.urn, a.name, a.platform, schema, f"{a.type} (synthetic example).")

    # 3) impact + write-back (gated by the catalog's require_review)
    toks = args.change.split()
    op = toks[0]; dataset, _, column = toks[1].rpartition("."); new_name = toks[2] if len(toks) > 2 else None
    change = ChangeSpec.parse(dataset, column, op, new_name)
    report = compute_impact(catalog, change)
    print(f"[{catalog.name}] {change.describe()} -> {report.counts()} risk={report.risk()['level']} "
          f"(require_review={catalog.require_review})")
    wb = WriteBack(gms_url=gms, token=token, dry_run=not args.write, require_review=catalog.require_review)
    res, _doc = wb.run(report, [])
    print(f"[{catalog.name}] written={len(res.written)} queued={len(res.queued_for_review)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
