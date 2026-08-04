"""Write-back layer: the part judges reward most — the agent contributes its
diagnosis *back* to the graph so the next person/agent inherits it.

Library mode uses the DataHub SDK. When running as an agent over MCP, the same
effects map 1:1 to the MCP mutation tools (enable with
TOOLS_IS_MUTATION_ENABLED=true on the server):
    add_at_risk_tag        -> add_tags
    set_drift_properties    -> add_structured_properties   (custom props need no schema)
    banner in description   -> update_description
    save_root_cause_document-> save_document

Reads/writes here follow the documented APIs; run them against your local
DataHub to confirm aspect/field names for your version. `dry_run=True` prints the
intended mutations without touching the graph — use it for the first demo pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

AT_RISK_TAG = "urn:li:tag:at-risk"
SKEW_TAG = "urn:li:tag:skew-detected"


@dataclass
class WriteBackResult:
    model_urn: str
    dry_run: bool
    actions: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        prefix = "[dry-run] would " if self.dry_run else "[write] "
        line = prefix + msg
        self.actions.append(line)
        print(line)


class WriteBack:
    def __init__(self, gms_url: str, token: str, dry_run: bool = False):
        self.gms_url = gms_url
        self.token = token
        self.dry_run = dry_run
        self._graph = None
        if not dry_run:
            from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

            self._graph = DataHubGraph(DatahubClientConfig(server=gms_url, token=token))

    # --- individual mutations ------------------------------------------------
    def add_at_risk_tag(self, model_urn: str, res: WriteBackResult) -> None:
        res.log(f"tag {model_urn} with at-risk + skew-detected")
        if self.dry_run:
            return
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import (
            GlobalTagsClass,
            TagAssociationClass,
        )

        existing = self._graph.get_aspect(model_urn, GlobalTagsClass) or GlobalTagsClass(tags=[])
        have = {t.tag for t in existing.tags}
        for tag in (AT_RISK_TAG, SKEW_TAG):
            if tag not in have:
                existing.tags.append(TagAssociationClass(tag=tag))
        self._graph.emit(MetadataChangeProposalWrapper(entityUrn=model_urn, aspect=existing))

    def set_drift_properties(self, model_urn: str, props: dict[str, str], res: WriteBackResult) -> None:
        res.log(f"set drift properties on {model_urn}: {props}")
        if self.dry_run:
            return
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import MLModelPropertiesClass

        existing = self._graph.get_aspect(model_urn, MLModelPropertiesClass) or MLModelPropertiesClass()
        existing.customProperties = {**(existing.customProperties or {}), **props}
        self._graph.emit(MetadataChangeProposalWrapper(entityUrn=model_urn, aspect=existing))

    def save_root_cause_document(self, model_urn: str, title: str, body_md: str, res: WriteBackResult) -> Path:
        """Persist the root-cause writeup. As an agent this is the MCP
        `save_document` tool; here we also drop a local copy under runs/."""
        res.log(f"save knowledge document '{title}' linked to {model_urn} (MCP: save_document)")
        runs = Path("runs")
        runs.mkdir(exist_ok=True)
        out = runs / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_root_cause.md"
        out.write_text(f"# {title}\n\nModel: `{model_urn}`\n\n{body_md}\n")
        res.log(f"wrote local copy {out}")
        return out

    # --- orchestration -------------------------------------------------------
    def flag_at_risk(
        self,
        model_urn: str,
        drift_score: float,
        offending_upstream: str,
        report_md: str,
    ) -> WriteBackResult:
        res = WriteBackResult(model_urn=model_urn, dry_run=self.dry_run)
        props = {
            "skew_status": "at-risk",
            "skew_drift_score": f"{drift_score:.3f}",
            "skew_offending_upstream": offending_upstream,
            "skew_checked_at": datetime.now(timezone.utc).isoformat(),
        }
        self.add_at_risk_tag(model_urn, res)
        self.set_drift_properties(model_urn, props, res)
        self.save_root_cause_document(model_urn, "ML Skew Sentinel: at-risk", report_md, res)
        return res
