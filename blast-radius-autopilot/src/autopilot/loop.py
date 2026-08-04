"""B6 — dataset-agnostic loop runner.

One config, many datasets: discovery → for each configured change, gather → analyze
→ decide → write back, all through the same generic primitives. Adding a dataset is
a config entry, not code — which is the whole "works on any dataset" claim, made
runnable.

Config (`loop.config.yaml`, YAML or JSON) shape::

    runs:
      - name: ecommerce-drop-zip
        catalog: examples/showcase-ecommerce/catalog.json
        change: "drop analytics.fct_orders.customer_zip"
      - name: finance-rename-revenue
        catalog: examples/finance/catalog.json
        change: "rename finance.fct_revenue.revenue_usd net_revenue_usd"
        require_review: true          # optional; else taken from the catalog

`require_review` defaults to the catalog's own flag (regulated catalogs queue every
write for a human).

NOTE (B19.3): the loop is a BREADTH runner — it does not statically verify each
generated fix, and auto-write requires a PASS. So every run here queues its mutations
for a human, with `queue_reason` naming why (`not_verified`, or `require_review` for a
regulated catalog). The loop has no approval route of its own by design: approving a
migration is a per-change decision, made with `--approve` on a single verified run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import load_catalog
from .fixgen import generate_fixes
from .impact import compute_impact
from .schema import ChangeSpec
from .writeback import WriteBack


@dataclass
class LoopRunResult:
    name: str
    catalog: str
    change: str
    counts: dict
    risk: dict
    written: int
    queued: int
    require_review: bool
    fixes: int
    # B17.4 — the truthful write-back buckets, carried per run so the loop summary
    # cannot report a dry run as written. B19.6 splits `written` by authorising path.
    written_auto: int = 0
    written_human_approved: int = 0
    queue_reason: str = ""
    planned: int = 0
    failed: int = 0
    total: int = 0
    dry_run: bool = True
    writeback_summary: str = ""
    reports: dict = field(default_factory=dict)


def load_loop_config(path: str | Path) -> list[dict]:
    text = Path(path).read_text()
    try:
        import yaml  # optional dependency

        data = yaml.safe_load(text)
    except ModuleNotFoundError:
        data = json.loads(text)
    if isinstance(data, dict):
        return list(data.get("runs", []))
    return list(data)


def run_loop(
    config_path: str | Path, write: bool = False, out_dir: str | Path | None = None,
    gms_url: str = "", token: str = "",
) -> list[LoopRunResult]:
    """Execute every run in the config; return per-run results."""
    config_path = Path(config_path)
    base = config_path.parent
    runs = load_loop_config(config_path)
    out_dir = Path(out_dir) if out_dir else None
    results: list[LoopRunResult] = []

    for run in runs:
        name = run["name"]
        catalog_path = (base / run["catalog"]).resolve()
        catalog = load_catalog(catalog_path)
        toks = str(run["change"]).split()
        op = toks[0]
        dataset, _, column = toks[1].rpartition(".")
        new_name = toks[2] if len(toks) > 2 else run.get("new_name")
        change = ChangeSpec.parse(dataset, column, op, new_name)

        report = compute_impact(catalog, change)
        fixes = generate_fixes(catalog, change, report, catalog_path.parent)
        require_review = bool(run.get("require_review", catalog.require_review))

        wb = WriteBack(gms_url=gms_url, token=token, dry_run=not write, require_review=require_review)
        res, assessment = wb.run(report, fixes)

        reports: dict = {}
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            from .report_html import render_html
            from .report_pr import render_pr_comment

            html_path = out_dir / f"{name}.html"
            html_path.write_text(render_html(report, fixes, assessment, writeback=res))
            pr_path = out_dir / f"{name}.PR_COMMENT.md"
            pr_path.write_text(render_pr_comment(report, fixes, assessment, writeback=res))
            reports = {"html": str(html_path), "pr_comment": str(pr_path)}

        wc = res.counts()
        results.append(
            LoopRunResult(
                name=name,
                catalog=catalog.name,
                change=change.describe(),
                counts=report.counts(),
                risk=report.risk(),
                written=wc["written"],
                written_auto=wc["written_auto"],
                written_human_approved=wc["written_human_approved"],
                queued=wc["queued_for_review"],
                queue_reason=res.queue_reason_line(),
                require_review=require_review,
                fixes=sum(1 for f in fixes if f.applicable and f.changed),
                planned=wc["planned"],
                failed=wc["failed"],
                total=wc["total"],
                dry_run=res.dry_run,
                writeback_summary=res.summary_line(),
                reports=reports,
            )
        )
    return results


def print_loop_summary(results: list[LoopRunResult]) -> None:
    print("\n" + "=" * 82)
    print("  BLAST RADIUS AUTOPILOT — LOOP SUMMARY (same loop, many datasets)")
    print("=" * 82)
    print(f"  {'RUN':<26}{'RISK':<10}{'BREAKS':>7}{'DEGR':>6}{'SAFE':>6}{'FIXES':>6}  WRITE-BACK")
    print("-" * 82)
    for r in results:
        # The real buckets, never the intent: a dry run reports 0 written (B17.4), and
        # the queue REASON is shown, because after B19.3 the loop (which does not
        # verify) can only ever queue — and a reader deserves to know why.
        print(
            f"  {r.name:<26}{r.risk['level']:<10}{r.counts['breaks']:>7}{r.counts['degrades']:>6}"
            f"{r.counts['safe']:>6}{r.fixes:>6}  {r.writeback_summary}"
            + ("  (dry run)" if r.dry_run else "")
        )
        if r.queue_reason:
            print(f"  {'':<26}{'':<10}{'':>7}{'':>6}{'':>6}{'':>6}  queued because: "
                  f"{r.queue_reason}")
    print("=" * 82 + "\n")
