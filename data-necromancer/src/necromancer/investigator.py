"""The investigation engine — what separates the Necromancer from a documentation
generator.

Two jobs:
  1. RESURRECT: triangulate meaning from >= 2 independent evidence types, and
     REFUSE to write when evidence is too thin (evidence-bound, anti-hallucination).
  2. EXPOSE ZOMBIES: detect assets whose *existing* description contradicts the
     current lineage/queries — metadata that has silently gone wrong. DataHub's
     enrich skill fills blanks; it cannot catch a description that now lies.

Deterministic heuristics here make it demoable and testable. In production an LLM
reasons over the same Evidence; the checks below are the guardrails on that
reasoning, not a replacement for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .evidence import Evidence

# Data platforms/systems a description might claim as a source.
PLATFORM_KEYWORDS = {
    "oracle", "snowflake", "postgres", "postgresql", "mysql", "s3", "kafka",
    "redshift", "bigquery", "mongodb", "mongo", "salesforce", "sap", "erp",
    "databricks", "hive", "teradata", "hadoop", "dynamodb", "sqlserver",
}
# Words that claim an asset is unimportant / on the way out.
DEPRECATION_WORDS = {
    "deprecated", "temporary", "temp", "legacy", "obsolete", "do not use",
    "test", "sandbox", "scratch", "throwaway", "unused",
}
HEAVY_USE_QUERIES = 25  # queries above this = clearly load-bearing


@dataclass
class Contradiction:
    kind: str      # "source_mismatch" | "false_deprecation" | "stale_column"
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.detail}"


@dataclass
class Investigation:
    urn: str
    proposed_description: str
    evidence_strength: int          # count of independent evidence types
    confidence: str                 # strong | moderate | weak | none
    contradictions: list[Contradiction] = field(default_factory=list)
    action: str = "abstain"         # write | review | abstain | none
    rationale: list[str] = field(default_factory=list)

    @property
    def is_zombie(self) -> bool:
        return bool(self.contradictions)


def _confidence(strength: int) -> str:
    return {0: "none", 1: "weak"}.get(strength, "moderate" if strength == 2 else "strong")


def detect_contradictions(ev: Evidence) -> list[Contradiction]:
    """Find where the existing description conflicts with current evidence."""
    out: list[Contradiction] = []
    desc = (ev.current_description or "").lower()
    if not desc:
        return out

    lineage_text = " ".join(ev.lineage_sources).lower()

    # 1) Description claims a source platform that no longer appears upstream.
    if ev.lineage_sources:
        for kw in PLATFORM_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", desc) and kw not in lineage_text:
                out.append(
                    Contradiction(
                        "source_mismatch",
                        f'description cites "{kw}" but current lineage is '
                        f'[{", ".join(ev.lineage_sources)}]',
                    )
                )

    # 2) Marked deprecated/temporary but heavily used — a false deprecation.
    if any(w in desc for w in DEPRECATION_WORDS) and (
        ev.query_count >= HEAVY_USE_QUERIES or ev.downstream_count > 0
    ):
        flagged = next(w for w in DEPRECATION_WORDS if w in desc)
        out.append(
            Contradiction(
                "false_deprecation",
                f'marked "{flagged}" but has {ev.query_count} queries and '
                f"{ev.downstream_count} downstream dependencies",
            )
        )

    # 3) Description references a column that is gone from the current schema.
    if ev.schema_fields:
        current = {f.lower() for f in ev.schema_fields}
        for m in re.findall(r"`([a-zA-Z_][\w]*)`", ev.current_description or ""):
            if m.lower() not in current:
                out.append(
                    Contradiction("stale_column", f"description references removed column `{m}`")
                )
    return out


def _triangulate(ev: Evidence) -> tuple[str, list[str]]:
    """Compose a description from whatever independent evidence corroborates it."""
    bits: list[str] = []
    rationale: list[str] = []
    if ev.lineage_sources:
        bits.append(f"derived from {', '.join(ev.lineage_sources)}")
        rationale.append(f"lineage: {len(ev.lineage_sources)} upstream source(s)")
    if ev.query_count:
        bits.append(f"actively queried ({ev.query_count} queries observed)")
        rationale.append(f"queries: {ev.query_count} real queries reference it")
    if ev.downstream_count:
        bits.append(f"feeds {ev.downstream_count} downstream asset(s)")
        rationale.append(f"downstream: {ev.downstream_count} dependent asset(s)")
    if ev.sibling_terms:
        bits.append(f"related to {', '.join(ev.sibling_terms)}")
        rationale.append(f"glossary: sibling terms {ev.sibling_terms}")
    if ev.schema_fields:
        rationale.append(f"schema: {len(ev.schema_fields)} columns")
    body = "; ".join(bits) if bits else "insufficient evidence to reconstruct"
    return f"{ev.name}: {body}." if bits else body, rationale


def investigate(ev: Evidence) -> Investigation:
    contradictions = detect_contradictions(ev)
    strength = len(ev.types_present())
    proposed, rationale = _triangulate(ev)

    # Decide the action — the evidence-bound guardrail.
    documented = bool(ev.current_description)
    if strength < 2 and not documented:
        action = "abstain"           # too thin to responsibly reconstruct
        rationale.append("ABSTAIN: fewer than 2 independent evidence types")
    elif contradictions:
        action = "review"            # never silently overwrite a contradicted doc
        rationale.append("REVIEW: existing description contradicts current evidence")
    elif documented:
        action = "none"              # already documented and consistent
    elif strength >= 3:
        action = "write"             # strong corroboration, no prior doc
        rationale.append("WRITE: >=3 corroborating evidence types, no prior description")
    else:
        action = "review"            # moderate evidence — propose, ask a human

    return Investigation(
        urn=ev.urn,
        proposed_description=proposed,
        evidence_strength=strength,
        confidence=_confidence(strength),
        contradictions=contradictions,
        action=action,
        rationale=rationale,
    )


def evidence_footer(ev: Evidence, inv: Investigation) -> str:
    """The short, durable provenance line written into the DataHub description."""
    parts = []
    if ev.lineage_sources:
        parts.append(f"{len(ev.lineage_sources)} upstream source(s)")
    if ev.query_count:
        parts.append(f"{ev.query_count} queries")
    if ev.downstream_count:
        parts.append(f"{ev.downstream_count} downstream")
    if ev.sibling_terms:
        parts.append(f"glossary: {', '.join(ev.sibling_terms)}")
    return f"Reconstructed by Data Necromancer from: {', '.join(parts)} (confidence: {inv.confidence})."
