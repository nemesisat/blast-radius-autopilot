"""Live DataHub round-trip demo (bonus evidence).

Requires a running DataHub (docker quickstart) at $DATAHUB_GMS_URL (default
http://localhost:8080). It:
  1. emits the synthetic showcase-ecommerce datasets + schema into the live catalog,
  2. computes the blast radius for `drop analytics.fct_orders.customer_zip`,
  3. runs the REAL write-back (structured properties, tags, assessment doc, description),
  4. reads the dataset back via GraphQL to prove the mutations landed.

Public/synthetic data only.
"""

from __future__ import annotations

import os

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
from autopilot.fixgen import generate_fixes
from autopilot.impact import compute_impact
from autopilot.schema import ChangeSpec
from autopilot.writeback import WriteBack

GMS = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
TOKEN = os.getenv("DATAHUB_TOKEN", "")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _emit_dataset(graph, ds) -> None:
    fields = []
    for name, native in ds.schema.items():
        t = NumberTypeClass() if native.upper() in ("NUMBER", "FLOAT", "INT") else StringTypeClass()
        fields.append(
            SchemaFieldClass(fieldPath=name, type=SchemaFieldDataTypeClass(type=t), nativeDataType=native)
        )
    graph.emit(MetadataChangeProposalWrapper(entityUrn=ds.urn, aspect=DatasetPropertiesClass(name=ds.name)))
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=ds.urn,
            aspect=SchemaMetadataClass(
                schemaName=ds.name, platform=builder.make_data_platform_urn(ds.platform),
                version=0, hash="", platformSchema=OtherSchemaClass(rawSchema=""), fields=fields,
            ),
        )
    )


def main() -> None:
    graph = DataHubGraph(DatahubClientConfig(server=GMS, token=TOKEN))
    catalog = load_catalog(os.path.join(HERE, "examples/showcase-ecommerce/catalog.json"))

    print("1) emit synthetic datasets into live DataHub")
    for ds in catalog.datasets:
        _emit_dataset(graph, ds)
        print(f"   emitted {ds.name}")

    change = ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop")
    report = compute_impact(catalog, change)
    fixes = generate_fixes(catalog, change, report, os.path.join(HERE, "examples/showcase-ecommerce"))
    print(f"\n2) blast radius: {report.counts()}  risk={report.risk()['level']}")

    print("\n3) LIVE write-back")
    wb = WriteBack(gms_url=GMS, token=TOKEN, dry_run=False)
    res, _doc = wb.run(report, fixes)
    print(f"   written: {len(res.written)}")

    print("\n4) GraphQL read-back")
    q = """query v($urn:String!){ dataset(urn:$urn){
      globalTags{tags{tag{urn}}}
      editableProperties{description}
      structuredProperties{properties{structuredProperty{urn} values{... on StringValue{stringValue}}}}
      institutionalMemory{elements{description}}
    }}"""
    d = graph.execute_graphql(q, variables={"urn": report.target_urn})["dataset"]
    print("   tags:", [t["tag"]["urn"] for t in (d.get("globalTags") or {}).get("tags", [])])
    print("   description:", ((d.get("editableProperties") or {}).get("description") or "")[:100])
    sp = (d.get("structuredProperties") or {}).get("properties", [])
    print("   structured properties:", len(sp), "set")
    print("   institutional memory:", [e["description"] for e in (d.get("institutionalMemory") or {}).get("elements", [])])


if __name__ == "__main__":
    main()
