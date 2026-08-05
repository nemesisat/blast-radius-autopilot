"""B21 — screenshot the sweep ledger, light and dark.

Honesty gate, same shape as the other capture scripts: the capture FAILS unless the page
really shows the header totals, all five bucket labels, and the read-only scope line. A
screenshot of a ledger that quietly dropped the unassessed group, or that omitted the
read-only guarantee, would look like better evidence than it is.

Run AFTER scripts/b21_sweep_capture.py:
    python scripts/b21_capture_sweep_ui.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "live_ui"
LEDGER = ROOT / "out" / "SWEEP.html"

MUST_SEE = [
    "Catalog Sweep",
    "Landmines", "Unassessed", "Needs review", "Verified safe", "Errors",
    "column(s) assessed",
    "nothing was written to DataHub",
    "no query was executed",
]


def main() -> int:
    if not LEDGER.exists():
        print(f"  {LEDGER} does not exist — run scripts/b21_sweep_capture.py first")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme, suffix in (("light", ""), ("dark", "_dark")):
            page = browser.new_page(viewport={"width": 1280, "height": 900},
                                    color_scheme=theme)
            page.goto(LEDGER.as_uri(), wait_until="load")
            page.wait_for_timeout(800)
            if theme == "light":
                body = page.inner_text("body")
                missing = [s for s in MUST_SEE if s.lower() not in body.lower()]
                # The page must not scroll horizontally — wide tables scroll inside their own
                # container, not the document.
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth > "
                    "document.documentElement.clientWidth")
                if overflow:
                    missing.append("<page scrolls horizontally>")
            page.screenshot(path=str(OUT / f"19_b21_sweep_ledger{suffix}.png"))
            page.screenshot(path=str(OUT / f"19_b21_sweep_ledger{suffix}_full.png"),
                            full_page=True)
            print(f"  captured 19_b21_sweep_ledger{suffix}.png (+ _full)")
            page.close()
        browser.close()

    if missing:
        print(f"\n  FAILED — the rendered ledger does not show: {missing}")
        return 1
    print(f"\n  All required content present: {len(MUST_SEE)} checks, no horizontal overflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
