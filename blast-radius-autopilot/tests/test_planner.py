"""B14 — grounded Migration Planner tests: topological step order, owner rollup,
rollback references the generated PR, and a guard that the rendered plan contains
NO fabricated effort/timeline/confidence tokens."""

from __future__ import annotations

import re

import pytest

from autopilot.fixgen import FixResult
from autopilot.planner import build_plan, plan_from_report, render_plan_md
from autopilot.schema import ChangeSpec, ImpactReport, ImpactVerdict, Verdict


@pytest.fixture
def report():
    change = ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop")
    verdicts = [
        # A: dbt model directly on the target (BREAKS)
        ImpactVerdict(query_id="qA", verdict=Verdict.BREAKS, usage="select", clauses=["select"],
                      confidence="high", team="team-a", runs=10,
                      asset_urn="urn:A", asset_name="stg_orders", asset_type="dbt_model", reason="projects customer_zip"),
        # B: BI dashboard that depends on A (BREAKS)
        ImpactVerdict(query_id="qB", verdict=Verdict.BREAKS, usage="select", clauses=["select"],
                      confidence="high", team="team-b", runs=8,
                      asset_urn="urn:B", asset_name="sales_dashboard", asset_type="looker_dashboard", reason="projects customer_zip"),
        # C: another dbt model, DEGRADES
        ImpactVerdict(query_id="qC", verdict=Verdict.DEGRADES, usage="filter", clauses=["where"],
                      confidence="medium", team="team-c", runs=5,
                      asset_urn="urn:C", asset_name="rpt_metrics", asset_type="dbt_model", reason="filters on customer_zip"),
        # a SAFE one (excluded from steps)
        ImpactVerdict(query_id="qS", verdict=Verdict.SAFE, usage="none", confidence="high", team="team-d", runs=3,
                      asset_urn=None, asset_name=None, asset_type=None, reason="no reference"),
    ]
    return ImpactReport(change=change, catalog="t", target_urn="urn:T", verdicts=verdicts, notes=[])


@pytest.fixture
def fix():
    return FixResult(asset_urn="urn:A", asset_name="stg_orders", path="models/stg_orders.sql",
                     original_sql="SELECT a, customer_zip FROM t", new_sql="SELECT a FROM t",
                     diff="--- a\n+++ b\n-  customer_zip", applicable=True, method="minimal")


LINEAGE = {"urn:B": ["urn:A"]}  # B (BI) depends on A (model)


def test_step_order_is_topological(report, fix):
    plan = build_plan(report.change, report, LINEAGE, owners=None, generated_fix=[fix])
    keys = [s.key for s in plan.ordered_steps]
    # deterministic topo order: models first (tie broken by name: rpt_metrics < stg_orders), BI last
    assert keys == ["urn:C", "urn:A", "urn:B"]
    # the dependency edge B->A is respected, and the BI consumer is last
    assert keys.index("urn:A") < keys.index("urn:B")
    assert plan.ordered_steps[-1].asset_type == "looker_dashboard"


def test_every_owner_in_teams_to_involve(report, fix):
    plan = build_plan(report.change, report, LINEAGE, owners=None, generated_fix=[fix])
    for team in ("team-a", "team-b", "team-c"):
        assert team in plan.teams_to_involve
    # the SAFE consumer's team is not an impacted step, so not required
    assert "team-d" not in plan.teams_to_involve


def test_action_uses_generated_fix_then_manual_review(report, fix):
    plan = build_plan(report.change, report, LINEAGE, owners=None, generated_fix=[fix])
    by_key = {s.key: s for s in plan.ordered_steps}
    assert "apply generated fix: models/stg_orders.sql" == by_key["urn:A"].action
    assert "manual review" in by_key["urn:B"].action     # BI has no auto-fix


def test_rollback_references_generated_pr(report, fix):
    plan = build_plan(report.change, report, LINEAGE, owners=None, generated_fix=[fix])
    joined = " ".join(plan.rollback)
    assert "PR" in joined
    assert "models/stg_orders.sql" in joined
    assert "re-add column `customer_zip`" in joined.lower() or "re-add column `customer_zip`" in joined


def test_no_fabricated_tokens_in_rendered_plan(report, fix):
    md = render_plan_md(build_plan(report.change, report, LINEAGE, owners=None, generated_fix=[fix]))
    low = md.lower()
    assert "hour" not in low
    assert not re.search(r"\bdays?\b", low)
    assert "%" not in md
    # no NUMERIC confidence anywhere; the only confidence is the labeled parser word (high/medium/low)
    assert not re.search(r"confidence:\s*\d", low)
    assert re.search(r"parser\) confidence: (high|medium|low)", low)
    # effort/timeline/window must be explicit human placeholders, not computed
    assert md.count("⟨human to decide⟩") >= 3


def test_plan_from_report_convenience(report):
    plan = plan_from_report(report, fixes=[])
    assert plan.change == "drop analytics.fct_orders.customer_zip"
    assert plan.risk_level in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert len(plan.ordered_steps) == 3   # A, B, C (SAFE excluded)
