"""B20 — re-screenshot the two LIVE-MCP reports against the current build.

The existing `out/live_ui/08_b15_*` / `09_b15_*` shots were captured under B15 semantics,
before the B16–B19 verification gates existed, so their verdict areas no longer match what
the tool prints. This regenerates them from the reports `scripts/mcp_live_run.py` just wrote.

Honesty gate, same idea as `capture_verification_ui.py`: the capture FAILS unless the page
really shows the coverage denominator and the UNKNOWN accounting — the two things the live
MCP runs exist to demonstrate. A screenshot of a report that quietly dropped the unassessed
consumers would otherwise look like better evidence than it is.

Run AFTER the two mcp_live_run.py invocations:
    PATH=~/bra/venv/bin:$PATH python scripts/b20_capture_mcp_ui.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "live_ui"

# (label, report html, strings that MUST be on the page)
CASES = [
    ("17_b20_mcp_live_order_details", "out/mcp_live_report.html",
     ["5 of 24", "REVIEW REQUIRED"]),
    ("18_b20_mcp_live_addresses", "out/mcp_live_addresses_report.html",
     ["5 of 17", "REVIEW REQUIRED"]),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, html, must_see in CASES:
            path = ROOT / html
            if not path.exists():
                failures.append(f"{label}: {html} does not exist — run mcp_live_run.py first")
                continue
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(path.as_uri(), wait_until="load")
            page.wait_for_timeout(900)
            body = page.inner_text("body")
            missing = [s for s in must_see if s not in body]
            page.screenshot(path=str(OUT / f"{label}_abovefold.png"))
            page.screenshot(path=str(OUT / f"{label}_full.png"), full_page=True)
            print(f"  captured {label}_abovefold.png + _full.png")
            if missing:
                failures.append(f"{label}: page does not show {missing}")
            page.close()
        browser.close()

    if failures:
        print("\n  FAILED:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("\n  Both reports show their coverage denominator and REVIEW REQUIRED state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
