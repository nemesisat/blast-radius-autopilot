"""B14 — grounded Migration Planner.

Turns an existing impact result into a step-by-step safe-change plan using ONLY
facts derivable from the data. No invented hours, dates, deployment windows, or
success percentages. The single "confidence" surfaced is the column-analysis
(parser) confidence from the impact verdicts, always labelled as such.

Everything else that a human must decide — effort, timeline, deployment window —
is emitted as an explicit "⟨human to decide⟩" placeholder, never computed.

Does not change the impact or fix-generation cores; it only reads their output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .schema import ChangeSpec, ImpactReport, Op

HUMAN = "⟨human to decide⟩"

# Asset-type tiers for the topological tiebreak: sources/models first, BI last.
_BI = ("dashboard", "report", "chart", "workbook", "looker", "powerbi", "tableau", "bi", "explore")


def _tier(asset_type: str | None) -> int:
    t = (asset_type or "").lower()
    if any(x in t for x in _BI):
        return 2          # BI consumers last
    if "view" in t:
        return 1
    return 0              # tables / dbt models / datasets first


def _toposort(nodes: list[str], deps: dict[str, list[str]], tiers: dict[str, int], names: dict[str, str]) -> list[str]:
    """Kahn topological sort over the impacted-asset subgraph. `deps[n]` lists the
    upstream nodes n depends on (restricted to the impacted set). Ties are broken by
    (tier, name) so sources/models come before BI and the order is deterministic."""
    nodeset = set(nodes)
    up = {n: [u for u in deps.get(n, []) if u in nodeset and u != n] for n in nodes}
    indeg = {n: len(up[n]) for n in nodes}
    downs: dict[str, list[str]] = {n: [] for n in nodes}
    for n in nodes:
        for u in up[n]:
            downs[u].append(n)
    order: list[str] = []
    placed: set[str] = set()
    avail = [n for n in nodes if indeg[n] == 0]
    while avail:
        avail.sort(key=lambda n: (tiers.get(n, 0), names.get(n, n)))
        n = avail.pop(0)
        order.append(n)
        placed.add(n)
        for d in downs[n]:
            indeg[d] -= 1
            if indeg[d] == 0:
                avail.append(d)
    # any cycle leftovers: append deterministically so nothing is dropped
    leftover = [n for n in nodes if n not in placed]
    leftover.sort(key=lambda n: (tiers.get(n, 0), names.get(n, n)))
    return order + leftover


@dataclass
class PlanStep:
    order: int
    key: str                       # asset_urn or query_id
    asset_name: str
    asset_type: str
    verdict: str                   # BREAKS | DEGRADES
    owner: str
    action: str                    # "apply generated fix: <path>" | "manual review"
    parser_confidence: str         # high | medium | low  (column-analysis confidence)
    verified: str = "not verified"  # verified-clean | still impacted after fix | unassessed | not verified


@dataclass
class MigrationPlan:
    change: str
    risk_level: str
    risk_score: int
    ordered_steps: list[PlanStep] = field(default_factory=list)
    teams_to_involve: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)          # impacted downstreams to verify
    rollback: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Human-only — never computed:
    effort: str = HUMAN
    timeline: str = HUMAN
    deploy_window: str = HUMAN


def _as_fix_list(generated_fix) -> list:
    if generated_fix is None:
        return []
    return list(generated_fix) if isinstance(generated_fix, (list, tuple)) else [generated_fix]


def build_plan(change: ChangeSpec, impact_result: ImpactReport, lineage: dict | None = None,
               owners: dict | None = None, generated_fix=None, verification=None) -> MigrationPlan:
    """Derive a safe-change plan from the impact result. All fields are derived;
    effort/timeline/deploy window are left as explicit human placeholders."""
    lineage = lineage or {}
    owners = owners or {}
    fixes = {f.asset_urn: f for f in _as_fix_list(generated_fix)
             if getattr(f, "applicable", False) and getattr(f, "changed", False)}

    # Confident breaks + degrades, PLUS every consumer we could not assess. An
    # unassessed consumer earns a manual-review step: leaving it out of the plan
    # would silently imply it needs no work.
    impacted = impact_result.impacted() + impact_result.unknown
    key = lambda v: v.asset_urn or v.query_id               # noqa: E731
    tiers = {key(v): _tier(v.asset_type) for v in impacted}
    names = {key(v): (v.asset_name or v.query_id) for v in impacted}
    ordered_keys = _toposort([key(v) for v in impacted], lineage, tiers, names)
    by_key = {key(v): v for v in impacted}

    def owner_of(v) -> str:
        o = owners.get(v.asset_urn or "") or owners.get(v.query_id or "") or ([v.team] if v.team else [])
        o = [x for x in o if x]
        return ", ".join(o) if o else f"{HUMAN} (unassigned owner)"

    steps: list[PlanStep] = []
    for i, k in enumerate(ordered_keys, 1):
        v = by_key[k]
        fx = fixes.get(v.asset_urn or "")
        if v.is_unknown:
            action = ("manual review — could not be assessed automatically "
                      f"({v.usage}); determine impact by hand")
        elif fx:
            action = f"apply generated fix: {fx.path}"
        else:
            action = "manual review — no mechanical fix generated"

        # B16: what the static verifier observed for THIS consumer, derived only.
        verified = "not verified"
        if verification is not None:
            if v.is_unknown:
                verified = "unassessed — verification cannot clear it"
            elif v.asset_name in set(verification.manual_work_remaining):
                verified = "still impacted after fix — manual review"
            else:
                moved = next((t for t in verification.transitions
                              if t.query_id == v.query_id), None)
                if moved is not None and moved.regressed:
                    verified = f"REGRESSED after fix ({moved.before} -> {moved.after})"
                elif moved is not None and moved.improved:
                    verified = f"verified-clean after fix ({moved.before} -> {moved.after})"
                else:
                    verified = "unchanged after fix — manual review"
        steps.append(PlanStep(
            order=i, key=k, asset_name=v.asset_name or v.query_id, asset_type=v.asset_type or "query",
            verdict=v.verdict.value, owner=owner_of(v), action=action, parser_confidence=v.confidence,
            verified=verified,
        ))

    # distinct owners across all steps (real ones only)
    teams: list[str] = []
    for s in steps:
        if not s.owner.startswith("⟨"):
            for o in s.owner.split(", "):
                if o and o not in teams:
                    teams.append(o)

    tests = [f"{s.asset_name} ({s.verdict})" for s in steps]

    # rollback references the generated PR / fix explicitly
    rollback: list[str] = []
    if change.op is Op.RENAME:
        rollback.append(f"Revert the schema change: rename `{change.new_name}` back to `{change.column}` on `{change.dataset}`.")
    else:
        rollback.append(f"Revert the schema change: re-add column `{change.column}` to `{change.dataset}`.")
    if fixes:
        for fx in fixes.values():
            rollback.append(f"Close the generated migration PR and revert `{fx.path}` to its pre-change version.")
    else:
        rollback.append("Close the generated migration PR (no auto-fix was applied; revert any manual edits).")
    rollback.append("Re-run Blast Radius Autopilot to confirm the catalog assessment clears.")

    risk = impact_result.risk()
    cov = impact_result.coverage()
    notes = [
        "This plan lists only facts derived from the impact analysis.",
        "Effort, timeline, and deployment window are left for a human to decide — not computed.",
        "The only confidence shown is the per-step column-analysis (parser) confidence.",
        f"Coverage: {cov['line']} consumer(s).",
    ]
    if impact_result.review_required():
        notes.append(
            f"REVIEW REQUIRED: {cov['unassessed']} consumer(s) could not be assessed and are "
            f"listed as manual-review steps. They are UNKNOWN, not safe; the risk level covers "
            f"only the {cov['analysed']} analysed consumer(s)."
        )
    if impact_result.ambiguous:
        notes.append(f"{len(impact_result.ambiguous)} low-confidence reference(s) were surfaced but not counted — verify manually.")
    if verification is not None:
        notes.append(
            f"Static verification: {verification.status} — breaks "
            f"{verification.before.get('breaks', 0)} -> {verification.after.get('breaks', 0)}, "
            f"coverage {verification.coverage_after.get('line', 'n/a')}."
        )
        notes.append(
            "Verification is STATIC: the patch was applied in an isolated copy, the patched SQL "
            "re-parsed, and impact recomputed. No queries were executed and no data was read."
        )
        if verification.status != "PASS":
            notes.append(
                "Verification did not PASS, so no step here may be applied without human approval."
            )

    return MigrationPlan(
        change=change.describe(),
        risk_level=str(risk["level_qualifier"]),
        risk_score=int(risk["score"]),
        ordered_steps=steps,
        teams_to_involve=teams,
        tests=tests,
        rollback=rollback,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Convenience: derive owners/plan straight from a report (used by CLI + HTML)
# --------------------------------------------------------------------------- #
def owners_from_report(report: ImpactReport) -> dict:
    return {(v.asset_urn or v.query_id): ([v.team] if v.team else []) for v in report.verdicts}


def plan_from_report(report: ImpactReport, fixes=None, lineage: dict | None = None,
                     verification=None) -> MigrationPlan:
    return build_plan(report.change, report, lineage or {}, owners_from_report(report),
                      fixes or [], verification=verification)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_plan_md(plan: MigrationPlan) -> str:
    lines: list[str] = []
    lines.append(f"# Migration Plan — {plan.change}")
    lines.append("")
    lines.append(f"**Change risk (derived):** {plan.risk_level} ({plan.risk_score}/100)")
    lines.append("")
    lines.append("## Ordered steps (deepest upstream first → consumers → BI last)")
    lines.append("")
    if plan.ordered_steps:
        for s in plan.ordered_steps:
            lines.append(f"{s.order}. **[{s.verdict}] {s.asset_name}** _({s.asset_type})_")
            lines.append(f"    - owner: {s.owner}")
            lines.append(f"    - action: {s.action}")
            lines.append(f"    - column-analysis (parser) confidence: {s.parser_confidence}")
            if s.verified != "not verified":
                lines.append(f"    - static verification: {s.verified}")
    else:
        lines.append("_No confident breaking/degrading consumers — no ordered steps required._")
    lines.append("")
    lines.append("## Teams to involve")
    lines.append("")
    lines.append(", ".join(plan.teams_to_involve) if plan.teams_to_involve else f"{HUMAN} (no owners on record)")
    lines.append("")
    lines.append("## Verify after the change (impacted downstreams)")
    lines.append("")
    for t in plan.tests:
        lines.append(f"- {t}")
    if not plan.tests:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Rollback")
    lines.append("")
    for r in plan.rollback:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Left for a human to decide (not computed)")
    lines.append("")
    lines.append(f"- Effort: {plan.effort}")
    lines.append(f"- Timeline: {plan.timeline}")
    lines.append(f"- Deployment window: {plan.deploy_window}")
    lines.append("")
    lines.append("---")
    for n in plan.notes:
        lines.append(f"_{n}_")
    return "\n".join(lines) + "\n"


def phrase_with_llm(plan: MigrationPlan) -> str:
    """Optionally reword the derived plan for readability WITHOUT adding any facts,
    numbers, dates, or estimates. Gated on ANTHROPIC_API_KEY; with no key (or on any
    error) it returns the deterministic plan unchanged — same pattern as the agent
    narrative. The structured, derived plan is the guardrail on the prose."""
    base = render_plan_md(plan)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return base
    try:
        import anthropic  # noqa: F401

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1500,
            system=(
                "Reword the following migration plan for readability ONLY. Do not add, remove, or "
                "change any fact, number, name, ordering, owner, or step. Never invent effort, "
                "hours, days, dates, deployment windows, or success percentages. Keep every "
                "'⟨human to decide⟩' placeholder verbatim. Output Markdown only."
            ),
            messages=[{"role": "user", "content": base}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        return text or base
    except Exception:  # noqa: BLE001 — any failure falls back to the deterministic plan
        return base
