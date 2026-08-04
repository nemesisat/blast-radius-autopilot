"""Capture DataHub UI screenshots proving the live write-back (for the demo video).

Logs into the local DataHub frontend (datahub/datahub), then screenshots the
fct_orders entity (tags + properties + documentation/institutional memory) and a
downstream impacted asset. Output -> out/live_ui/. Public/synthetic data only.
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:9002"
OUT = Path(__file__).resolve().parents[1] / "out" / "live_ui"
# Real showcase-ecommerce datapack assets (not the earlier hand-seeded toy ones).
FCT = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.orders,PROD)"
DOWN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"


def ds_url(urn: str, tab: str = "") -> str:
    enc = urllib.parse.quote(urn, safe="")
    return f"{BASE}/dataset/{enc}/{tab}"


def login(page) -> None:
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    # DataHub login form (Ant Design). Try several selectors robustly.
    filled = False
    for user_sel, pass_sel in [
        ("input[data-testid='username']", "input[data-testid='password']"),
        ("#username", "#password"),
        ("input[name='username']", "input[name='password']"),
        ("input[placeholder='Username']", "input[placeholder='Password']"),
    ]:
        try:
            if page.locator(user_sel).count():
                page.fill(user_sel, "datahub")
                page.fill(pass_sel, "datahub")
                filled = True
                break
        except Exception:
            continue
    if not filled:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT / "00_login_page_DEBUG.png"), full_page=True)
        raise RuntimeError("could not locate login inputs; saved 00_login_page_DEBUG.png")
    # The Login button is data-testid='sign-in'. NOT button[type=submit] — that also
    # matches "Sign in with SSO", which would bounce us off the login form.
    for btn in ["button[data-testid='sign-in']", "button:has-text('Login')"]:
        if page.locator(btn).count():
            page.click(btn)
            break
    page.wait_for_timeout(4000)
    # Honesty gate: fail loudly if we're still on the login form.
    if page.locator("#username").count() or page.locator("input[data-testid='username']").count():
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT / "00_login_FAILED_DEBUG.png"), full_page=True)
        raise RuntimeError("login did not succeed — still on login form (see 00_login_FAILED_DEBUG.png)")


def dismiss_onboarding(page) -> None:
    """Close DataHub's 'Introducing…' onboarding tour so it doesn't overlay shots."""
    for sel in ["[data-testid='onboarding-close-button']", ".ant-modal-close",
                "button[aria-label='close']", "button[aria-label='Close']"]:
        try:
            if page.locator(sel).count():
                page.click(sel, timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except Exception:
        pass


def shoot(page, url: str, name: str, ready_text: str, waits: int = 3500) -> str:
    page.goto(url, wait_until="domcontentloaded")
    # Wait for real content (a known string on this page), not the loading skeleton.
    try:
        page.wait_for_selector(f"text={ready_text}", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(waits)
    dismiss_onboarding(page)
    page.wait_for_timeout(600)
    p = OUT / name
    page.screenshot(path=str(p), full_page=True)
    return str(p)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1600})
        page = ctx.new_page()
        login(page)
        # prove we're authenticated (search bar / home present)
        page.screenshot(path=str(OUT / "00_home_after_login.png"))
        shots.append(shoot(page, ds_url(FCT), "01_orders_overview.png", ready_text="order_total"))
        shots.append(shoot(page, ds_url(FCT, "Properties"), "02_orders_properties.png", ready_text="Blast Radius"))
        shots.append(shoot(page, ds_url(FCT, "Documentation"), "03_orders_documentation.png", ready_text="Blast Radius"))
        shots.append(shoot(page, ds_url(DOWN), "04_downstream_order_details.png", ready_text="impacted-by-upstream-change"))
        browser.close()
    print("screenshots saved:")
    for s in shots:
        print("  " + s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
