"""B21 evidence — sweep every synthetic example catalog and capture the ledgers.

OFFLINE ONLY. This touches no DataHub instance: the sweep is read-only by construction, and
this script never constructs a client. (The live instance is in use for video recording.)

Writes per-catalog ledgers plus a combined one:
    out/sweep/<catalog>/SWEEP.md · SWEEP.html · sweep.json
    out/SWEEP.md · out/SWEEP.html · out/sweep.json     (the flagship catalog, for the demo)

Run: python scripts/b21_sweep_capture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autopilot.catalog import load_catalog  # noqa: E402
from autopilot.report_sweep import render_sweep_html, render_sweep_md, sweep_json  # noqa: E402
from autopilot.sweep import BUCKET_ORDER, sweep  # noqa: E402

EXAMPLES = [
    "showcase-ecommerce", "nyc-taxi", "healthcare", "fiction-retail", "finance",
    "verified-migration",
]
FLAGSHIP = "showcase-ecommerce"


def main() -> int:
    out = ROOT / "out"
    rows = []
    total_cols = total_datasets = 0
    grand = {b: 0 for b in BUCKET_ORDER}
    wall = 0.0

    for name in EXAMPLES:
        cat_path = ROOT / "examples" / name / "catalog.json"
        if not cat_path.exists():
            print(f"  SKIP {name}: {cat_path} not found")
            continue
        catalog = load_catalog(cat_path)
        res = sweep(catalog, repo_root=cat_path.parent,
                    patch_dir=out / "sweep" / name / "patches")

        d = out / "sweep" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SWEEP.md").write_text(render_sweep_md(res))
        (d / "SWEEP.html").write_text(render_sweep_html(res))
        (d / "sweep.json").write_text(json.dumps(sweep_json(res), indent=2))

        if name == FLAGSHIP:
            (out / "SWEEP.md").write_text(render_sweep_md(res))
            (out / "SWEEP.html").write_text(render_sweep_html(res))
            (out / "sweep.json").write_text(json.dumps(sweep_json(res), indent=2))

        t = res.totals()
        for b in BUCKET_ORDER:
            grand[b] += t[b]
        total_cols += res.columns_assessed
        total_datasets += res.datasets_scanned
        wall += res.duration_seconds
        rows.append((name, res, t))
        assert res.reconciles(), f"{name}: buckets do not reconcile"

    print("=" * 108)
    print("  B21 CATALOG SWEEP — every synthetic example catalog (OFFLINE; nothing written)")
    print("=" * 108)
    print(f"  {'CATALOG':<22} {'DS':>3} {'COLS':>5} {'LAND':>5} {'UNASS':>6} {'REVIEW':>7} "
          f"{'SAFE':>5} {'ERR':>4} {'SECS':>6}  COVERAGE")
    print("-" * 108)
    for name, res, t in rows:
        print(f"  {name:<22} {res.datasets_scanned:>3} {res.columns_assessed:>5} "
              f"{t['landmine']:>5} {t['unassessed']:>6} {t['needs_review']:>7} "
              f"{t['verified_safe']:>5} {t['error']:>4} {res.duration_seconds:>6.2f}  "
              f"{res.coverage_line()}")
    print("-" * 108)
    print(f"  {'TOTAL':<22} {total_datasets:>3} {total_cols:>5} "
          f"{grand['landmine']:>5} {grand['unassessed']:>6} {grand['needs_review']:>7} "
          f"{grand['verified_safe']:>5} {grand['error']:>4} {wall:>6.2f}")
    print("=" * 108)
    print("  READ-ONLY: no DataHub client was constructed and no mutation was attempted.")
    print("=" * 108)

    # The honesty split inside "verified safe" — how many were actually verified by a patch.
    verified_patch = no_refs = 0
    for _n, res, _t in rows:
        for e in res.by_bucket()["verified_safe"]:
            if e.basis == "verified_patch":
                verified_patch += 1
            elif e.basis == "no_references":
                no_refs += 1
    print(f"\n  Of {grand['verified_safe']} 'verified safe': {verified_patch} had a patch "
          f"generated, applied in isolation and re-checked (`verified_patch`); "
          f"{no_refs} were referenced by nothing that parses, so no patch was needed and "
          f"none was verified (`no_references`).")
    print(f"  Ledgers -> {out / 'sweep'}/<catalog>/  and the flagship at {out / 'SWEEP.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
