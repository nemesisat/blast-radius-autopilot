"""Integration test: the flagship scenario end to end over the showcase-ecommerce
fixtures — 'drop customer_zip from fct_orders'. Proves the impact core produces the
exact blast radius the demo claims.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.catalog import load_catalog
from autopilot.impact import compute_impact
from autopilot.schema import ChangeSpec, Op, Verdict

EX = Path(__file__).resolve().parents[1] / "examples" / "showcase-ecommerce"


@pytest.fixture
def catalog():
    return load_catalog(EX / "catalog.json")


def test_flagship_drop_customer_zip(catalog):
    report = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))
    c = report.counts()
    # B15: filter-only references (WHERE/JOIN) now BREAK on a drop rather than
    # DEGRADE — dropping a column a WHERE names makes the query error. The two
    # previously-DEGRADES consumers moved into breaks; nothing else changed.
    assert c["breaks"] == 6
    assert c["degrades"] == 0
    assert c["safe"] == 3
    assert c["ambiguous"] == 1
    assert c["unknown"] == 0
    assert c["runs_impacted"] == 41          # the demo's "41 queries" figure
    assert set(report.teams_impacted()) == {"growth-analytics", "analytics-eng", "marketing-bi"}
    assert report.risk()["level"] == "CRITICAL"


def test_flagship_has_full_coverage_but_one_unresolved_reference(catalog):
    """Coverage and confidence are different axes, and the flagship separates them.

    Every fixture query PARSES, so coverage is complete — the B15 blind-spot gate does
    not fire. But one unqualified column reference spans two joined tables that both
    provide it, so it cannot be attributed. B17.1: that is unresolved impact, and it
    forces review even though nothing was left unread.
    """
    report = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))
    cov = report.coverage()
    assert cov == {"analysed": 10, "total": 10, "unassessed": 0, "line": "10 of 10 analysed"}
    assert report.counts()["ambiguous"] == 1
    assert report.review_required() is True, "an unattributable reference must force review"
    assert report.auto_applicable() is False
    # The qualifier names the real reason: nothing went unassessed, one ref is unresolved.
    assert report.risk()["level_qualifier"] == "CRITICAL with 1 unresolved reference(s)"
    assert "among assessed" not in report.risk()["level_qualifier"]


def test_breaks_include_the_expected_consumers(catalog):
    report = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))
    broken_ids = {v.query_id for v in report.breaks}
    assert "q_looker_sales_by_zip" in broken_ids      # Looker dashboard
    assert "q_dbt_rpt_orders_by_region" in broken_ids  # dbt model (the one we auto-fix)
    # B15: filter-only consumers are breaks now, not degrades.
    assert "q_powerbi_revenue_by_state" in broken_ids     # WHERE-only -> would error
    assert "q_adhoc_join_on_zip" in broken_ids            # JOIN-only  -> would error
    assert report.degrades == []


def test_ambiguous_is_gated_not_counted(catalog):
    report = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))
    amb = report.ambiguous
    assert len(amb) == 1
    assert amb[0].query_id == "q_adhoc_ambiguous_zip"
    assert amb[0] not in report.breaks   # low-confidence: never counted as a definite break


def test_rename_and_drop_agree_on_resolved_references(catalog):
    """B15: a reference that resolves to the column breaks under BOTH ops, so the
    verdicts now agree. What differs is the remediation the reason text prescribes."""
    drop = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))
    rename = compute_impact(
        catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "rename", new_name="postal_code")
    )
    assert {v.query_id for v in rename.breaks} == {v.query_id for v in drop.breaks}
    assert len(rename.degrades) == len(drop.degrades) == 0
    # The prescription differs even though the severity does not.
    rn = next(v for v in rename.breaks if v.query_id == "q_looker_sales_by_zip")
    dr = next(v for v in drop.breaks if v.query_id == "q_looker_sales_by_zip")
    assert "postal_code" in rn.reason and "rewritten" in rn.reason
    assert "column removed" in dr.reason


def test_safe_column_has_no_breaks(catalog):
    report = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "status", "drop"))
    # `status` is only ever grouped/counted, never projected as a lineage output here...
    # at least it must not falsely break the customer_zip consumers.
    assert all(v.usage != "select" or v.query_id == "q_adhoc_status_breakdown" for v in report.verdicts)
