"""B11 — self-contained visual Blast Radius report.

One standalone HTML file (no external assets, no network): a left-to-right lineage
graph with red/amber/green nodes (breaks/degrades/safe), a change-risk scorecard,
per-consumer detail with owning teams, and the generated migration diff.

Colour = status, not series: critical/warning/good from the data-viz status palette,
always paired with a glyph + text label (never colour alone), and theme-aware
(light/dark) so it reads in either surface.
"""

from __future__ import annotations

import html

from .assessment import AssessmentDoc, build_assessment
from .schema import ImpactReport, Verdict

# Status palette (fixed, never themed) + glyph + label — colour is never alone.
_STATUS = {
    Verdict.BREAKS: {"color": "#d03b3b", "glyph": "✕", "label": "BREAKS"},
    Verdict.DEGRADES: {"color": "#fab219", "glyph": "!", "label": "DEGRADES"},
    Verdict.SAFE: {"color": "#0ca30c", "glyph": "✓", "label": "SAFE"},
    Verdict.UNKNOWN: {"color": "#898781", "glyph": "?", "label": "UNKNOWN"},
}
_RISK_COLOR = {"CRITICAL": "#d03b3b", "HIGH": "#ec835a", "MODERATE": "#fab219", "LOW": "#0ca30c"}


def _e(s: object) -> str:
    return html.escape(str(s), quote=True)


def _node_label(v) -> tuple[str, str]:
    if v.asset_name:
        return v.asset_name, (v.asset_type or "").replace("_", " ")
    return v.query_id, (v.team or "ad-hoc")


def _graph_svg(report: ImpactReport) -> str:
    """Left-to-right DAG: target dataset -> impacted consumers, coloured by verdict.
    SAFE and low-confidence consumers are aggregated into one node each to stay
    readable."""
    rows: list[dict] = []
    for v in report.breaks:
        name, sub = _node_label(v)
        rows.append({"name": name, "sub": sub, "team": v.team, "runs": v.runs, "v": Verdict.BREAKS})
    for v in report.degrades:
        name, sub = _node_label(v)
        rows.append({"name": name, "sub": sub, "team": v.team, "runs": v.runs, "v": Verdict.DEGRADES})
    if report.unknown:
        rows.append({"name": f"{len(report.unknown)} unassessed consumer(s)",
                     "sub": "could not be analysed — review",
                     "team": None, "runs": sum(x.runs for x in report.unknown), "v": Verdict.UNKNOWN})
    if report.safe:
        rows.append({"name": f"{len(report.safe)} safe consumer(s)", "sub": "unaffected",
                     "team": None, "runs": sum(x.runs for x in report.safe), "v": Verdict.SAFE})

    n = max(len(rows), 1)
    row_h, top, pad = 62, 40, 24
    height = max(top + n * row_h + pad, 220)
    width, tx, tw, th = 940, 40, 250, 74
    ty = height / 2 - th / 2
    nx, nw, nh = 560, 340, 46

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="Blast radius lineage graph" style="max-width:100%;height:auto">'
    ]
    # target node
    tgt = _e(report.target_urn.split(",")[-2].split(".")[-1] if report.target_urn else report.change.dataset)
    col = _e(report.change.column)
    parts.append(
        f'<g><rect x="{tx}" y="{ty:.0f}" width="{tw}" height="{th}" rx="10" '
        f'fill="var(--surface-2)" stroke="var(--border-strong)" stroke-width="1.5"/>'
        f'<text x="{tx + 16}" y="{ty + 28:.0f}" class="n-title">{tgt}</text>'
        f'<text x="{tx + 16}" y="{ty + 50:.0f}" class="n-sub">changing column: {col}</text></g>'
    )
    # consumer nodes + edges
    for i, r in enumerate(rows):
        cy = top + i * row_h
        s = _STATUS[r["v"]]
        c = s["color"]
        y_mid_src = ty + th / 2
        y_mid_dst = cy + nh / 2
        # edge (colour = destination verdict), curved
        mx = (tx + tw + nx) / 2
        parts.append(
            f'<path d="M{tx + tw},{y_mid_src:.0f} C{mx:.0f},{y_mid_src:.0f} {mx:.0f},{y_mid_dst:.0f} '
            f'{nx},{y_mid_dst:.0f}" fill="none" stroke="{c}" stroke-width="2" opacity="0.75"/>'
        )
        runs = f'{r["runs"]} runs' + (f' · {_e(r["team"])}' if r["team"] else "")
        parts.append(
            f'<g><rect x="{nx}" y="{cy}" width="{nw}" height="{nh}" rx="9" fill="var(--surface-2)" '
            f'stroke="{c}" stroke-width="1.5"/>'
            f'<rect x="{nx}" y="{cy}" width="6" height="{nh}" rx="3" fill="{c}"/>'
            f'<circle cx="{nx + 26}" cy="{cy + nh/2:.0f}" r="11" fill="{c}"/>'
            f'<text x="{nx + 26}" y="{cy + nh/2 + 4:.0f}" text-anchor="middle" class="badge">{s["glyph"]}</text>'
            f'<text x="{nx + 46}" y="{cy + 20}" class="n-title">{_e(r["name"])}</text>'
            f'<text x="{nx + 46}" y="{cy + 38}" class="n-sub">{_e(s["label"])} · {_e(r["sub"])} · {runs}</text>'
            f"</g>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _legend() -> str:
    items = []
    for v, s in _STATUS.items():
        items.append(
            f'<span class="lg"><span class="dot" style="background:{s["color"]}">{s["glyph"]}</span>'
            f'{_e(s["label"])}</span>'
        )
    return '<div class="legend">' + "".join(items) + "</div>"


_V_STATUS = {
    "PASS": {"color": "#0ca30c", "glyph": "✓", "label": "PASS"},
    "REVIEW_REQUIRED": {"color": "#fab219", "glyph": "!", "label": "REVIEW REQUIRED"},
    "FAIL": {"color": "#d03b3b", "glyph": "✕", "label": "FAIL"},
}


_V_METRICS = [("breaks", "Breaks"), ("degrades", "Degrades"), ("unknown", "Unassessed"),
              ("ambiguous", "Ambiguous")]


def _verification_banner(v) -> str:
    """B17.7 — the verdict, ABOVE the fold.

    The verdict used to sit below the blast radius, two lineage graphs and two plan
    sections down, so a screenshot of the report showed the problem and not the
    answer. This banner is the first thing under the header: one badge (not two), the
    residual-impact counters that decided it, and the limitation next to the verdict
    rather than a page away from it.
    """
    if v is None:
        return ""
    st = _V_STATUS.get(v.status, {"color": "#898781", "glyph": "?", "label": v.status})
    cells = []
    for key, label in _V_METRICS:
        before, after = v.before.get(key, 0), v.after.get(key, 0)
        cls = "vg" if after == 0 else "vb"
        cells.append(
            f"<div class='vm'><div class='vm-l'>{_e(label)}</div>"
            f"<div class='vm-v'><span class='vm-b'>{before}</span> &rarr; "
            f"<span class='{cls}'>{after}</span></div></div>"
        )
    cells.append(
        f"<div class='vm'><div class='vm-l'>Coverage</div>"
        f"<div class='vm-v'>{_e(str(v.coverage_after.get('line', 'n/a')))}</div></div>"
    )
    gaps = []
    if not v.target_resolved:
        gaps.append(f"The change did not resolve: {_e(v.target_problem)}")
    elif not v.schema_known:
        gaps.append(f"The target's schema is unknown: {_e(v.target_problem)}")
    if v.unmapped_files:
        gaps.append(f"{len(v.unmapped_files)} patched file(s) could not be mapped to a catalog "
                    f"consumer — their impact was not recomputed.")
    if v.deleted_files:
        gaps.append("The diff DELETES " + ", ".join(f"<code>{_e(f)}</code>" for f in v.deleted_files)
                    + " — a vanished consumer is not an unaffected one.")
    if v.unresolved_renames:
        gaps.append("The diff MOVES " + ", ".join(
            f"<code>{_e(o)}</code> &rarr; <code>{_e(n)}</code>" for o, n in v.unresolved_renames)
            + " to a path that could not be re-analysed.")
    gap = "".join(f"<div class='vgap'>{g}</div>" for g in gaps)
    return f"""<div class="vbanner" style="--vc:{st['color']}">
  <div class="vhead">STATIC MIGRATION CHECK: <span class="vverdict">{_e(st['label'])}</span></div>
  <div class="vmetrics">{''.join(cells)}</div>
  {gap}
  <div class="vnote">No queries were executed. No warehouse was contacted. No data was read.</div>
</div>
"""


def _verification_html(v) -> str:
    """B16 verification section: verdict badge, before/after deltas, transitions.

    Every string here is derived from the VerificationResult. The scope disclaimer is
    mandatory — this is static analysis, and the report must never imply otherwise.
    """
    if v is None:
        return ""
    from .verify import _REASON_TEXT

    st = _V_STATUS.get(v.status, {"color": "#898781", "glyph": "?", "label": v.status})
    d = v.deltas()

    rows = []
    for key, label in [("breaks", "🔴 Breaks"), ("degrades", "🟡 Degrades"),
                       ("safe", "🟢 Safe"), ("unknown", "⚪ Unassessed"),
                       ("ambiguous", "◐ Ambiguous")]:
        before, after = v.before.get(key, 0), v.after.get(key, 0)
        delta = d.get(key, 0)
        cls = "good" if (key in ("breaks", "degrades", "unknown", "ambiguous") and delta < 0) else (
            "bad" if (key in ("breaks", "degrades", "unknown", "ambiguous") and delta > 0) else "")
        rows.append(
            f"<tr><td>{_e(label)}</td><td class='num'>{before}</td>"
            f"<td class='num'>{after}</td>"
            f"<td class='num {cls}'>{delta:+d}</td></tr>"
        )
    rows.append(
        f"<tr><td>Coverage</td><td class='num'>{_e(v.coverage_before.get('line', 'n/a'))}</td>"
        f"<td class='num'>{_e(v.coverage_after.get('line', 'n/a'))}</td><td class='num'>—</td></tr>"
    )

    trans = ""
    if v.transitions:
        items = []
        for t in v.transitions:
            tag = (" <strong style='color:#d03b3b'>REGRESSED</strong>" if t.regressed
                   else " <span class='muted'>improved</span>" if t.improved else "")
            items.append(f"<li><strong>{_e(t.consumer)}</strong>: "
                         f"{_e(t.before)} → {_e(t.after)}{tag}</li>")
        trans = f"<p><strong>Consumer transitions</strong></p><ul>{''.join(items)}</ul>"

    why = "".join(f"<li><code>{_e(r)}</code> — {_e(_REASON_TEXT.get(r, r))}</li>"
                  for r in v.reasons)

    extra = ""
    if v.parse_errors:
        extra += ("<p><strong>Parse errors in patched SQL</strong></p><ul>"
                  + "".join(f"<li><code>{_e(e)}</code></li>" for e in v.parse_errors) + "</ul>")
    if v.scope_violations:
        extra += ("<p><strong>Scope violations</strong></p><ul>"
                  + "".join(f"<li>{_e(x)}</li>" for x in v.scope_violations) + "</ul>")
    if v.residual_references:
        extra += ("<p><strong>Fix incomplete — column still referenced after patching</strong></p><ul>"
                  + "".join(f"<li><code>{_e(x)}</code></li>" for x in v.residual_references) + "</ul>")
    if v.unknown_consumers:
        extra += ("<p><strong>Unassessed consumers</strong> (not safe — manual review)</p><ul>"
                  + "".join(f"<li>{_e(x)}</li>" for x in v.unknown_consumers) + "</ul>")
    if v.ambiguous_consumers:
        extra += ("<p><strong>Ambiguous references</strong> (parsed, but not attributable to a "
                  "source table — not safe, and not a proven break)</p><ul>"
                  + "".join(f"<li>{_e(x)}</li>" for x in v.ambiguous_consumers) + "</ul>")
    if not v.target_resolved:
        extra += (f"<p><strong>The change did not resolve</strong></p>"
                  f"<p class='muted'>{_e(v.target_problem)}</p>")
    elif not v.schema_known:
        extra += (f"<p><strong>The target dataset's schema is unknown</strong></p>"
                  f"<p class='muted'>{_e(v.target_problem)}</p>")
    if v.unmapped_files:
        extra += ("<p><strong>Patched files whose impact could not be recomputed</strong> — these "
                  "SQL files could not be mapped to a catalog consumer, so the recomputed numbers "
                  "above do not cover the whole diff</p><ul>"
                  + "".join(f"<li><code>{_e(x)}</code></li>" for x in v.unmapped_files) + "</ul>")
    if v.deleted_files:
        extra += ("<p><strong>SQL files DELETED by the diff</strong> — a consumer whose defining "
                  "SQL was removed is not a consumer that became safe; its impact simply can no "
                  "longer be recomputed</p><ul>"
                  + "".join(f"<li><code>{_e(x)}</code></li>" for x in v.deleted_files) + "</ul>")
    if v.renamed_files:
        items = []
        for old, new in v.renamed_files:
            tag = ("recomputed at the new path" if (old, new) not in v.unresolved_renames
                   else "<strong>not re-analysable at the new path</strong>")
            items.append(f"<li><code>{_e(old)}</code> &rarr; <code>{_e(new)}</code> — {tag}</li>")
        extra += "<p><strong>SQL files MOVED by the diff</strong></p><ul>" + "".join(items) + "</ul>"
    if v.file_query_map:
        extra += ("<p><strong>Patched files that WERE recomputed</strong></p><ul>"
                  + "".join(f"<li><code>{_e(rel)}</code> &rarr; consumer query "
                            f"<code>{_e(qid)}</code></li>"
                            for rel, qid in sorted(v.file_query_map.items())) + "</ul>")
    if v.manual_work_remaining:
        extra += ("<p><strong>Still needs manual work</strong> (no mechanical fix possible)</p><ul>"
                  + "".join(f"<li>{_e(x)}</li>" for x in v.manual_work_remaining) + "</ul>")

    files = ", ".join(f"<code>{_e(f)}</code>" for f in v.files_patched) or "—"
    # ONE badge. The card used to print the pill and then a summary line that also
    # began with the status, which rendered as "PASS PASS".
    detail = _e(v.summary_line().split("—", 1)[-1].strip())

    return f"""<h2>Verification — proof-carrying migration</h2>
<div class="card">
  <p><span class="pill" style="--pc:{st['color']}">{st['glyph']} {_e(st['label'])}</span>
     <span class="muted">{detail}</span></p>
  <div style="overflow-x:auto"><table>
    <thead><tr><th>Metric</th><th class='num'>Before</th><th class='num'>After</th><th class='num'>&Delta;</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
  {trans}
  <p><strong>Why this verdict</strong></p><ul>{why}</ul>
  {extra}
  <p class="muted">Files patched in isolation: {files}</p>
  <p class="muted"><strong>Scope of this verification.</strong> The patch was applied in an
  isolated copy of the repository, the patched SQL was re-parsed, and column-level impact was
  recomputed with the same analyzer. <strong>No queries were executed, no warehouse was
  contacted, and no data was read.</strong> This is static evidence about the SQL, not about
  runtime behaviour or results.</p>
  <p class="muted">Verified at {_e(v.verified_at)} · method: {_e(v.method)}</p>
</div>
"""


def _tiles(report: ImpactReport) -> str:
    c = report.counts()
    risk = report.risk()
    rc = _RISK_COLOR.get(risk["level"], "#898781")
    cov = report.coverage()
    tiles = [
        ("Change risk", f'{risk["score"]}<span class="unit">/100</span>',
         str(risk["level_qualifier"]), rc, risk["score"]),
        ("Breaks", str(c["breaks"]), "consumers error / lose data", _STATUS[Verdict.BREAKS]["color"], None),
        ("Degrades", str(c["degrades"]), "runs, output changes", _STATUS[Verdict.DEGRADES]["color"], None),
        ("Safe", str(c["safe"]), "proven unaffected", _STATUS[Verdict.SAFE]["color"], None),
        ("Unassessed", str(c["unknown"]),
         "no SQL / unparseable — not safe", _STATUS[Verdict.UNKNOWN]["color"], None),
        ("Coverage", str(cov["line"]),
         "consumers we could analyse", "var(--series-1)", None),
        ("Teams impacted", str(c["teams"]), ", ".join(report.teams_impacted()) or "—", "var(--series-1)", None),
        ("Impacted runs", str(c["runs_impacted"]), "query executions in history", "var(--series-1)", None),
    ]
    out = ['<div class="tiles">']
    for title, value, sub, color, meter in tiles:
        meter_html = ""
        if meter is not None:
            meter_html = (
                f'<div class="meter"><div class="meter-fill" style="width:{min(meter,100)}%;background:{color}">'
                f"</div></div>"
            )
        out.append(
            f'<div class="tile"><div class="t-title">{_e(title)}</div>'
            f'<div class="t-value" style="color:{color}">{value}</div>'
            f'{meter_html}<div class="t-sub">{_e(sub)}</div></div>'
        )
    out.append("</div>")
    return "".join(out)


def _consumer_rows(report: ImpactReport) -> str:
    rows = []
    for v in report.impacted():
        s = _STATUS[v.verdict]
        name, sub = _node_label(v)
        clauses = ", ".join(v.clauses) if v.clauses else "—"
        rows.append(
            f"<tr>"
            f'<td><span class="pill" style="--pc:{s["color"]}">{s["glyph"]} {_e(s["label"])}</span></td>'
            f"<td><strong>{_e(name)}</strong><br><span class='muted'>{_e(sub)}</span></td>"
            f"<td>{_e(v.team or '—')}</td>"
            f"<td><code>{_e(v.usage)}</code> <span class='muted'>({_e(clauses)})</span></td>"
            f"<td class='num'>{v.runs}</td>"
            f"<td>{_e(v.reason)}</td>"
            f"</tr>"
        )
    for v in report.unknown:
        s = _STATUS[Verdict.UNKNOWN]
        name, sub = _node_label(v)
        rows.append(
            f"<tr class='amb'>"
            f'<td><span class="pill" style="--pc:{s["color"]}">{s["glyph"]} {_e(s["label"])}</span></td>'
            f"<td><strong>{_e(name)}</strong><br><span class='muted'>{_e(sub)}</span></td>"
            f"<td>{_e(v.team or '—')}</td>"
            f"<td><code>{_e(v.usage)}</code></td>"
            f"<td class='num'>{v.runs}</td>"
            f"<td>{_e(v.reason)}</td>"
            f"</tr>"
        )
    if report.ambiguous:
        for v in report.ambiguous:
            rows.append(
                f"<tr class='amb'>"
                f'<td><span class="pill" style="--pc:#898781">? LOW-CONF</span></td>'
                f"<td><strong>{_e(v.query_id)}</strong></td>"
                f"<td>{_e(v.team or '—')}</td>"
                f"<td><code>{_e(v.usage)}</code></td>"
                f"<td class='num'>{v.runs}</td>"
                f"<td>{_e(v.reason)} <em>(surfaced, not counted)</em></td>"
                f"</tr>"
            )
    return "".join(rows)


def _diff_html(diff: str) -> str:
    out = []
    for line in diff.splitlines():
        cls = ""
        if line.startswith("+") and not line.startswith("+++"):
            cls = "add"
        elif line.startswith("-") and not line.startswith("---"):
            cls = "del"
        elif line.startswith("@@"):
            cls = "hunk"
        out.append(f'<span class="{cls}">{_e(line)}</span>')
    return "\n".join(out)


def _fixes_html(fixes: list) -> str:
    if not fixes:
        return "<p class='muted'>No dbt-model fixes auto-generated — impacted consumers are BI/queries.</p>"
    blocks = []
    for fx in fixes:
        state = "auto-generated ✓" if fx.applicable and fx.changed else "needs manual work"
        review = ""
        if fx.needs_review:
            review = "<ul class='review'>" + "".join(f"<li>⚠️ {_e(r)}</li>" for r in fx.needs_review) + "</ul>"
        diff = f"<pre class='diff'>{_diff_html(fx.diff)}</pre>" if fx.diff else ""
        blocks.append(
            f"<div class='fix'><div class='fix-head'><strong>{_e(fx.asset_name)}</strong> "
            f"<code>{_e(fx.path)}</code> <span class='tag'>{_e(state)}</span> "
            f"<span class='muted'>({_e(fx.method)})</span></div>{review}{diff}</div>"
        )
    return "".join(blocks)


def _plan_html(plan) -> str:
    steps = []
    for s in plan.ordered_steps:
        color = _STATUS[Verdict(s.verdict)]["color"]
        steps.append(
            f"<li><span class='pill' style='--pc:{color}'>{_e(s.verdict)}</span> "
            f"<strong>{_e(s.asset_name)}</strong> <span class='muted'>({_e(s.asset_type)})</span>"
            f"<div class='muted' style='margin:2px 0 0 2px'>owner: {_e(s.owner)} · action: {_e(s.action)} · "
            f"parser confidence: {_e(s.parser_confidence)}"
            + (f" · <strong>static verification:</strong> {_e(s.verified)}"
               if s.verified != "not verified" else "")
            + "</div></li>"
        )
    steps_html = "<ol class='plan'>" + "".join(steps) + "</ol>" if steps else "<p class='muted'>No ordered steps required.</p>"
    teams = ", ".join(_e(t) for t in plan.teams_to_involve) or "⟨human to decide⟩"
    tests = "".join(f"<li>{_e(t)}</li>" for t in plan.tests) or "<li>(none)</li>"
    rollback = "".join(f"<li>{_e(r)}</li>" for r in plan.rollback)
    return (
        f"{steps_html}"
        f"<p><strong>Teams to involve:</strong> {teams}</p>"
        f"<p><strong>Verify after the change:</strong></p><ul>{tests}</ul>"
        f"<p><strong>Rollback:</strong></p><ul>{rollback}</ul>"
        f"<p class='muted'><strong>Left for a human to decide (not computed):</strong> "
        f"effort {_e(plan.effort)} · timeline {_e(plan.timeline)} · deployment window {_e(plan.deploy_window)}</p>"
    )


def _writeback_html(wb) -> str:
    """B17.4 — the real write-back counters, straight from the result object."""
    if wb is None:
        return ""
    c = wb.counts()
    rows = "".join(
        f"<tr><td>{_e(lbl)}</td><td class='num'>{c[key]}</td></tr>"
        for key, lbl in [("total", "Planned (total)"),
                         ("written_auto", "Written — automatic (verification PASSed)"),
                         ("written_human_approved", "Written — human-approved"),
                         ("queued_for_review", "Queued for review"), ("failed", "Failed"),
                         ("planned", "Not attempted (dry run)"), ("skipped", "Skipped")]
    )
    fails = ""
    if wb.failed:
        fails = ("<p><strong>Failed mutations</strong></p><ul>" + "".join(
            f"<li><code>{_e(f['tool'])}</code> on <code>{_e(f['target_urn'])}</code> — "
            f"{_e(f['error'])}</li>" for f in wb.failed) + "</ul>")
    mode = ("<span class='muted'>dry run — nothing was written</span>" if wb.dry_run
            else "<span class='muted'>live write-back</span>")
    # B19.6 — the authorising path, never left to inference.
    who = f"<p><strong>Applied by:</strong> {_e(wb.applied_by)}</p>"
    if wb.approver:
        who += (f"<p><strong>Approved by:</strong> <code>{_e(wb.approver)}</code> under "
                f"approval manifest <code>{_e(wb.manifest_id)}</code> — single-use, bound to "
                f"this change and this verdict.</p>")
    if wb.queued_for_review:
        who += (f"<p><strong>Queued because:</strong> <code>{_e(wb.queue_reason_line())}</code>"
                f" — a migration is written automatically only when static verification "
                f"returned PASS.</p>")
    if wb.manifest_path and not wb.approver:
        who += (f"<p class='muted'><strong>Approval route:</strong> a human may approve exactly "
                f"these queued mutations via <code>{_e(wb.manifest_path)}</code>.</p>")
    return f"""<h2>Catalog write-back</h2>
<div class="card">
  <p><strong>{_e(wb.summary_line())}</strong> &nbsp; {mode}</p>
  {who}
  <div style="overflow-x:auto"><table>
    <thead><tr><th>Outcome</th><th class='num'>Count</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  {fails}
</div>
"""


def render_html(report: ImpactReport, fixes: list | None = None, assessment: AssessmentDoc | None = None,
                plan=None, verification=None, writeback=None) -> str:
    fixes = fixes or []
    assessment = assessment or build_assessment(report, fixes, writeback=writeback)
    if plan is None:
        from .planner import plan_from_report

        plan = plan_from_report(report, fixes, verification=verification)
    c = report.counts()
    risk = report.risk()
    rc = _RISK_COLOR.get(risk["level"], "#898781")
    notes = ""
    if report.notes:
        notes = "<h2>Notes</h2><ul>" + "".join(f"<li>{_e(n)}</li>" for n in report.notes) + "</ul>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blast Radius — {_e(report.change.describe())}</title>
<style>
:root {{
  color-scheme: light;
  --plane:#f9f9f7; --surface-1:#fcfcfb; --surface-2:#ffffff;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --muted:#898781;
  --grid:#e1e0d9; --border:rgba(11,11,11,0.10); --border-strong:#c3c2b7;
  --series-1:#2a78d6;
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) {{
    color-scheme: dark;
    --plane:#0d0d0d; --surface-1:#1a1a19; --surface-2:#232320;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --border:rgba(255,255,255,0.10); --border-strong:#383835;
    --series-1:#3987e5;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --plane:#0d0d0d; --surface-1:#1a1a19; --surface-2:#232320;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --border:rgba(255,255,255,0.10); --border-strong:#383835;
  --series-1:#3987e5;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--plane); color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.5; }}
.wrap {{ max-width:1040px; margin:0 auto; padding:32px 24px 64px; }}
header .pitch {{ color:var(--text-secondary); font-size:15px; margin:2px 0 0; }}
h1 {{ font-size:26px; margin:0; letter-spacing:-0.01em; }}
h2 {{ font-size:18px; margin:32px 0 12px; }}
.change {{ display:inline-block; margin-top:14px; padding:8px 14px; border-radius:8px;
  background:var(--surface-2); border:1px solid var(--border); font-size:15px; }}
.change code {{ color:{rc}; font-weight:600; }}
.summary {{ margin:16px 0 0; padding:14px 16px; border-left:4px solid {rc};
  background:var(--surface-1); border-radius:0 8px 8px 0; }}
.card {{ background:var(--surface-1); border:1px solid var(--border); border-radius:12px;
  padding:20px; margin-top:20px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
.tile {{ background:var(--surface-2); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
.t-title {{ font-size:12px; text-transform:uppercase; letter-spacing:0.04em; color:var(--muted); }}
.t-value {{ font-size:30px; font-weight:700; margin:4px 0 2px; }}
.t-value .unit {{ font-size:14px; color:var(--muted); font-weight:500; }}
.t-sub {{ font-size:12px; color:var(--text-secondary); }}
.meter {{ height:6px; border-radius:3px; background:var(--grid); overflow:hidden; margin:6px 0; }}
.meter-fill {{ height:100%; border-radius:3px; }}
.legend {{ display:flex; gap:18px; flex-wrap:wrap; margin:6px 0 16px; font-size:13px; color:var(--text-secondary); }}
.lg {{ display:inline-flex; align-items:center; gap:7px; }}
.dot {{ width:18px; height:18px; border-radius:50%; color:#fff; font-size:11px; font-weight:700;
  display:inline-flex; align-items:center; justify-content:center; }}
svg text {{ font-family:system-ui,-apple-system,sans-serif; }}
.n-title {{ fill:var(--text-primary); font-size:14px; font-weight:600; }}
.n-sub {{ fill:var(--text-secondary); font-size:11.5px; }}
.badge {{ fill:#fff; font-size:12px; font-weight:700; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--grid); vertical-align:top; }}
th {{ font-size:11px; text-transform:uppercase; letter-spacing:0.04em; color:var(--muted); }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
tr.amb td {{ color:var(--text-secondary); }}
.muted {{ color:var(--muted); }}
.pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700;
  color:#fff; background:var(--pc); white-space:nowrap; }}
ol.plan {{ padding-left:22px; margin:0; }}
ol.plan li {{ margin:10px 0; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }}
.fix {{ margin-top:14px; }}
.fix-head {{ margin-bottom:6px; }}
.tag {{ background:var(--surface-2); border:1px solid var(--border); border-radius:6px; padding:1px 7px; font-size:12px; }}
.review {{ margin:6px 0; color:var(--text-secondary); font-size:13px; }}
pre.diff {{ background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:12px;
  overflow-x:auto; font-family:ui-monospace,Menlo,monospace; font-size:12.5px; line-height:1.55; }}
pre.diff span {{ display:block; }}
pre.diff .add {{ background:rgba(12,163,12,0.14); }}
pre.diff .del {{ background:rgba(208,59,59,0.14); }}
pre.diff .hunk {{ color:var(--muted); }}
footer {{ margin-top:36px; color:var(--muted); font-size:12.5px; }}
.toggle {{ float:right; cursor:pointer; background:var(--surface-2); border:1px solid var(--border);
  border-radius:8px; padding:6px 12px; font-size:13px; color:var(--text-primary); }}
/* B17.7 — the verdict, above the fold. */
.vbanner {{ margin-top:20px; padding:18px 20px; border-radius:12px; background:var(--surface-1);
  border:1px solid var(--border); border-left:6px solid var(--vc); }}
.vhead {{ font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted);
  font-weight:700; }}
.vverdict {{ font-size:28px; letter-spacing:-0.01em; color:var(--vc); display:block; margin-top:2px; }}
.vmetrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(118px,1fr)); gap:10px;
  margin-top:14px; }}
.vm {{ background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:9px 12px; }}
.vm-l {{ font-size:11px; text-transform:uppercase; letter-spacing:0.04em; color:var(--muted); }}
.vm-v {{ font-size:19px; font-weight:700; font-variant-numeric:tabular-nums; margin-top:2px; }}
.vm-b {{ color:var(--muted); font-weight:600; }}
.vg {{ color:#0ca30c; }}
.vb {{ color:#d03b3b; }}
.vgap {{ margin-top:12px; font-size:13px; color:#d03b3b; }}
.vnote {{ margin-top:12px; font-size:12.5px; color:var(--text-secondary); }}
</style>
</head>
<body>
<div class="wrap">
<button class="toggle" onclick="var r=document.documentElement;r.setAttribute('data-theme',r.getAttribute('data-theme')==='dark'?'light':'dark')">◐ theme</button>
<header>
  <h1>Blast Radius Autopilot</h1>
  <p class="pitch">DataHub's Impact Analysis shows you the blast radius; this defuses it.</p>
  <div class="change">Proposed change: <code>{_e(report.change.describe())}</code> &nbsp;·&nbsp; catalog <strong>{_e(report.catalog)}</strong></div>
  <div class="summary">{_e(assessment.summary)}</div>
</header>

{_verification_banner(verification)}
<div class="card">{_tiles(report)}</div>

<h2>Impacted lineage</h2>
{_legend()}
<div class="card">{_graph_svg(report)}</div>

<h2>Impacted consumers</h2>
<div class="card" style="overflow-x:auto">
<table>
<thead><tr><th>Impact</th><th>Consumer</th><th>Team</th><th>Uses column</th><th>Runs</th><th>Detail</th></tr></thead>
<tbody>{_consumer_rows(report)}</tbody>
</table>
</div>

<h2>Migration plan</h2>
<div class="card">{_fixes_html(fixes)}</div>

<h2>Migration plan — grounded step-by-step</h2>
<div class="card">{_plan_html(plan)}</div>

{_verification_html(verification)}

{_writeback_html(writeback)}

{notes}

<footer>{_e(assessment.title)} · Generated by Blast Radius Autopilot · public/synthetic data only.</footer>
</div>
</body>
</html>
"""
