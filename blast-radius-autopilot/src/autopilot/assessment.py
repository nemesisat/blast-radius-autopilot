"""Shared impact-assessment narrative — the durable memory written back to the
catalog and reused by every report (HTML, PR comment).

Deterministic by default (no LLM needed to run or test). If an ANTHROPIC_API_KEY
is present, `narrative_summary()` can be swapped for an LLM-authored paragraph;
the structured facts below are the guardrails on that prose, not a replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schema import ImpactReport


@dataclass
class AssessmentDoc:
    title: str
    summary: str
    markdown: str
    properties: dict[str, object] = field(default_factory=dict)


def _asset_label(v) -> str:
    if v.asset_name:
        kind = (v.asset_type or "asset").replace("_", " ")
        return f"{v.asset_name} ({kind})"
    team = f" · {v.team}" if v.team else ""
    return f"query {v.query_id}{team}"


def narrative_summary(report: ImpactReport) -> str:
    """One honest sentence. Never claims a clean bill of health when some consumers
    could not be assessed — an absence of findings over a partial corpus is not the
    same as an absence of impact."""
    c = report.counts()
    risk = report.risk()
    cov = report.coverage()
    # Caveat, appended to whichever branch we take. The two reasons for review are
    # named separately because they are different failures of knowledge: unassessed
    # means we could not read the consumer; ambiguous means we read it and could not
    # attribute the reference. Reporting one as the other would misdescribe the gap.
    parts: list[str] = []
    if cov["unassessed"]:
        parts.append(
            f"{cov['unassessed']} of {cov['total']} consumer(s) could NOT be assessed "
            f"(unparseable SQL or no SQL definition) and are reported UNKNOWN, not safe"
        )
    if c["ambiguous"]:
        parts.append(
            f"{c['ambiguous']} column reference(s) could not be confidently attributed to a "
            f"source table (unqualified column across joined tables) — not safe, and not "
            f"counted as a proven break"
        )
    caveat = f" {'; '.join(parts)} — REVIEW REQUIRED before applying." if parts else ""
    if c["breaks"] == 0 and c["degrades"] == 0:
        if cov["analysed"] == 0:
            # Nothing at all could be assessed. Quoting ANY risk level here would be
            # a number over an empty evidence set — the exact false comfort B15 exists
            # to prevent. Say plainly that we know nothing.
            return (
                f"UNABLE TO ASSESS {report.change.describe()}: none of the "
                f"{cov['total']} known consumer(s) could be analysed (unparseable SQL or "
                f"no SQL definition). No risk level is reported because there is no "
                f"evidence to base one on. REVIEW REQUIRED."
            )
        head = (
            f"No impact found for {report.change.describe()} among the "
            f"{cov['analysed']} consumer(s) that could be analysed. "
            f"Risk among assessed: {risk['level']}."
            if report.review_required()
            else
            f"No confident impact found for {report.change.describe()} across "
            f"{c['queries_total']} queries. Risk: {risk['level']}."
        )
        return head + caveat
    teams = report.teams_impacted()
    team_str = f" across {len(teams)} team(s) ({', '.join(teams)})" if teams else ""
    return (
        f"{report.change.describe()} breaks {c['breaks']} and degrades {c['degrades']} "
        f"downstream consumer(s){team_str}, spanning {c['runs_impacted']} query runs in history. "
        f"Change risk: {risk['level_qualifier']} ({risk['score']}/100)." + caveat
    )


def approval_audit_properties(writeback) -> dict[str, object]:
    """The human-approval audit trail, as structured properties (B20.3).

    THE ONE SOURCE for these six fields. They are emitted into the catalog by
    `WriteBack._record_approval_audit()` and reported by every local surface from here,
    so the graph and the report cannot describe the same approval differently.

    Empty unless a human actually approved this run. That emptiness is the B19.6 split
    made visible in the catalog: an automatic write has no approver, so it must carry no
    approver field — not blank, not "system", not "auto". A reader of the properties can
    then tell a machine decision from a human consent by looking, not by inferring.

    `_approved_writes` / `_approved_failures` are OUTCOMES, so they are only meaningful
    once the mutations have been attempted; this is called after the apply loop, never
    before. Zero writes with non-zero failures is a legitimate and important record: a
    human approved, and it did not land.
    """
    if writeback is None or not (getattr(writeback, "approver", "") or "").strip():
        return {}
    c = writeback.counts()
    return {
        "blast_radius_approved_by": writeback.approver,
        "blast_radius_approved_at": writeback.approved_at,
        "blast_radius_manifest_id": writeback.manifest_id,
        "blast_radius_verification_status_at_approval":
            writeback.verification_status_at_approval,
        "blast_radius_approved_writes": c["written_human_approved"],
        "blast_radius_approved_failures": c["failed"],
    }


def build_assessment(report: ImpactReport, fixes: list | None = None, now: datetime | None = None,
                     verification=None, writeback=None) -> AssessmentDoc:
    fixes = fixes or []
    now = now or datetime.now(timezone.utc)
    c = report.counts()
    risk = report.risk()
    change = report.change

    title = f"Blast Radius Assessment — {change.describe()}"
    summary = narrative_summary(report)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("> _DataHub's Impact Analysis shows you the blast radius; Blast Radius Autopilot defuses it._")
    lines.append("")
    lines.append(f"**Summary.** {summary}")
    lines.append("")
    cov = report.coverage()
    lines.append(
        f"**Scorecard:** risk **{risk['level_qualifier']} ({risk['score']}/100)** · "
        f"🔴 {c['breaks']} breaks · 🟡 {c['degrades']} degrades · 🟢 {c['safe']} safe · "
        f"⚪ {c['unknown']} unassessed · {c['teams']} team(s) · {c['runs_impacted']} impacted runs"
    )
    lines.append("")
    lines.append(f"**Coverage:** {cov['line']} consumer(s).")
    if report.review_required():
        lines.append("")
        lines.append(
            f"> ⚠️ **REVIEW REQUIRED.** {cov['unassessed']} consumer(s) could not be assessed, "
            f"so this assessment is incomplete. Unassessed consumers are reported UNKNOWN — "
            f"**not** safe — and the risk level above describes only the "
            f"{cov['analysed']} consumer(s) that could be analysed."
        )
    lines.append("")

    def _table(title: str, rows: list, emoji: str) -> None:
        if not rows:
            return
        lines.append(f"## {emoji} {title} ({len(rows)})")
        lines.append("")
        lines.append("| Consumer | Team | Uses column | Runs | Detail |")
        lines.append("|---|---|---|---|---|")
        for v in rows:
            clauses = ", ".join(v.clauses) if v.clauses else "—"
            lines.append(
                f"| {_asset_label(v)} | {v.team or '—'} | `{v.usage}` ({clauses}) | {v.runs} | {v.reason} |"
            )
        lines.append("")

    _table("Breaks", report.breaks, "🔴")
    _table("Degrades", report.degrades, "🟡")

    if report.unknown:
        lines.append(f"## ⚪ Unassessed — could NOT be analysed ({len(report.unknown)})")
        lines.append("")
        lines.append(
            "_These consumers are **not** safe; nothing is known about them. Either their SQL "
            "could not be parsed or they expose no SQL definition at all. Each needs manual review._"
        )
        lines.append("")
        for v in report.unknown:
            lines.append(f"- {_asset_label(v)} — `{v.usage}`: {v.reason}")
        lines.append("")

    if report.ambiguous:
        lines.append(f"## ⚪ Low-confidence — surfaced, not counted ({len(report.ambiguous)})")
        lines.append("")
        lines.append("_Unqualified column that exists on more than one joined table; confirm manually._")
        lines.append("")
        for v in report.ambiguous:
            lines.append(f"- {_asset_label(v)} — `{v.usage}`: {v.reason}")
        lines.append("")

    lines.append("## 🛠 Migration plan")
    lines.append("")
    if fixes:
        for fx in fixes:
            status = "auto-generated" if fx.applicable and fx.changed else "needs manual work"
            lines.append(f"- **{fx.asset_name}** (`{fx.path}`) — {status} ({fx.method}).")
            for nr in fx.needs_review:
                lines.append(f"    - ⚠️ {nr}")
    else:
        lines.append("- No dbt-model fixes were auto-generated (impacted consumers are BI/queries).")
    lines.append("")

    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
        lines.append("")

    if verification is not None:
        vd = verification.deltas()
        lines.append("## 🔬 Migration verification (static)")
        lines.append("")
        lines.append(f"**Verdict: {verification.status}** — {verification.summary_line()}")
        lines.append("")
        lines.append("| Metric | Before | After | Δ |")
        lines.append("|---|---:|---:|---:|")
        for k, lbl in [("breaks", "Breaks"), ("degrades", "Degrades"),
                       ("safe", "Safe"), ("unknown", "Unassessed"),
                       ("ambiguous", "Ambiguous")]:
            lines.append(f"| {lbl} | {verification.before.get(k, 0)} | "
                         f"{verification.after.get(k, 0)} | {vd.get(k, 0):+d} |")
        lines.append(f"| Coverage | {verification.coverage_before.get('line', 'n/a')} | "
                     f"{verification.coverage_after.get('line', 'n/a')} | — |")
        lines.append("")
        if verification.transitions:
            lines.append("Consumer transitions:")
            lines.append("")
            for t in verification.transitions:
                lines.append(f"- {t.describe()}")
            lines.append("")
        lines.append("Reasons: " + ", ".join(f"`{r}`" for r in verification.reasons))
        lines.append("")
        lines.append(
            "> **Scope.** Static verification only: the generated patch was applied in an "
            "isolated copy of the repository, the patched SQL was re-parsed, and column-level "
            "impact was recomputed with the same analyzer. **No queries were executed, no "
            "warehouse was contacted, and no data was read.** This is evidence about the SQL, "
            "not about runtime behaviour or results."
        )
        lines.append("")
        if verification.unmapped_files:
            lines.append(
                "> ⚠️ **Incomplete recomputation.** These patched SQL files **could not be "
                "mapped** to a catalog consumer, so their impact was not recomputed: "
                + ", ".join(f"`{u}`" for u in verification.unmapped_files)
            )
            lines.append("")
        if verification.status != "PASS":
            lines.append(
                f"> ⚠️ Verification returned **{verification.status}**, so this change must not "
                f"be applied on the strength of the generated fix alone."
            )
            lines.append("")

    if writeback is not None:
        # The real counters, never the intent. A dry run reports 0 written, and the two
        # authorising paths are always both shown (B19.6) so a zero is as explicit as a
        # non-zero — nobody can mistake a human approval for an automatic write.
        wc = writeback.counts()
        lines.append("## 📤 Catalog write-back")
        lines.append("")
        lines.append(f"**{writeback.summary_line()}** "
                     + ("_(dry run — nothing was written)_" if writeback.dry_run else ""))
        lines.append("")
        lines.append("| Outcome | Count |")
        lines.append("|---|---:|")
        for key, lbl in [("total", "Planned (total)"),
                         ("written_auto", "Written — automatic (verification PASSed)"),
                         ("written_human_approved", "Written — human-approved"),
                         ("queued_for_review", "Queued for review"),
                         ("failed", "Failed"), ("planned", "Not attempted (dry run)"),
                         ("skipped", "Skipped")]:
            lines.append(f"| {lbl} | {wc[key]} |")
        lines.append("")
        lines.append(f"**Applied by:** {writeback.applied_by}")
        if writeback.approver:
            lines.append("")
            lines.append(f"**Approved by:** `{writeback.approver}` under approval manifest "
                         f"`{writeback.manifest_id}` (single-use, bound to this change and "
                         f"this verdict).")
            # B20.3 — say where the trail lives, and whether it got there. An audit that
            # only exists in this document is not an audit.
            audit = {
                "emitted": "recorded in the catalog",
                "failed": f"**NOT recorded in the catalog** — {writeback.audit_error}",
                "planned": "not recorded (dry run — nothing was written)",
            }.get(writeback.audit_status, "not recorded")
            lines.append("")
            lines.append(
                f"**Approval audit:** {audit} as `blast_radius_approved_by` / `_approved_at` / "
                f"`_manifest_id` / `_verification_status_at_approval` / `_approved_writes` "
                f"({len(writeback.written_human_approved)}) / `_approved_failures` "
                f"({len(writeback.failed)}) on the changed dataset."
            )
        if writeback.queued_for_review:
            lines.append("")
            lines.append(f"**Queued because:** `{writeback.queue_reason_line()}` — "
                         f"nothing was auto-applied. A migration is written automatically "
                         f"only when static verification returned PASS.")
        if writeback.manifest_path and not writeback.approver:
            lines.append("")
            lines.append(f"**Approval route:** a human may approve exactly these queued "
                         f"mutations via `{writeback.manifest_path}`.")
        lines.append("")
        if writeback.failed:
            lines.append("Failed mutations:")
            lines.append("")
            for f in writeback.failed:
                lines.append(f"- `{f['tool']}` on `{f['target_urn']}` — {f['error']}")
            lines.append("")

    lines.append(f"_Generated by Blast Radius Autopilot at {now.isoformat(timespec='seconds')}._")
    markdown = "\n".join(lines)

    properties = {
        "blast_radius_status": "pending-change",
        "blast_radius_risk": risk["level"],
        "blast_radius_score": risk["score"],
        "blast_radius_breaks": c["breaks"],
        "blast_radius_degrades": c["degrades"],
        "blast_radius_teams": c["teams"],
        # Coverage travels with the verdict into the catalog, so a reader of the
        # structured properties can never mistake a partial assessment for a full one.
        "blast_radius_unassessed": c["unknown"],
        # Unattributable references travel with the verdict too (B17.1): a reader of
        # the structured properties must be able to see WHY review was required.
        "blast_radius_ambiguous": c["ambiguous"],
        "blast_radius_coverage": cov["line"],
        "blast_radius_review_required": report.review_required(),
        "blast_radius_assessed_at": now.isoformat(timespec="seconds"),
    }
    if verification is not None:
        properties.update({
            "blast_radius_verification_status": verification.status,
            "blast_radius_verification_breaks_before": int(verification.before.get("breaks", 0)),
            "blast_radius_verification_breaks_after": int(verification.after.get("breaks", 0)),
            "blast_radius_verification_degrades_after": int(verification.after.get("degrades", 0)),
            "blast_radius_verification_ambiguous_after": int(verification.after.get("ambiguous", 0)),
            "blast_radius_verification_unmapped_files": len(verification.unmapped_files),
            "blast_radius_verification_coverage": verification.coverage_after.get("line", ""),
            "blast_radius_verified_at": verification.verified_at,
            "blast_radius_verification_method": verification.method,
        })
    if writeback is not None:
        wc = writeback.counts()
        properties.update({
            "blast_radius_writeback_planned": wc["total"],
            "blast_radius_writeback_written": wc["written"],
            # B19.6 — the catalog itself records which path applied the change, so a
            # reader of the properties can tell a machine decision from a human one.
            "blast_radius_writeback_written_auto": wc["written_auto"],
            "blast_radius_writeback_written_human_approved": wc["written_human_approved"],
            "blast_radius_writeback_applied_by": writeback.applied_by,
            "blast_radius_writeback_approver": writeback.approver or "",
            "blast_radius_approval_manifest_id": writeback.manifest_id or "",
            "blast_radius_writeback_queue_reason": writeback.queue_reason_line(),
            "blast_radius_writeback_queued": wc["queued_for_review"],
            "blast_radius_writeback_failed": wc["failed"],
            "blast_radius_writeback_dry_run": writeback.dry_run,
        })
        # B20.3 — and the approval audit itself, from its single source. On the auto
        # path this adds nothing at all, which is the point.
        properties.update(approval_audit_properties(writeback))
    return AssessmentDoc(title=title, summary=summary, markdown=markdown, properties=properties)
