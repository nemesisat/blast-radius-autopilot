"""Evidence: the facts the Necromancer investigates.

Collected from DataHub's read surface. When running as an agent, each field maps
to an MCP tool; in library mode it's the SDK/GraphQL equivalent:

    schema_fields    -> list_schema_fields / get_entities
    lineage_sources  -> get_lineage, get_lineage_paths_between
    query_count/tokens-> get_dataset_queries
    downstream_count -> get_lineage (DOWNSTREAM)
    sibling_terms    -> get_entities on lineage neighbours

Evidence is a plain dataclass so the investigator and health logic are pure and
unit-testable without a live catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    urn: str
    name: str
    current_description: str | None = None
    owner: str | None = None
    schema_fields: list[str] = field(default_factory=list)
    lineage_sources: list[str] = field(default_factory=list)  # upstream names/platforms
    downstream_count: int = 0                                  # dashboards + datasets downstream
    query_count: int = 0                                       # real queries referencing it
    query_tokens: list[str] = field(default_factory=list)      # column/table tokens seen in queries
    sibling_terms: list[str] = field(default_factory=list)     # glossary terms on neighbours

    def types_present(self) -> set[str]:
        """Which independent evidence types we actually have (drives confidence)."""
        present = set()
        if self.schema_fields:
            present.add("schema")
        if self.lineage_sources:
            present.add("lineage")
        if self.query_count > 0:
            present.add("queries")
        if self.downstream_count > 0:
            present.add("downstream")
        if self.sibling_terms:
            present.add("glossary")
        return present


# --------------------------------------------------------------------------- #
# DataHub collection (documented APIs; verify field names on your instance)
# --------------------------------------------------------------------------- #
def collect_from_datahub(gms_url: str, token: str, urn: str) -> Evidence:
    """Gather evidence for one asset via the DataHub SDK/GraphQL.

    This mirrors the MCP read tools. Kept thin on purpose — confirm the exact
    GraphQL fields against http://localhost:9002/api/graphiql for your version.
    """
    from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

    graph = DataHubGraph(DatahubClientConfig(server=gms_url, token=token))
    q = """
    query ev($urn: String!) {
      dataset(urn: $urn) {
        name
        properties { description }
        ownership { owners { owner { urn } } }
        schemaMetadata { fields { fieldPath } }
      }
    }
    """
    res = graph.execute_graphql(q, variables={"urn": urn})
    d = res.get("dataset") or {}
    owners = (d.get("ownership") or {}).get("owners") or []
    fields = (d.get("schemaMetadata") or {}).get("fields") or []
    # Lineage + queries would be pulled via searchAcrossLineage / dataset queries;
    # left as follow-up wiring so the investigation core stays the focus.
    return Evidence(
        urn=urn,
        name=d.get("name", urn),
        current_description=(d.get("properties") or {}).get("description"),
        owner=owners[0]["owner"]["urn"] if owners else None,
        schema_fields=[f["fieldPath"] for f in fields],
    )
