"""B13 — catalog fragility leaderboard: ranks columns by drop blast radius."""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.catalog import load_catalog
from autopilot.fragility import fragility_leaderboard, render_html, render_markdown

EX = Path(__file__).resolve().parents[1] / "examples" / "showcase-ecommerce"


@pytest.fixture
def catalog():
    return load_catalog(EX / "catalog.json")


def test_leaderboard_ranks_most_consumed_first(catalog):
    rows = fragility_leaderboard(catalog)
    assert rows, "leaderboard should not be empty"
    # `amount` is projected/aggregated in the most queries, so it is the single most
    # fragile column — even ahead of customer_zip. The leaderboard surfaces that honestly.
    top = rows[0]
    assert (top.dataset, top.column) == ("fct_orders", "amount")
    assert top.breaks >= 7 and top.level == "CRITICAL"
    # customer_zip (the flagship change) is still near the top and CRITICAL.
    top3 = {(r.dataset, r.column): r for r in rows[:3]}
    assert ("fct_orders", "customer_zip") in top3
    assert top3[("fct_orders", "customer_zip")].level == "CRITICAL"
    # unused columns rank at the bottom with zero fragility.
    assert rows[-1].breaks == 0 and rows[-1].degrades == 0


def test_leaderboard_is_sorted_worst_first(catalog):
    rows = fragility_leaderboard(catalog)
    scores = [r.score for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_leaderboard_covers_every_column(catalog):
    rows = fragility_leaderboard(catalog)
    total_cols = sum(len(d.schema) for d in catalog.datasets)
    assert len(rows) == total_cols     # every column scored, including the safe ones


def test_renders_html_and_markdown(catalog):
    rows = fragility_leaderboard(catalog)
    html = render_html(rows, catalog.name)
    assert html.strip().startswith("<!doctype html>")
    assert "customer_zip" in html
    md = render_markdown(rows, catalog.name)
    assert "Catalog Fragility Leaderboard" in md and "customer_zip" in md
