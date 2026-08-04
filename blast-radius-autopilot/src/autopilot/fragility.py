"""B13 — Catalog Fragility leaderboard.

Ranks the riskiest columns to change across the whole catalog. For every column of
every dataset it simulates a DROP and scores the resulting blast radius (the same
impact core as everywhere else), then sorts worst-first. The output answers a
question every data platform team has: *"which columns are load-bearing landmines
we should be most careful changing?"*

Dataset-agnostic: it walks whatever datasets + query history the catalog has.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from .impact import compute_impact
from .schema import Catalog, ChangeSpec, Op

_RISK_COLOR = {"CRITICAL": "#d03b3b", "HIGH": "#ec835a", "MODERATE": "#fab219", "LOW": "#0ca30c"}


@dataclass
class FragilityRow:
    dataset: str
    dataset_urn: str
    column: str
    breaks: int
    degrades: int
    safe: int
    runs_impacted: int
    teams: int
    score: int
    level: str

    @property
    def rank_key(self) -> tuple:
        return (-self.score, -self.breaks, -self.runs_impacted, -self.degrades)


def fragility_leaderboard(catalog: Catalog, top: int | None = None) -> list[FragilityRow]:
    """Score every (dataset, column) by the blast radius of dropping it, worst first."""
    rows: list[FragilityRow] = []
    for ds in catalog.datasets:
        for col in ds.schema:
            report = compute_impact(catalog, ChangeSpec(dataset=ds.sql_name, column=col, op=Op.DROP))
            c = report.counts()
            risk = report.risk()
            if c["breaks"] == 0 and c["degrades"] == 0:
                # Still record it (fragility 0) so "safe to change" columns are visible too.
                pass
            rows.append(
                FragilityRow(
                    dataset=ds.name,
                    dataset_urn=ds.urn,
                    column=col,
                    breaks=c["breaks"],
                    degrades=c["degrades"],
                    safe=c["safe"],
                    runs_impacted=c["runs_impacted"],
                    teams=c["teams"],
                    score=int(risk["score"]),
                    level=str(risk["level"]),
                )
            )
    rows.sort(key=lambda r: r.rank_key)
    return rows[:top] if top else rows


def render_text(rows: list[FragilityRow], catalog_name: str) -> str:
    out = []
    out.append("=" * 78)
    out.append(f"  CATALOG FRAGILITY LEADERBOARD — {catalog_name}  (riskiest columns to change)")
    out.append("=" * 78)
    out.append(f"  {'#':>2}  {'DATASET.COLUMN':<40} {'RISK':>4}  {'BREAKS':>6} {'DEGR':>4} {'RUNS':>5} {'TEAMS':>5}")
    out.append("-" * 78)
    for i, r in enumerate(rows, 1):
        ref = f"{r.dataset}.{r.column}"
        out.append(
            f"  {i:>2}  {ref:<40} {r.score:>4}  {r.breaks:>6} {r.degrades:>4} {r.runs_impacted:>5} {r.teams:>5}"
            f"   {r.level}"
        )
    out.append("=" * 78)
    return "\n".join(out)


def render_markdown(rows: list[FragilityRow], catalog_name: str) -> str:
    out = [f"# Catalog Fragility Leaderboard — {catalog_name}", "",
           "_Riskiest columns to change, ranked by the blast radius of dropping each._", "",
           "| # | Column | Risk | Breaks | Degrades | Impacted runs | Teams |",
           "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        out.append(f"| {i} | `{r.dataset}.{r.column}` | **{r.level}** ({r.score}) | {r.breaks} | "
                   f"{r.degrades} | {r.runs_impacted} | {r.teams} |")
    out.append("")
    return "\n".join(out)


def render_html(rows: list[FragilityRow], catalog_name: str) -> str:
    def _e(s):
        return html.escape(str(s), quote=True)

    body = []
    maxscore = max((r.score for r in rows), default=1) or 1
    for i, r in enumerate(rows, 1):
        rc = _RISK_COLOR.get(r.level, "#898781")
        w = int(100 * r.score / maxscore)
        body.append(
            f"<tr><td class='num'>{i}</td>"
            f"<td><code>{_e(r.dataset)}.{_e(r.column)}</code></td>"
            f"<td><span class='bar'><span style='width:{w}%;background:{rc}'></span></span>"
            f"<span class='lvl' style='color:{rc}'>{_e(r.level)} ({r.score})</span></td>"
            f"<td class='num'>{r.breaks}</td><td class='num'>{r.degrades}</td>"
            f"<td class='num'>{r.runs_impacted}</td><td class='num'>{r.teams}</td></tr>"
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catalog Fragility — {_e(catalog_name)}</title>
<style>
:root {{ color-scheme:light; --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --muted:#898781;
  --grid:#e1e0d9; --border:rgba(11,11,11,0.10); }}
@media (prefers-color-scheme:dark){{ :root:where(:not([data-theme="light"])){{ color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,0.10); }} }}
body{{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,sans-serif;line-height:1.5}}
.wrap{{max-width:900px;margin:0 auto;padding:32px 24px 64px}}
h1{{font-size:24px;margin:0}} p.sub{{color:var(--muted);margin:4px 0 20px}}
table{{width:100%;border-collapse:collapse;font-size:14px;background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--grid);text-align:left}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:13px}}
.bar{{display:inline-block;width:90px;height:6px;border-radius:3px;background:var(--grid);vertical-align:middle;margin-right:8px;overflow:hidden}}
.bar span{{display:block;height:100%}} .lvl{{font-size:12px;font-weight:600}}
</style></head><body><div class="wrap">
<h1>Catalog Fragility Leaderboard</h1>
<p class="sub">{_e(catalog_name)} — riskiest columns to change, ranked by the blast radius of dropping each.</p>
<table><thead><tr><th>#</th><th>Column</th><th>Change risk</th><th>Breaks</th><th>Degrades</th><th>Impacted runs</th><th>Teams</th></tr></thead>
<tbody>{''.join(body)}</tbody></table>
<p class="sub" style="margin-top:16px">Generated by Blast Radius Autopilot · public/synthetic data only.</p>
</div></body></html>
"""
