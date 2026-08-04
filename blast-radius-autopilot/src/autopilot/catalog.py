"""Read layer — gather the universal primitives the impact core needs.

Two sources, one shape (`Catalog`):

  * OFFLINE  — load a JSON catalog + query log (the fallback blessed in BUILD_GUIDE;
    also how the reference repos demo without a live instance). This mirrors what
    the MCP read tools return, so the impact core is identical online and offline.

  * ONLINE   — pull from DataHub via the SDK / MCP read tools:
        list_schema_fields / get_entities   -> Dataset.schema, owners
        get_lineage (DOWNSTREAM)            -> candidate downstream Assets
        get_dataset_queries                 -> Query history (T + downstreams)
    (Requires `pip install acryl-datahub` and a reachable GMS. Kept thin on
    purpose; the offline path is the tested one.)

Nothing here is dataset-specific: a catalog is just datasets + queries + assets.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import Asset, Catalog, Dataset, Query


# --------------------------------------------------------------------------- #
# Offline loader (the tested path)
# --------------------------------------------------------------------------- #
def load_catalog(catalog_path: str | Path, query_log_path: str | Path | None = None) -> Catalog:
    """Load a Catalog from a JSON metadata file (+ optional query log).

    `catalog.json` shape::

        {"name": ..., "sql_dialect": "snowflake",
         "datasets": [{"urn","name","sql_name","platform","schema","owners"}, ...],
         "assets":   [{"urn","name","type","platform","owners",
                       "defining_query_id","dbt_path"}, ...]}

    Query history may live inline (`catalog["queries"]`) or in a separate
    `query_log.json` (a list of query objects). If `query_log_path` is omitted,
    a sibling `query_log.json` is used when present.
    """
    catalog_path = Path(catalog_path)
    raw = json.loads(catalog_path.read_text())

    datasets = [_dataset(d) for d in raw.get("datasets", [])]
    assets = [_asset(a) for a in raw.get("assets", [])]

    queries_raw = list(raw.get("queries", []))
    if query_log_path is None:
        sibling = catalog_path.parent / "query_log.json"
        if sibling.exists():
            query_log_path = sibling
    if query_log_path is not None:
        queries_raw += json.loads(Path(query_log_path).read_text())

    queries = [_query(q) for q in queries_raw]

    return Catalog(
        name=raw.get("name", catalog_path.parent.name),
        datasets=datasets,
        queries=queries,
        assets=assets,
        sql_dialect=raw.get("sql_dialect", "snowflake"),
        require_review=bool(raw.get("require_review", False)),
        compliance_note=raw.get("compliance_note", ""),
    )


def _dataset(d: dict) -> Dataset:
    return Dataset(
        urn=d["urn"],
        name=d.get("name", d["urn"]),
        sql_name=d.get("sql_name", d.get("name", d["urn"])),
        platform=d.get("platform", "unknown"),
        schema=dict(d.get("schema", {})),
        owners=list(d.get("owners", [])),
    )


def _asset(a: dict) -> Asset:
    return Asset(
        urn=a["urn"],
        name=a.get("name", a["urn"]),
        type=a.get("type", "asset"),
        platform=a.get("platform", "unknown"),
        owners=list(a.get("owners", [])),
        defining_query_id=a.get("defining_query_id"),
        dbt_path=a.get("dbt_path"),
    )


def _query(q: dict) -> Query:
    return Query(
        query_id=q["query_id"],
        sql=q["sql"],
        platform=q.get("platform", "unknown"),
        team=q.get("team"),
        actor=q.get("actor"),
        runs=int(q.get("runs", 1)),
        last_run=q.get("last_run"),
    )


# --------------------------------------------------------------------------- #
# Online reader (DataHub SDK / MCP). Optional — offline is the tested path.
# --------------------------------------------------------------------------- #
class DataHubCatalogReader:
    """Assemble a Catalog for one target dataset from a live DataHub instance.

    Maps 1:1 to the MCP read tools (see module docstring). Used only with
    `--online`; import of `acryl-datahub` is deferred so the offline path has no
    heavy dependency.
    """

    def __init__(self, gms_url: str | None = None, token: str | None = None):
        from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

        self.gms_url = gms_url or os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
        self.token = token or os.getenv("DATAHUB_TOKEN", "")
        self._graph = DataHubGraph(DatahubClientConfig(server=self.gms_url, token=self.token))

    # -- schema (list_schema_fields / get_entities) ------------------------
    def dataset(self, urn: str) -> Dataset:
        q = """
        query ds($urn: String!) {
          dataset(urn: $urn) {
            name platform { name }
            ownership { owners { owner { urn } } }
            schemaMetadata { fields { fieldPath nativeDataType } }
          }
        }
        """
        d = (self._graph.execute_graphql(q, variables={"urn": urn}) or {}).get("dataset") or {}
        fields = (d.get("schemaMetadata") or {}).get("fields") or []
        owners = [o["owner"]["urn"] for o in (d.get("ownership") or {}).get("owners", [])]
        name = d.get("name") or urn
        return Dataset(
            urn=urn,
            name=name,
            sql_name=name,
            platform=(d.get("platform") or {}).get("name", "unknown"),
            schema={f["fieldPath"]: f.get("nativeDataType", "") for f in fields},
            owners=owners,
        )

    # -- downstream lineage (get_lineage DOWNSTREAM) -----------------------
    def downstream_urns(self, urn: str, count: int = 200) -> list[str]:
        q = """
        query down($urn: String!, $count: Int!) {
          searchAcrossLineage(input: {urn: $urn, direction: DOWNSTREAM, count: $count}) {
            searchResults { entity { urn type } }
          }
        }
        """
        res = self._graph.execute_graphql(q, variables={"urn": urn, "count": count}) or {}
        results = (res.get("searchAcrossLineage") or {}).get("searchResults", [])
        return [r["entity"]["urn"] for r in results]

    # -- query history (get_dataset_queries) -------------------------------
    def dataset_queries(self, urn: str, limit: int = 200) -> list[Query]:
        q = """
        query dq($urn: String!, $limit: Int!) {
          dataset(urn: $urn) {
            usageStats(resource: $urn) { buckets { metrics { topSqlQueries } } }
            queries(start: 0, count: $limit) {
              queries { query environment }
            }
          }
        }
        """
        try:
            d = (self._graph.execute_graphql(q, variables={"urn": urn, "limit": limit}) or {}).get("dataset") or {}
        except Exception:  # noqa: BLE001 — GraphQL shape varies by version; caller falls back
            return []
        out: list[Query] = []
        for i, item in enumerate((d.get("queries") or {}).get("queries", []) or []):
            sql = item.get("query")
            if sql:
                out.append(Query(query_id=f"{urn}#q{i}", sql=sql, platform=item.get("environment", "unknown")))
        return out

    def parse_sql_lineage(self, sql: str, default_db: str | None = None, default_schema: str | None = None):
        """Delegate to DataHub's own SQL parser when available (column lineage).

        The offline engine (`lineage.py`) uses sqlglot directly — the same engine
        DataHub's parser is built on — so results match. This hook lets an online
        run prefer DataHub's parser and its confidence_score.
        """
        return self._graph.parse_sql_lineage(sql, default_db=default_db, default_schema=default_schema)
