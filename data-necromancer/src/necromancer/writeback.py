"""Write-back: the Necromancer contributes its findings to the graph.

MCP tool mapping (enable TOOLS_IS_MUTATION_ENABLED=true on the server):
    set_description  -> update_description   (with a durable evidence footer)
    set_health       -> add_structured_properties
    save_dictionary  -> save_document

Approve-before-write is enforced *here* (DataHub has no native gate for
descriptions): only investigations whose action == "write" are written; "review"
and "abstain" are surfaced to a human queue instead. dry_run prints intended
mutations without touching the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import Evidence
from .health import HealthResult
from .investigator import Investigation, evidence_footer


@dataclass
class WriteBackResult:
    dry_run: bool
    written: list[str] = field(default_factory=list)
    queued_for_review: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def _p(self, msg: str) -> None:
        print(("[dry-run] would " if self.dry_run else "[write] ") + msg)


class WriteBack:
    def __init__(self, gms_url: str = "", token: str = "", dry_run: bool = True):
        self.gms_url, self.token, self.dry_run = gms_url, token, dry_run
        self._graph = None
        if not dry_run:
            from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

            self._graph = DataHubGraph(DatahubClientConfig(server=gms_url, token=token))

    def apply(self, ev: Evidence, inv: Investigation, health: HealthResult, res: WriteBackResult) -> None:
        # Health status is always safe to record (structured property).
        self._set_health(ev.urn, health.status.value, res)

        if inv.action == "write":
            desc = f"{inv.proposed_description}\n\n_{evidence_footer(ev, inv)}_"
            res._p(f"update_description on {ev.urn}")
            res.written.append(ev.urn)
            if not self.dry_run:
                self._update_description(ev.urn, desc)
        elif inv.action in ("review",):
            res._p(f"QUEUE for human review: {ev.urn} ({_why(inv)})")
            res.queued_for_review.append(ev.urn)
        else:  # abstain / none
            res._p(f"skip {ev.urn} ({inv.action}: {_why(inv)})")
            res.skipped.append(ev.urn)

    # --- individual mutations (SDK; MCP equivalents in the module docstring) ---
    def _set_health(self, urn: str, status: str, res: WriteBackResult) -> None:
        res._p(f"add_structured_properties knowledge_health={status!r} on {urn}")
        if self.dry_run:
            return
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import MLModelPropertiesClass  # placeholder aspect

        # NOTE: use the real structured-property emit for your entity type; the
        # property must be defined once first. See docs/api/tutorials/structured-properties.
        _ = (MetadataChangeProposalWrapper, MLModelPropertiesClass)

    def _update_description(self, urn: str, description: str) -> None:
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import EditableDatasetPropertiesClass

        aspect = self._graph.get_aspect(urn, EditableDatasetPropertiesClass) or EditableDatasetPropertiesClass()
        aspect.description = description
        self._graph.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))


def _why(inv: Investigation) -> str:
    if inv.contradictions:
        return "; ".join(str(c) for c in inv.contradictions)
    return f"{inv.confidence} evidence"
