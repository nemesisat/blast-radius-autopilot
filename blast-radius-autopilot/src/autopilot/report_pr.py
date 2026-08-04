"""B12 — CI-style pull-request comment.

`render_pr_comment()` produces the Markdown a CI bot would post on the migration
PR: a risk badge, the blast-radius summary, a collapsible impacted-consumers table,
the generated diff, and a reviewer checklist.

`open_local_pr()` makes it real without a remote or credentials: it branches a
local git repo, applies the generated fix, commits, and writes the comment to
`PR_COMMENT.md` at the repo root (a real PR would `gh pr comment` instead — noted,
not attempted, since that needs the human's GitHub auth).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .assessment import AssessmentDoc, build_assessment
from .schema import ImpactReport, Verdict

_BADGE = {"CRITICAL": "🚨 CRITICAL", "HIGH": "🟠 HIGH", "MODERATE": "🟡 MODERATE", "LOW": "🟢 LOW"}
_EMOJI = {Verdict.BREAKS: "🔴", Verdict.DEGRADES: "🟡", Verdict.SAFE: "🟢", Verdict.UNKNOWN: "⚪"}


def _consumer_line(v) -> str:
    name = v.asset_name or v.query_id
    kind = f" _{(v.asset_type or '').replace('_', ' ')}_" if v.asset_type else ""
    clauses = ", ".join(v.clauses) if v.clauses else "—"
    return f"| {_EMOJI[v.verdict]} {v.verdict.value} | {name}{kind} | {v.team or '—'} | `{v.usage}` ({clauses}) | {v.runs} |"


_V_BADGE = {"PASS": "✅ **PASS**", "REVIEW_REQUIRED": "⚠️ **REVIEW REQUIRED**",
            "FAIL": "❌ **FAIL**"}


def _verification_block(v) -> list[str]:
    """B16: verdict + delta table for the CI comment. Static evidence only."""
    if v is None:
        return []
    from .verify import _REASON_TEXT

    d = v.deltas()
    L: list[str] = []
    L.append(f"### 🔬 Migration verification (static) — {_V_BADGE.get(v.status, v.status)}")
    L.append("")
    if v.status == "PASS":
        L.append("The generated fix was applied in an isolated copy, the patched SQL re-parsed, "
                 "and impact recomputed: **no breaking or unassessed consumers remain**.")
    elif v.status == "FAIL":
        L.append("**Do not merge as-is.** The generated fix did not verify.")
    else:
        L.append("**Human review required.** The fix improved things but did not fully clear the "
                 "blast radius, or some consumers could not be assessed.")
    L.append("")
    L.append("| Metric | Before | After | Δ |")
    L.append("|---|---:|---:|---:|")
    for key, label in [("breaks", "🔴 Breaks"), ("degrades", "🟡 Degrades"),
                       ("safe", "🟢 Safe"), ("unknown", "⚪ Unassessed"),
                       ("ambiguous", "◐ Ambiguous")]:
        L.append(f"| {label} | {v.before.get(key, 0)} | {v.after.get(key, 0)} | {d.get(key, 0):+d} |")
    L.append(f"| Coverage | {v.coverage_before.get('line', 'n/a')} | "
             f"{v.coverage_after.get('line', 'n/a')} | — |")
    L.append("")
    if v.transitions:
        L.append("<details open><summary><b>Consumer transitions</b></summary>")
        L.append("")
        for t in v.transitions:
            tag = " **REGRESSED**" if t.regressed else ""
            L.append(f"- `{t.consumer}`: {t.before} → {t.after}{tag}")
        L.append("")
        L.append("</details>")
        L.append("")
    L.append("<details><summary><b>Why this verdict</b></summary>")
    L.append("")
    for r in v.reasons:
        L.append(f"- `{r}` — {_REASON_TEXT.get(r, r)}")
    L.append("")
    L.append("</details>")
    L.append("")
    if v.parse_errors:
        L.append("**Parse errors in patched SQL:**")
        for e in v.parse_errors:
            L.append(f"- `{e}`")
        L.append("")
    if v.scope_violations:
        L.append("**Scope violations:**")
        for x in v.scope_violations:
            L.append(f"- {x}")
        L.append("")
    if v.ambiguous_consumers:
        L.append("**Ambiguous references (parsed, not attributable — not safe):**")
        for x in v.ambiguous_consumers:
            L.append(f"- {x}")
        L.append("")
    if not v.target_resolved:
        L.append(f"**The change did not resolve.** {v.target_problem}")
        L.append("")
    elif not v.schema_known:
        L.append(f"**The target dataset's schema is unknown.** {v.target_problem}")
        L.append("")
    if v.unmapped_files:
        L.append("**Patched files whose impact could not be recomputed** — these SQL files "
                 "could not be mapped to a catalog consumer, so the recomputed numbers above "
                 "do not cover the whole diff:")
        for x in v.unmapped_files:
            L.append(f"- `{x}`")
        L.append("")
    if v.deleted_files:
        L.append("**SQL files DELETED by the diff** — a consumer whose defining SQL was removed "
                 "is not a consumer that became safe; its impact simply can no longer be "
                 "recomputed:")
        for x in v.deleted_files:
            L.append(f"- `{x}`")
        L.append("")
    if v.renamed_files:
        L.append("**SQL files MOVED by the diff:**")
        for old, new in v.renamed_files:
            tag = ("recomputed at the new path" if (old, new) not in v.unresolved_renames
                   else "**not re-analysable at the new path**")
            L.append(f"- `{old}` → `{new}` — {tag}")
        L.append("")
    if v.file_query_map:
        L.append("**Patched files that WERE recomputed:** "
                 + ", ".join(f"`{rel}` → `{qid}`" for rel, qid in sorted(v.file_query_map.items())))
        L.append("")
    L.append("> **Scope.** Static verification: the patch was applied in an isolated copy, the "
             "patched SQL re-parsed, and column-level impact recomputed. **No queries were "
             "executed, no warehouse was contacted, and no data was read.** This is evidence "
             "about the SQL, not about runtime behaviour or results.")
    L.append("")
    return L


def _writeback_block(wb) -> list[str]:
    """B17.4: the real write-back counters. A dry run reports 0 written."""
    if wb is None:
        return []
    c = wb.counts()
    L = ["### 📤 Catalog write-back"]
    L.append("")
    L.append(f"**{wb.summary_line()}**"
             + ("  _(dry run — nothing was written)_" if wb.dry_run else ""))
    L.append("")
    L.append("| Outcome | Count |")
    L.append("|---|---:|")
    for key, lbl in [("total", "Planned (total)"),
                     ("written_auto", "Written — automatic (verification PASSed)"),
                     ("written_human_approved", "Written — human-approved"),
                     ("queued_for_review", "Queued for review"), ("failed", "Failed"),
                     ("planned", "Not attempted (dry run)"), ("skipped", "Skipped")]:
        L.append(f"| {lbl} | {c[key]} |")
    L.append("")
    # B19.6 — say which path applied it. Never leave it to be inferred.
    L.append(f"**Applied by:** {wb.applied_by}")
    L.append("")
    if wb.approver:
        L.append(f"**Approved by:** `{wb.approver}` under approval manifest "
                 f"`{wb.manifest_id}` — single-use, bound to this change and this verdict.")
        L.append("")
    if wb.queued_for_review:
        L.append(f"**Queued because:** `{wb.queue_reason_line()}` — a migration is written "
                 f"automatically only when static verification returned PASS.")
        L.append("")
    if wb.manifest_path and not wb.approver:
        L.append(f"**Approval route:** a human may approve exactly these queued mutations via "
                 f"`{wb.manifest_path}`.")
        L.append("")
    if wb.failed:
        L.append("**Failed mutations:**")
        for f in wb.failed:
            L.append(f"- `{f['tool']}` on `{f['target_urn']}` — {f['error']}")
        L.append("")
    return L


def render_pr_comment(
    report: ImpactReport, fixes: list | None = None, assessment: AssessmentDoc | None = None,
    branch: str | None = None, verification=None, writeback=None,
) -> str:
    fixes = fixes or []
    assessment = assessment or build_assessment(report, fixes, writeback=writeback)
    c = report.counts()
    risk = report.risk()
    lines: list[str] = []

    cov = report.coverage()
    qualifier = " among assessed" if cov["unassessed"] else ""
    lines.append(f"## 🧨 Blast Radius Autopilot — risk **{_BADGE.get(risk['level'], risk['level'])}**{qualifier} ({risk['score']}/100)")
    lines.append("")
    lines.append(f"Assessing **`{report.change.describe()}`** against available query history and downstream SQL definitions in `{report.catalog}`.")
    lines.append("")
    lines.append(
        f"🔴 **{c['breaks']} break** · 🟡 **{c['degrades']} degrade** · 🟢 {c['safe']} safe · "
        f"⚪ **{c['unknown']} unassessed** · ◐ **{c['ambiguous']} ambiguous** · "
        f"👥 {c['teams']} team(s) · ▶️ {c['runs_impacted']} impacted runs in history"
    )
    lines.append("")
    lines.append(f"**Coverage:** {cov['line']} consumer(s).")
    lines.append("")
    if report.review_required():
        # Name the actual gap. "Could not be assessed" and "could not be attributed"
        # are different findings and must not be reported as each other.
        why: list[str] = []
        if cov["unassessed"]:
            why.append(f"{cov['unassessed']} consumer(s) could not be assessed (unparseable SQL "
                       f"or no SQL definition) and are reported UNKNOWN, **not** safe")
        if c["ambiguous"]:
            why.append(f"{c['ambiguous']} column reference(s) could not be confidently attributed "
                       f"to a source table, so they are **not** safe and **not** counted as "
                       f"proven breaks")
        lines.append("> ⚠️ **REVIEW REQUIRED — do not auto-apply.** " + "; ".join(why) + ".")
        lines.append("")
    lines.append(f"> {assessment.summary}")
    lines.append("")

    impacted = report.impacted()
    if impacted:
        lines.append("<details open><summary><b>Impacted consumers</b></summary>")
        lines.append("")
        lines.append("| Impact | Consumer | Team | Uses column | Runs |")
        lines.append("|---|---|---|---|---|")
        lines += [_consumer_line(v) for v in impacted]
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if report.unknown:
        lines.append("<details open><summary>⚪ <b>Unassessed — could NOT be analysed (not safe)</b></summary>")
        lines.append("")
        for v in report.unknown:
            lines.append(f"- **{v.asset_name or v.query_id}** — {v.reason}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if report.ambiguous:
        lines.append("<details><summary>⚪ Low-confidence (surfaced, not counted)</summary>")
        lines.append("")
        for v in report.ambiguous:
            lines.append(f"- `{v.query_id}` — {v.reason}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("### 🛠 Proposed migration")
    lines.append("")
    if fixes:
        for fx in fixes:
            state = "auto-generated ✅" if fx.applicable and fx.changed else "needs manual work ⚠️"
            lines.append(f"**`{fx.path}`** — {state} ({fx.method})")
            for nr in fx.needs_review:
                lines.append(f"> ⚠️ {nr}")
            if fx.diff:
                lines.append("")
                lines.append("```diff")
                lines.append(fx.diff.rstrip("\n"))
                lines.append("```")
            lines.append("")
    else:
        lines.append("_No dbt-model fix auto-generated — impacted consumers are BI dashboards/queries._")
        lines.append("")

    lines += _verification_block(verification)
    lines += _writeback_block(writeback)

    lines.append("### ✅ Reviewer checklist")
    lines.append("")
    lines.append(f"- [ ] Confirm the {c['breaks']} breaking consumer(s) are migrated or signed off")
    lines.append(f"- [ ] Notify impacted teams: {', '.join(report.teams_impacted()) or '—'}")
    if verification is not None and verification.status != "PASS":
        lines.append(f"- [ ] **Verification returned {verification.status}** — do not merge on the "
                     f"strength of the generated fix alone")
    if report.unknown:
        lines.append(f"- [ ] **Manually assess {len(report.unknown)} unassessed consumer(s)** — impact unknown, not safe")
    if report.ambiguous:
        lines.append(f"- [ ] Manually verify {len(report.ambiguous)} low-confidence reference(s)")
    if any(fx.needs_review for fx in fixes):
        lines.append("- [ ] Review filter/join logic flagged above (not auto-rewritten)")
    lines.append("")
    if branch:
        lines.append(f"_Auto-posted by Blast Radius Autopilot on branch `{branch}`. Public/synthetic data only._")
    else:
        lines.append("_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._")
    return "\n".join(lines) + "\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def open_local_pr(
    repo_root: str | Path, report: ImpactReport, fixes: list, assessment: AssessmentDoc | None = None,
    branch: str | None = None,
) -> dict:
    """Branch the local repo, apply the fix, commit, and write PR_COMMENT.md.

    Returns a dict describing the 'PR' (branch, applied files, comment path). Does
    NOT push or open a remote PR — that needs the human's GitHub auth (see
    PROGRESS 'Human-only remaining')."""
    repo = Path(repo_root)
    assessment = assessment or build_assessment(report, fixes)
    col = report.change.column
    branch = branch or f"blast-radius/{report.change.op.value}-{col}"
    if not (repo / ".git").exists():
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        # allow commit in CI/sandbox without global identity
        _git(repo, "-c", "user.email=autopilot@local", "-c", "user.name=Autopilot", "commit", "-q", "-m", "baseline")

    # fresh branch off current HEAD
    try:
        _git(repo, "checkout", "-q", "-B", branch)
    except subprocess.CalledProcessError:
        _git(repo, "checkout", "-q", branch)

    applied: list[str] = []
    for fx in fixes:
        if fx.applicable and fx.changed and fx.new_sql:
            target = repo / fx.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(fx.new_sql)
            applied.append(fx.path)

    comment = render_pr_comment(report, fixes, assessment, branch=branch)
    comment_path = repo / "PR_COMMENT.md"
    comment_path.write_text(comment)

    if applied:
        _git(repo, "add", "-A")
        _git(
            repo, "-c", "user.email=autopilot@local", "-c", "user.name=Autopilot",
            "commit", "-q", "-m", f"fix: {report.change.describe()} (auto-migration)\n\n{assessment.summary}",
        )
    commit = _git(repo, "rev-parse", "--short", "HEAD").strip() if (repo / ".git").exists() else ""
    return {"branch": branch, "applied": applied, "comment_path": str(comment_path), "commit": commit}
