"""Read layer: walk a model's upstream ML lineage in DataHub and pull the
current schema + freshness of its training inputs.

Library mode (here) uses the DataHub Python SDK / GraphQL, which is stable and
runnable. When the sentinel runs *as an agent*, the same reads map to MCP tools:
    upstream_datasets     -> get_lineage
    dataset_schema        -> get_entities / list_schema_fields
    dataset_last_modified -> get_entities (operation aspect)

GraphQL queries below are intentionally small; verify field names against your
DataHub version at http://localhost:9002/api/graphiql.
"""

from __future__ import annotations

from datetime import datetime, timezone


class DataHubReader:
    def __init__(self, gms_url: str, token: str):
        from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

        self._graph = DataHubGraph(DatahubClientConfig(server=gms_url, token=token))

    def upstream_datasets(self, entity_urn: str, max_hops: int = 3) -> list[str]:
        """Datasets upstream of a model (training inputs), following run lineage."""
        q = """
        query up($urn: String!) {
          searchAcrossLineage(input: {
            urn: $urn, direction: UPSTREAM, count: 100,
            types: [DATASET]
          }) {
            searchResults { entity { urn type } }
          }
        }
        """
        res = self._graph.execute_graphql(q, variables={"urn": entity_urn})
        results = res.get("searchAcrossLineage", {}).get("searchResults", [])
        return [r["entity"]["urn"] for r in results if r["entity"]["type"] == "DATASET"]

    def dataset_schema(self, dataset_urn: str) -> dict[str, str]:
        """{column: native_type} for the current live schema."""
        q = """
        query schema($urn: String!) {
          dataset(urn: $urn) {
            schemaMetadata { fields { fieldPath nativeDataType } }
          }
        }
        """
        res = self._graph.execute_graphql(q, variables={"urn": dataset_urn})
        fields = (res.get("dataset") or {}).get("schemaMetadata", {}).get("fields", []) or []
        return {f["fieldPath"]: f.get("nativeDataType", "") for f in fields}

    def dataset_last_modified(self, dataset_urn: str) -> datetime | None:
        """Last operational update time (freshness signal)."""
        q = """
        query op($urn: String!) {
          dataset(urn: $urn) {
            operations(limit: 1) { lastUpdatedTimestamp }
          }
        }
        """
        res = self._graph.execute_graphql(q, variables={"urn": dataset_urn})
        ops = (res.get("dataset") or {}).get("operations") or []
        if not ops or not ops[0].get("lastUpdatedTimestamp"):
            return None
        return datetime.fromtimestamp(ops[0]["lastUpdatedTimestamp"] / 1000.0, tz=timezone.utc)


def schema_from_csv(csv_path: str) -> dict[str, str]:
    """Offline helper: derive a {column: dtype} schema from a serving CSV so the
    full detect -> report loop can be demoed without wiring DataHub reads."""
    import pandas as pd

    df = pd.read_csv(csv_path, nrows=1000)
    return {c: str(t) for c, t in df.dtypes.items()}


def feature_values_from_csv(csv_path: str, feature: str, limit: int = 5000) -> list[float]:
    import pandas as pd

    series = pd.read_csv(csv_path, usecols=[feature])[feature].dropna()
    return [float(x) for x in series.head(limit).tolist()]
