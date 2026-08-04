"""Compose the sentinel's findings into a root-cause writeup.

The rule-based path always works and needs no API key. If ANTHROPIC_API_KEY is
set, `enrich_with_llm` rewrites the summary into a crisper narrative — this is
the "agent interprets the drift" layer. Detection stays deterministic; the LLM
only phrases the conclusion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .detectors.distribution_drift import DistributionDriftResult
from .detectors.freshness import FreshnessResult
from .detectors.schema_drift import SchemaDriftResult


@dataclass
class Diagnosis:
    has_drift: bool
    drift_score: float
    offending_upstream: str
    report_md: str


def _score(
    schema: SchemaDriftResult,
    dists: list[DistributionDriftResult],
    freshness: FreshnessResult | None,
) -> float:
    """0 = healthy. >=0.25 is a strong at-risk signal (PSI-scaled + penalties)."""
    score = max((d.psi for d in dists), default=0.0)
    if schema.severity == "high":
        score += 0.30
    elif schema.severity == "low":
        score += 0.05
    if freshness and freshness.is_stale:
        score += 0.30 if freshness.severity == "high" else 0.15
    return round(score, 3)


def diagnose(
    model_urn: str,
    schema: SchemaDriftResult,
    dists: list[DistributionDriftResult],
    freshness: FreshnessResult | None,
    upstream_urn: str = "",
) -> Diagnosis:
    drift_score = _score(schema, dists, freshness)
    drifted = [d for d in dists if d.has_drift]
    has_drift = bool(schema.has_drift or drifted or (freshness and freshness.is_stale))

    # Pick the single biggest offender for the machine-readable field.
    if drifted:
        worst = max(drifted, key=lambda d: d.psi)
        offending = f"{upstream_urn or 'upstream'}#{worst.feature}"
    elif freshness and freshness.is_stale:
        offending = upstream_urn or "upstream (freshness)"
    elif schema.has_drift:
        offending = upstream_urn or "upstream (schema)"
    else:
        offending = ""

    verdict = "AT RISK" if drift_score >= 0.25 or has_drift else "healthy"
    lines = [
        f"**Verdict:** {verdict}  ",
        f"**Drift score:** {drift_score}  ",
        f"**Model:** `{model_urn}`",
        "",
        "## Findings",
        f"- **Schema:** {schema.summary()}",
    ]
    if freshness is not None:
        lines.append(f"- **Freshness:** {freshness.summary()}")
    if dists:
        lines.append("- **Distribution:**")
        for d in sorted(dists, key=lambda x: -x.psi):
            flag = "  ⚠️" if d.has_drift else ""
            lines.append(f"    - {d.summary()}{flag}")
    lines += ["", "## Recommended action"]
    if has_drift:
        lines.append(
            "- Investigate the offending upstream before trusting new predictions; "
            "consider retraining on refreshed data or rolling back to the last good snapshot."
        )
    else:
        lines.append("- None. Inputs match the training baseline within thresholds.")

    return Diagnosis(
        has_drift=has_drift,
        drift_score=drift_score,
        offending_upstream=offending,
        report_md="\n".join(lines),
    )


def enrich_with_llm(diagnosis: Diagnosis, model: str = "claude-sonnet-5") -> Diagnosis:
    """Optional: rephrase the report into a tighter narrative. No-op without a key."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return diagnosis
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model,
            max_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are an ML reliability agent. Rewrite the following drift "
                        "report as a crisp root-cause summary a data team can act on. "
                        "Keep the verdict, drift score, and the offending upstream.\n\n"
                        + diagnosis.report_md
                    ),
                }
            ],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if text.strip():
            diagnosis.report_md = text.strip()
    except Exception as exc:  # noqa: BLE001 — narrative is best-effort
        print(f"[agent] LLM enrichment skipped ({exc!r}); using rule-based report.")
    return diagnosis
