"""B20.3 — screenshot the approval audit AS DATAHUB RENDERS IT (for the demo video).

`scripts/b20_3_live_readback.py` proves the six properties are in the catalog over
GraphQL. This proves they are *visible* — which is the claim the demo makes on camera.

Honesty gate, in the spirit of `capture_verification_ui.py`: the capture FAILS if
`blast_radius_approved_by` and the approver are not actually present on the rendered
page. A screenshot of an empty Properties tab would otherwise look like evidence.

Run AFTER b20_3_live_readback.py, with the local DataHub frontend up:
    PATH=~/bra/venv/bin:$PATH python scripts/b20_3_capture_audit_ui.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from capture_ui import OUT, dismiss_onboarding, ds_url, login  # noqa: E402

# The synthetic showcase-ecommerce target the approval was applied to.
FCT_ORDERS = "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.fct_orders,PROD)"
# DataHub's Properties tab renders each property's DISPLAY NAME, not its qualifiedName —
# `ensure_property_definitions()` sets `displayName = key.replace("_", " ").title()`. The
# first version of this gate looked for `blast_radius_approved_by` and failed a capture
# that was in fact correct, which is the gate working: assert what the page shows.
MUST_SEE = ["Blast Radius Approved By", "reviewer@example.com",
            "Blast Radius Approved At", "Blast Radius Approved Writes",
            "Blast Radius Approved Failures", "Blast Radius Manifest Id",
            "Blast Radius Verification Status At Approval"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        login(page)
        dismiss_onboarding(page)

        page.goto(ds_url(FCT_ORDERS, "Properties"), wait_until="domcontentloaded")
        try:
            page.wait_for_selector("text=Blast Radius Approved By", timeout=25000)
        except Exception:
            pass
        page.wait_for_timeout(3500)
        dismiss_onboarding(page)
        page.wait_for_timeout(600)

        body = page.inner_text("body")
        missing = [s for s in MUST_SEE if s not in body]
        shots = []
        for name, full in [("15_b20_3_approval_audit_properties.png", True),
                           ("16_b20_3_approval_audit_viewport.png", False)]:
            path = OUT / name
            page.screenshot(path=str(path), full_page=full)
            shots.append(str(path))
        browser.close()

    for s in shots:
        print(f"  captured {s}")
    if missing:
        print(f"\n  FAILED — the page does not show: {missing}")
        print("  The screenshots were kept so the gap is inspectable, but they are NOT "
              "evidence that the audit is visible.")
        return 1
    print(f"\n  All required text present on the rendered page: {MUST_SEE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
