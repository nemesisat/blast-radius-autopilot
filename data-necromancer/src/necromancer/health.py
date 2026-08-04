"""Knowledge Health Status — the leaderboard buckets (the demo's cold open).

Evidence-strength buckets, not fabricated confidence percentages:
    🔴 Critical    — load-bearing AND (undocumented or contradicted)
    🟡 Needs Review — documented but the docs contradict current evidence (a zombie)
    🟠 Forgotten    — undocumented, low usage
    🟢 Healthy      — documented, consistent

Written back to DataHub via add_structured_properties.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .evidence import Evidence
from .investigator import HEAVY_USE_QUERIES, Investigation


class Health(Enum):
    CRITICAL = "🔴 Critical"
    NEEDS_REVIEW = "🟡 Needs Review"
    FORGOTTEN = "🟠 Forgotten"
    HEALTHY = "🟢 Healthy"


# Worst first — this is the leaderboard sort order.
_SEVERITY = {Health.CRITICAL: 0, Health.NEEDS_REVIEW: 1, Health.FORGOTTEN: 2, Health.HEALTHY: 3}


@dataclass
class HealthResult:
    urn: str
    status: Health
    reasons: list[str]


def _heavily_used(ev: Evidence) -> bool:
    return ev.downstream_count > 0 or ev.query_count >= HEAVY_USE_QUERIES


def classify(ev: Evidence, inv: Investigation) -> HealthResult:
    documented = bool(ev.current_description)
    contradicted = inv.is_zombie
    heavy = _heavily_used(ev)
    reasons: list[str] = []

    if heavy and (not documented or contradicted):
        status = Health.CRITICAL
        reasons.append("load-bearing (" + _use_str(ev) + ")")
        reasons.append("undocumented" if not documented else "documentation contradicts evidence")
    elif contradicted:
        status = Health.NEEDS_REVIEW
        reasons.append("zombie: " + "; ".join(str(c) for c in inv.contradictions))
    elif not documented:
        status = Health.FORGOTTEN
        reasons.append("undocumented; " + ("reconstructable" if inv.action != "abstain" else "evidence too thin to reconstruct"))
    else:
        status = Health.HEALTHY
        reasons.append("documented and consistent with evidence")

    return HealthResult(urn=ev.urn, status=status, reasons=reasons)


def _use_str(ev: Evidence) -> str:
    return f"{ev.query_count} queries, {ev.downstream_count} downstream"


def severity_rank(status: Health) -> int:
    return _SEVERITY[status]


def leaderboard(results: list[HealthResult]) -> list[HealthResult]:
    """Worst assets first — the cold-open ranking."""
    return sorted(results, key=lambda r: severity_rank(r.status))


def coverage(results: list[HealthResult]) -> dict[str, float]:
    """Catalog knowledge coverage — the measurable-impact metric.

    healthy_pct is what you show jumping before/after a Necromancer run.
    """
    n = len(results) or 1
    counts = {h: 0 for h in Health}
    for r in results:
        counts[r.status] += 1
    return {
        "assets": len(results),
        "healthy_pct": round(100 * counts[Health.HEALTHY] / n, 1),
        "critical": counts[Health.CRITICAL],
        "needs_review": counts[Health.NEEDS_REVIEW],
        "forgotten": counts[Health.FORGOTTEN],
        "healthy": counts[Health.HEALTHY],
    }
