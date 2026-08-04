"""B17.7 — capture the verification VERDICT, in frame.

The earlier PASS/REVIEW screenshots showed the original blast radius with the actual
verdict below the visible area, so a reader of the evidence saw the problem and not the
answer. B17.7 moved the verdict banner directly under the report header; this script
captures it that way and proves it:

    *_verdict_abovefold.png   viewport-only shot (1280x800) — what a reader sees first.
                              The script FAILS if the verdict banner is not fully inside
                              that viewport, so the claim cannot rot silently.
    *_full.png                the whole page, for the record.

Public/synthetic data only. Nothing here executes SQL; it renders reports the CLI wrote.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "live_ui"
VIEWPORT = {"width": 1280, "height": 800}

# (label, catalog, change, html path) — the two verdicts the demo contrasts.
CASES = [
    ("13_b17_verification_pass", "examples/verified-migration/catalog.json",
     "drop analytics.fct_signups.referrer_code", "out/b17_pass_report.html"),
    ("14_b17_verification_review_required", "examples/showcase-ecommerce/catalog.json",
     "drop analytics.fct_orders.customer_zip", "out/b17_review_report.html"),
]


def build(catalog: str, change: str, html: str) -> None:
    """Regenerate the report from the CLI so the screenshot is of a real run."""
    subprocess.run(
        [sys.executable, "-m", "autopilot.run", "--catalog", catalog,
         "--change", change, "--verify", "--html", html],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )


def capture(page, label: str, html: str) -> None:
    page.goto((ROOT / html).as_uri(), wait_until="load")
    page.wait_for_timeout(400)

    banner = page.locator(".vbanner")
    if not banner.count():
        raise RuntimeError(f"{label}: no verification banner in {html}")

    verdict = page.locator(".vbanner .vverdict").first.inner_text().strip()
    box = banner.bounding_box()
    # THE assertion this script exists for: the verdict must be fully above the fold.
    bottom = box["y"] + box["height"]
    if bottom > VIEWPORT["height"]:
        page.screenshot(path=str(OUT / f"{label}_BELOWFOLD_DEBUG.png"))
        raise RuntimeError(
            f"{label}: verdict banner ends at y={bottom:.0f}px, below the "
            f"{VIEWPORT['height']}px fold — the verdict is not immediately visible"
        )

    page.screenshot(path=str(OUT / f"{label}_verdict_abovefold.png"))       # viewport only
    page.screenshot(path=str(OUT / f"{label}_full.png"), full_page=True)
    print(f"  {label}: verdict '{verdict}' visible at y={box['y']:.0f}-{bottom:.0f}px "
          f"(fold {VIEWPORT['height']}px) -> {label}_verdict_abovefold.png")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for label, catalog, change, html in CASES:
        print(f"building {html} ...")
        build(catalog, change, html)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in ("light", "dark"):
            page = browser.new_page(viewport=VIEWPORT, color_scheme=theme,
                                    device_scale_factor=2)
            for label, _cat, _chg, html in CASES:
                capture(page, f"{label}_{theme}" if theme == "dark" else label, html)
            page.close()
        browser.close()
    print(f"\nscreenshots -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
