"""B21 — the sweep ledger: markdown, HTML, and JSON.

Grouped by bucket, worst first, because a triage list whose good news comes first is a triage
list nobody finishes reading.

Every number rendered here comes off a `SweepResult` or a `SweepEntry`. This module computes
nothing — no averages, no estimates, no projections, no "time saved". If a figure is not in
the ledger data it does not appear on the page. The header duration is a real measured
wall-clock number, and the coverage line is a count of fully-assessed candidates rather than
an average of ratios (averaging coverage across candidates yields a number that describes
nothing).
"""

from __future__ import annotations

import html
from pathlib import Path

from .sweep import BUCKET_LABEL, BUCKET_ORDER, SweepEntry, SweepResult

_BUCKET_COLOR = {
    "landmine": "#d03b3b",
    "unassessed": "#898781",
    "needs_review": "#fab219",
    "verified_safe": "#0ca30c",
    "error": "#ec835a",
}

_BUCKET_BLURB = {
    "landmine": "Proven breakage that no mechanical fix reaches, or a failed verification. "
                "Changing these needs a migration plan and owners in the room.",
    "unassessed": "At least one consumer could not be read (unparseable SQL, or no SQL "
                  "definition at all). **Not safe** — nothing is known about them. Zero "
                  "breaks over a partial corpus is not a clean bill of health.",
    "needs_review": "Improved, ambiguous, or incomplete. A human decides.",
    "verified_safe": "Safe to change. Read the `basis` column: `verified_patch` means a fix "
                     "was generated, applied in isolation and re-checked; `no_references` "
                     "means nothing that parses referenced the column, so no patch was "
                     "needed and none was verified.",
    "error": "The sweep could not assess these. An error is not a verdict — nothing is "
             "claimed about them either way.",
}

_SCOPE = ("Static analysis only. Patches were applied in isolated copies and re-parsed; "
          "**no query was executed, no warehouse was contacted, no data was read**, and "
          "**nothing was written to DataHub** — a sweep is read-only by construction.")


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _rel(path: str | None) -> str | None:
    """Render patch links relative to the working directory.

    An absolute link is correct on the machine that produced the ledger and broken everywhere
    else — including in a fresh clone, which is exactly where a reviewer reads it. The stored
    `patch_path` stays absolute (callers use it to open the file); only the rendered link is
    relativised, and it falls back to the absolute form when the file is genuinely outside the
    tree rather than emitting a link that silently points nowhere.
    """
    if not path:
        return None
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path


def _entry_detail(e: SweepEntry, *, markdown: bool = True) -> str:
    """The row's explanation. `markdown=False` yields plain text for the HTML renderer, which
    escapes its input — emitting `**bold**` and backticks there would render them literally."""
    if e.bucket == "error":
        return e.error or "unknown error"
    b = "**" if markdown else ""
    t = "`" if markdown else ""
    bits: list[str] = []
    if e.verdict:
        bits.append(f"verification {b}{e.verdict}{b}")
        if e.breaks_before is not None:
            bits.append(f"breaks {e.breaks_before}→{e.breaks_after}")
    if e.basis:
        bits.append(f"basis {t}{e.basis}{t}")
    if e.blocking_consumers:
        shown = ", ".join(e.blocking_consumers[:3])
        more = f" +{len(e.blocking_consumers) - 3} more" if len(e.blocking_consumers) > 3 else ""
        bits.append(f"unreachable by any mechanical fix: {shown}{more}")
    if e.reasons:
        bits.append(", ".join(f"{t}{r}{t}" for r in e.reasons[:4]))
    return " · ".join(bits) or "—"


def render_sweep_md(res: SweepResult) -> str:
    t = res.totals()
    L: list[str] = []
    L.append(f"# Catalog Sweep — {res.catalog}")
    L.append("")
    L.append("_Every candidate column change, assessed with the same impact → fix → verify "
             "chain as a single run._")
    L.append("")
    L.append(f"**{res.header_line()}**")
    L.append("")
    L.append(f"| Datasets | Columns assessed | Coverage | Duration | Started |")
    L.append("|---:|---:|---|---:|---|")
    L.append(f"| {res.datasets_scanned} | {res.columns_assessed} of {res.candidates_total} "
             f"| {res.coverage_line()} | {res.duration_seconds:.1f}s | {res.started_at} |")
    L.append("")
    L.append("| Bucket | Count |")
    L.append("|---|---:|")
    for b in BUCKET_ORDER:
        L.append(f"| {BUCKET_LABEL[b]} | {t[b]} |")
    L.append("")
    L.append(f"> {_SCOPE}")
    L.append("")
    if res.limit is not None:
        L.append(f"> ⚠️ **Partial sweep.** `--sweep-limit {res.limit}` was given, so "
                 f"**{res.columns_assessed} of {res.candidates_total}** candidates were "
                 f"assessed. The {res.candidates_total - res.columns_assessed} not assessed "
                 f"are absent from this ledger — they are not implied safe.")
        L.append("")
    L.append("---")
    L.append("")

    by = res.by_bucket()
    for b in BUCKET_ORDER:
        rows = by[b]
        L.append(f"## {BUCKET_LABEL[b]} ({len(rows)})")
        L.append("")
        L.append(f"_{_BUCKET_BLURB[b]}_")
        L.append("")
        if not rows:
            L.append("None.")
            L.append("")
            continue
        L.append("| Column | Change | Risk | Breaks | Degr | Safe | Unknown | Coverage | "
                 "Patch | Detail |")
        L.append("|---|---|---|---:|---:|---:|---:|---|---|---|")
        for e in rows:
            patch = f"[`patch`]({_rel(e.patch_path)})" if e.patch_path else "—"
            L.append(
                f"| `{e.ref}` | {e.change} | {e.risk_level} ({e.risk_score}) | {e.breaks} | "
                f"{e.degrades} | {e.safe} | {e.unknown} | {e.coverage} | {patch} | "
                f"{_entry_detail(e)} |"
            )
        L.append("")

    L.append("---")
    L.append("")
    L.append(f"_Generated by Blast Radius Autopilot · sweep of `{res.catalog}` · "
             f"ops {', '.join(res.ops)} · public/synthetic data only._")
    return "\n".join(L) + "\n"


def render_sweep_html(res: SweepResult) -> str:
    t = res.totals()
    by = res.by_bucket()

    tiles = "".join(
        f"<div class='tile'><div class='tnum' style='color:{_BUCKET_COLOR[b]}'>{t[b]}</div>"
        f"<div class='tlab'>{_e(BUCKET_LABEL[b])}</div></div>"
        for b in BUCKET_ORDER
    )

    sections = []
    for b in BUCKET_ORDER:
        rows = by[b]
        body = []
        for e in rows:
            patch = (f"<a href='{_e(_rel(e.patch_path))}'>patch</a>" if e.patch_path else "—")
            # The detail sits UNDER the change rather than in a far-right column: as its own
            # column it was pushed off the horizontal scroll and left every row tall and
            # apparently empty, which read as a rendering bug.
            body.append(
                f"<tr><td><code>{_e(e.ref)}</code>"
                f"<div class='detail'>{_e(_entry_detail(e, markdown=False))}</div></td>"
                f"<td>{_e(e.risk_level)} ({e.risk_score})</td>"
                f"<td class='num'>{e.breaks}</td><td class='num'>{e.degrades}</td>"
                f"<td class='num'>{e.safe}</td><td class='num'>{e.unknown}</td>"
                f"<td>{_e(e.coverage)}</td><td>{patch}</td></tr>"
            )
        table = (
            "<table><thead><tr><th>Column &amp; detail</th><th>Risk</th><th>Breaks</th>"
            "<th>Degr</th><th>Safe</th><th>Unknown</th><th>Coverage</th><th>Patch</th>"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
            if rows else "<p class='sub'>None.</p>"
        )
        sections.append(
            f"<section><h2><span class='dot' style='background:{_BUCKET_COLOR[b]}'></span>"
            f"{_e(BUCKET_LABEL[b])} <span class='count'>({len(rows)})</span></h2>"
            f"<p class='sub'>{_e(_BUCKET_BLURB[b])}</p>{table}</section>"
        )

    partial = ""
    if res.limit is not None:
        partial = (
            f"<p class='warn'>⚠️ <strong>Partial sweep.</strong> "
            f"<code>--sweep-limit {res.limit}</code> was given, so "
            f"{res.columns_assessed} of {res.candidates_total} candidates were assessed. The "
            f"{res.candidates_total - res.columns_assessed} not assessed are absent from this "
            f"ledger — they are <strong>not</strong> implied safe.</p>"
        )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catalog Sweep — {_e(res.catalog)}</title>
<style>
:root {{ color-scheme:light; --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --muted:#898781;
  --grid:#e1e0d9; --border:rgba(11,11,11,0.10); }}
@media (prefers-color-scheme:dark){{ :root:where(:not([data-theme="light"])){{ color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --muted:#898781; --grid:#2c2c2a;
  --border:rgba(255,255,255,0.10); }} }}
:root[data-theme="dark"]{{ color-scheme:dark; --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff;
  --muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,0.10); }}
:root[data-theme="light"]{{ color-scheme:light; --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b;
  --muted:#898781; --grid:#e1e0d9; --border:rgba(11,11,11,0.10); }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,sans-serif;line-height:1.5}}
.wrap{{max-width:1180px;margin:0 auto;padding:32px 24px 64px}}
h1{{font-size:26px;margin:0}} h2{{font-size:17px;margin:0 0 4px;display:flex;align-items:center;gap:8px}}
p.sub{{color:var(--muted);margin:4px 0 14px;font-size:14px}}
.hdr{{margin:14px 0 20px;padding:14px 16px;background:var(--surface);
  border:1px solid var(--border);border-radius:12px;font-size:14px}}
.tiles{{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 24px}}
.tile{{flex:1 1 150px;background:var(--surface);border:1px solid var(--border);
  border-radius:12px;padding:14px 16px}}
.tnum{{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}}
.tlab{{font-size:12px;color:var(--muted);margin-top:2px}}
.dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.count{{color:var(--muted);font-weight:400}}
section{{margin:0 0 30px}}
.tablewrap, table{{width:100%}}
section > table{{display:block;overflow-x:auto;white-space:nowrap}}
table{{border-collapse:collapse;font-size:13px;background:var(--surface);
  border:1px solid var(--border);border-radius:12px;overflow:hidden}}
th,td{{padding:9px 11px;border-bottom:1px solid var(--grid);text-align:left;vertical-align:top}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
td:first-child{{white-space:normal;min-width:340px;max-width:520px}}
.detail{{margin-top:3px;font-size:12px;color:var(--muted);white-space:normal}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:12px}}
.scope{{margin:0 0 20px;padding:12px 14px;border-left:3px solid var(--muted);
  background:var(--surface);border-radius:0 8px 8px 0;font-size:13px;color:var(--muted)}}
.warn{{margin:0 0 20px;padding:12px 14px;border-left:3px solid #fab219;
  background:var(--surface);border-radius:0 8px 8px 0;font-size:13px}}
a{{color:inherit}}
</style></head><body><div class="wrap">
<h1>Catalog Sweep</h1>
<p class="sub">{_e(res.catalog)} — every candidate column change, assessed with the same
impact → fix → verify chain as a single run.</p>
<div class="hdr"><strong>{_e(res.header_line())}</strong></div>
{partial}
<div class="tiles">{tiles}</div>
<div class="scope">{_SCOPE.replace('**', '')}</div>
{''.join(sections)}
<p class="sub">Generated by Blast Radius Autopilot · ops {_e(', '.join(res.ops))} ·
public/synthetic data only.</p>
</div></body></html>
"""


def sweep_json(res: SweepResult) -> dict:
    """Machine-readable ledger. Mirrors exactly what the markdown and HTML show."""
    return {
        "catalog": res.catalog,
        "started_at": res.started_at,
        "duration_seconds": round(res.duration_seconds, 3),
        "ops": list(res.ops),
        "order": res.order,
        "limit": res.limit,
        "datasets_scanned": res.datasets_scanned,
        "candidates_total": res.candidates_total,
        "columns_assessed": res.columns_assessed,
        "coverage_line": res.coverage_line(),
        "reconciles": res.reconciles(),
        "read_only": True,
        "scope": ("static analysis only; no query executed, no warehouse contacted, no data "
                  "read, and nothing written to DataHub"),
        "totals": res.totals(),
        "entries": [
            {
                "dataset": e.dataset, "dataset_urn": e.dataset_urn, "column": e.column,
                "op": e.op, "change": e.change, "bucket": e.bucket, "basis": e.basis,
                "breaks": e.breaks, "degrades": e.degrades, "safe": e.safe,
                "unknown": e.unknown, "ambiguous": e.ambiguous,
                "coverage": e.coverage, "coverage_complete": e.coverage_complete,
                "risk_level": e.risk_level, "risk_score": e.risk_score,
                "fragility_score": e.fragility_score,
                "runs_impacted": e.runs_impacted, "teams": e.teams,
                "patch_generated": e.patch_generated, "patch_path": e.patch_path,
                "fix_method": e.fix_method, "fixable_consumers": e.fixable_consumers,
                "blocking_consumers": e.blocking_consumers,
                "verdict": e.verdict, "reasons": e.reasons,
                "breaks_before": e.breaks_before, "breaks_after": e.breaks_after,
                "error": e.error,
            }
            for e in res.entries
        ],
    }
