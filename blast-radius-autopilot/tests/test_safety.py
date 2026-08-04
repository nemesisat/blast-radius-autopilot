"""B15 — safety semantics: MISSING EVIDENCE MUST NEVER READ AS PROOF OF SAFETY.

Two verified correctness defects motivated this suite (see PROGRESS.md 2026-07-29):

 1. A SQL parse failure was scored SAFE with confidence "high". `lineage.py`
    correctly marked it low-confidence, then `impact.py` overwrote confidence back
    to "high" because `usage == "none"`, and "none" maps to SAFE. On the live
    ADDRESSES run this scored a Jinja-templated dbt model SAFE while that model
    references `country_id` 4x — a false negative that made the whole run read LOW.

 2. On a DROP, a reference that resolves to the dropped column but sits only in
    WHERE/JOIN/GROUP/HAVING/ORDER was called DEGRADES. Dropping a column that a
    WHERE clause names makes the query *error*, not silently drift.

The invariants under test:

    parsed + no reference      -> SAFE      / high    (evidence of safety)
    parsed + resolved refernce -> BREAKS              (evidence of harm)
    parsed + star-only         -> DEGRADES            (runs; output changes)
    parse failure              -> UNKNOWN   / low     (NO evidence — never SAFE)
    no SQL definition at all   -> UNKNOWN             (NO evidence — never SAFE)
    ambiguous attribution      -> low confidence, not a definite BREAKS

UNKNOWN is its own state: it is not a break (no inflation) and not safe (no
false comfort). Any UNKNOWN forces the run to REVIEW_REQUIRED and is reported as a
coverage dimension, never folded into the numeric risk score.

All fixtures are synthetic.
"""

from __future__ import annotations

import pytest

from autopilot.impact import compute_impact
from autopilot.lineage import analyze_query
from autopilot.schema import Asset, Catalog, ChangeSpec, Dataset, Query, Verdict

# --- fixtures ------------------------------------------------------------------

ORDERS = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.orders,PROD)",
    name="orders",
    sql_name="sales.orders",
    platform="snowflake",
    schema={"order_id": "NUMBER", "customer_id": "NUMBER", "promotion_id": "NUMBER",
            "amount": "NUMBER", "order_date": "DATE"},
)

# A second table that ALSO has promotion_id — needed for the ambiguity and
# false-positive guards.
BONUSES = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.bonuses,PROD)",
    name="bonuses",
    sql_name="sales.bonuses",
    platform="snowflake",
    schema={"order_id": "NUMBER", "promotion_id": "NUMBER", "bonus_amt": "NUMBER"},
)

JINJA_SQL = "SELECT * FROM {{ ref('addresses') }} WHERE country_id = 1"


def _catalog(*queries: Query, assets: list[Asset] | None = None,
             datasets: list[Dataset] | None = None) -> Catalog:
    return Catalog(
        name="synthetic-safety",
        datasets=datasets if datasets is not None else [ORDERS, BONUSES],
        queries=list(queries),
        assets=assets or [],
        sql_dialect="snowflake",
    )


def _one(sql: str, *, column: str = "promotion_id", op: str = "drop",
         datasets: list[Dataset] | None = None):
    """Assess a single query and return its lone verdict."""
    cat = _catalog(Query(query_id="q1", sql=sql, platform="snowflake", team="t", runs=1),
                   datasets=datasets)
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", column, op))
    assert len(report.verdicts) == 1
    return report, report.verdicts[0]


# --- (a) parse failure -> UNKNOWN, never SAFE ----------------------------------

def test_a_unparseable_sql_is_unknown_not_safe():
    report, v = _one(JINJA_SQL, column="country_id")

    assert v.verdict is Verdict.UNKNOWN, f"parse failure must be UNKNOWN, got {v.verdict}"
    assert v.confidence == "low", f"parse failure must stay low confidence, got {v.confidence}"
    assert "parse_error" in v.reason or any("parse_error" in n for n in report.notes)

    # The two defect assertions, stated directly.
    assert v.verdict is not Verdict.SAFE, "a parse failure must never read as SAFE"
    assert v.confidence != "high", "a parse failure must never read as high confidence"


def test_a_unknown_is_not_counted_as_safe_or_break():
    report, v = _one(JINJA_SQL, column="country_id")
    c = report.counts()
    assert c["safe"] == 0, "an unassessed consumer must not be counted safe"
    assert c["breaks"] == 0, "UNKNOWN must not be inflated into a break"
    assert c["unknown"] == 1
    assert v not in report.safe
    assert v not in report.breaks


def test_a_lineage_layer_reports_parse_error_usage():
    """The core signal must exist at the lineage layer, not just be inferred."""
    usage = analyze_query(JINJA_SQL, ORDERS, "country_id", _catalog())
    assert usage.usage == "parse_error", f"expected usage='parse_error', got {usage.usage!r}"
    assert usage.confidence == "low"
    assert usage.note.startswith("parse_error")


# --- (b) DROP + WHERE reference -> BREAKS --------------------------------------

def test_b_drop_with_where_reference_breaks():
    report, v = _one("SELECT order_id FROM sales.orders WHERE promotion_id IS NOT NULL")
    assert v.usage == "filter", f"expected usage='filter', got {v.usage!r}"
    assert v.verdict is Verdict.BREAKS, (
        "dropping a column named in WHERE makes the query error — that is a BREAK, "
        f"got {v.verdict}"
    )
    assert "where" in v.clauses


# --- (c) the other filter clauses also BREAK on DROP --------------------------

@pytest.mark.parametrize(
    "label,sql,clause",
    [
        ("join",
         "SELECT o.order_id FROM sales.orders o "
         "JOIN sales.bonuses b ON o.promotion_id = b.bonus_amt",
         "join"),
        ("group",
         "SELECT promotion_id, COUNT(*) FROM sales.orders GROUP BY promotion_id",
         "group"),
        ("having",
         "SELECT customer_id FROM sales.orders GROUP BY customer_id "
         "HAVING MAX(promotion_id) > 3",
         "having"),
        ("order",
         "SELECT order_id FROM sales.orders ORDER BY promotion_id",
         "order"),
    ],
)
def test_c_all_filter_clauses_break_on_drop(label, sql, clause):
    _report, v = _one(sql)
    assert v.verdict is Verdict.BREAKS, f"{label}: expected BREAKS, got {v.verdict}"
    assert clause in v.clauses, f"{label}: expected clause {clause!r} in {v.clauses}"


# --- (d) genuine non-reference stays SAFE/high (no regression) -----------------

def test_d_unreferenced_parsed_query_stays_safe_high():
    report, v = _one("SELECT order_id, amount FROM sales.orders WHERE amount > 100")
    assert v.verdict is Verdict.SAFE, f"expected SAFE, got {v.verdict}"
    assert v.confidence == "high", (
        "a query that parsed cleanly and provably does not touch the column is "
        f"positive evidence of safety — must stay high, got {v.confidence}"
    )
    assert v.usage == "none"
    assert report.counts()["safe"] == 1
    assert report.counts()["unknown"] == 0


# --- (e) qualified ref to a DIFFERENT table -> not a break --------------------

def test_e_other_tables_same_named_column_is_not_a_break():
    _report, v = _one(
        "SELECT o.order_id FROM sales.orders o "
        "JOIN sales.bonuses b ON o.order_id = b.order_id "
        "WHERE b.promotion_id IS NOT NULL"
    )
    assert v.verdict is not Verdict.BREAKS, (
        "b.promotion_id belongs to bonuses, not orders — must not be a break"
    )
    assert v.verdict is Verdict.SAFE
    assert v.usage == "none"


# --- (f) ambiguous unqualified ref -> low confidence, not definite BREAKS -----

def test_f_ambiguous_unqualified_reference_is_gated():
    report, v = _one(
        "SELECT o.order_id FROM sales.orders o "
        "JOIN sales.bonuses b ON o.order_id = b.order_id "
        "WHERE promotion_id IS NOT NULL"          # unqualified; BOTH tables provide it
    )
    assert v.confidence == "low", f"ambiguous attribution must be low, got {v.confidence}"
    assert v.is_ambiguous
    assert v not in report.breaks, "a low-confidence reference is not a definite break"
    assert report.counts()["ambiguous"] == 1
    assert report.counts()["breaks"] == 0
    # Ambiguity is uncertainty, not absence of risk — it must not be filed as safe.
    assert report.counts()["safe"] == 0


# --- (g) consumer with no SQL definition at all -> unassessed, never SAFE -----

def test_g_consumer_without_sql_definition_is_unassessed():
    """PowerBI/Looker consumers discovered in lineage but exposing no
    viewProperties.logic cannot be analysed — they must surface as UNKNOWN."""
    assets = [
        Asset(urn="urn:li:dataset:(urn:li:dataPlatform:powerbi,synthetic.kpi_measures,PROD)",
              name="Essential KPI Measures", type="powerbi_report", platform="powerbi",
              defining_query_id=None),
        Asset(urn="urn:li:dataset:(urn:li:dataPlatform:looker,synthetic.orders_view,PROD)",
              name="Orders Looker View", type="looker_dashboard", platform="looker",
              defining_query_id=None),
    ]
    cat = _catalog(
        Query(query_id="q_ok", sql="SELECT order_id FROM sales.orders", platform="snowflake"),
        assets=assets,
    )
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))
    c = report.counts()

    assert c["unknown"] == 2, f"2 definition-less consumers must be UNKNOWN, got {c['unknown']}"
    assert c["safe"] == 1, "only the one analysable query is safe"
    names = {v.asset_name for v in report.unknown}
    assert names == {"Essential KPI Measures", "Orders Looker View"}
    for v in report.unknown:
        assert v.verdict is not Verdict.SAFE
        assert v.usage == "no_definition"
    assert report.review_required() is True


# --- (h) SELECT * on a DROP -> DEGRADES ---------------------------------------

def test_h_select_star_on_drop_degrades():
    """The query still executes; its output silently loses a column."""
    _report, v = _one("SELECT * FROM sales.orders")
    assert v.verdict is Verdict.DEGRADES, (
        f"SELECT * on a DROP changes output but still runs — expected DEGRADES, got {v.verdict}"
    )
    assert "select(*)" in v.clauses


def test_h_explicit_projection_still_breaks():
    """Guard: the star rule must not soften an explicit projection."""
    _report, v = _one("SELECT order_id, promotion_id FROM sales.orders")
    assert v.verdict is Verdict.BREAKS
    assert "select" in v.clauses


# --- (i) aggregate fail-closed ------------------------------------------------

def test_i_batch_with_parse_error_forces_review_required():
    cat = _catalog(
        Query(query_id="q_breaks", sql="SELECT promotion_id FROM sales.orders",
              platform="snowflake", team="a", runs=5),
        Query(query_id="q_safe", sql="SELECT amount FROM sales.orders",
              platform="snowflake", team="b", runs=3),
        Query(query_id="q_unparseable", sql=JINJA_SQL, platform="dbt", team="c", runs=7),
    )
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))
    c = report.counts()

    # fail closed
    assert report.review_required() is True, ">=1 parse error must force review"
    assert report.risk()["review_required"] is True
    assert report.auto_applicable() is False, "must not be auto-applied with an unassessed consumer"

    # the parse-error consumer is excluded from the SAFE count
    assert c["safe"] == 1, f"only q_safe is safe, got safe={c['safe']}"
    assert c["unknown"] == 1
    assert c["breaks"] == 1
    safe_ids = {v.query_id for v in report.safe}
    assert "q_unparseable" not in safe_ids

    # coverage is its own dimension
    cov = report.coverage()
    assert cov["analysed"] == 2
    assert cov["total"] == 3
    assert cov["unassessed"] == 1
    assert cov["line"] == "2 of 3 analysed"


def test_i_unknown_does_not_lower_the_risk_score():
    """Adding an unassessed consumer must not dilute the score downward."""
    base = _catalog(
        Query(query_id="q_breaks", sql="SELECT promotion_id FROM sales.orders",
              platform="snowflake", team="a", runs=5),
    )
    with_unknown = _catalog(
        Query(query_id="q_breaks", sql="SELECT promotion_id FROM sales.orders",
              platform="snowflake", team="a", runs=5),
        Query(query_id="q_unparseable", sql=JINJA_SQL, platform="dbt", team="c", runs=7),
    )
    change = ChangeSpec.parse("sales.orders", "promotion_id", "drop")
    r_base = compute_impact(base, change)
    r_unk = compute_impact(with_unknown, change)

    assert r_unk.risk()["score"] >= r_base.risk()["score"], (
        "an unassessed consumer must never reduce the risk score"
    )
    # ...and it does not inflate it either: coverage is reported separately.
    assert r_unk.risk()["score"] == r_base.risk()["score"]
    assert r_unk.risk()["review_required"] is True
    assert r_base.risk()["review_required"] is False


def test_i_all_clear_batch_is_auto_applicable():
    """The positive case: full coverage, no unknowns -> no forced review."""
    cat = _catalog(
        Query(query_id="q_safe1", sql="SELECT amount FROM sales.orders", platform="snowflake"),
        Query(query_id="q_safe2", sql="SELECT order_id FROM sales.orders", platform="snowflake"),
    )
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))
    assert report.review_required() is False
    assert report.auto_applicable() is True
    assert report.coverage()["line"] == "2 of 2 analysed"
    assert report.coverage()["unassessed"] == 0


# --- 2d/2e: the fix must reach write-back, planner, and the reports -----------

def _mixed_report():
    """A batch with one break, one safe, one unparseable consumer, and one
    consumer that exposes no SQL at all."""
    cat = _catalog(
        Query(query_id="q_breaks", sql="SELECT promotion_id FROM sales.orders",
              platform="snowflake", team="analytics", runs=5),
        Query(query_id="q_safe", sql="SELECT amount FROM sales.orders",
              platform="snowflake", team="bi", runs=3),
        Query(query_id="q_jinja", sql=JINJA_SQL, platform="dbt", team="data-eng", runs=7),
        assets=[
            Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.order_history,PROD)",
                  name="order_history", type="dbt_model", platform="dbt",
                  defining_query_id="q_jinja"),
            Asset(urn="urn:li:dataset:(urn:li:dataPlatform:powerbi,synthetic.kpis,PROD)",
                  name="Essential KPI Measures", type="powerbi_report", platform="powerbi",
                  defining_query_id=None),
        ],
    )
    return compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))


def test_writeback_queues_everything_when_coverage_is_incomplete():
    """2d: an incomplete assessment must never be auto-applied, even when the
    caller did not ask for review."""
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    report = _mixed_report()
    assert report.review_required() is True

    muts = plan_mutations(report, build_assessment(report, []), require_review=False)
    assert muts, "expected mutations to be planned"
    assert all(not m.auto for m in muts), (
        "every mutation must be queued for a human while any consumer is unassessed"
    )


def test_writeback_gate_on_full_coverage_is_verification_only(tmp_path):
    """The coverage gate must not be a blanket block: with full coverage, the ONLY thing
    still standing between this run and an automatic write is a verification.

    B19.3 made that explicit — an unverified run queues with `not_verified`, not with
    `unresolved_impact`. Naming the right gate matters: the reviewer's next action is
    "run --verify", not "go assess a consumer".
    """
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    cat = _catalog(
        Query(query_id="q_breaks", sql="SELECT promotion_id FROM sales.orders",
              platform="snowflake", team="analytics", runs=5),
    )
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))
    assert report.review_required() is False, "coverage is complete"
    muts = plan_mutations(report, build_assessment(report, []), require_review=False,
                          assessment_dir=tmp_path)
    assert muts and all(not m.auto for m in muts), "no PASS, no automatic write"
    assert {m.queue_reason for m in muts} == {"not_verified"}, (
        [m.queue_reason for m in muts]
    )


def test_structured_properties_carry_coverage():
    """2d: coverage must travel into the catalog, not just the console."""
    from autopilot.assessment import build_assessment

    doc = build_assessment(_mixed_report(), [])
    assert doc.properties["blast_radius_unassessed"] == 2
    assert doc.properties["blast_radius_coverage"] == "2 of 4 analysed"
    assert doc.properties["blast_radius_review_required"] is True


def test_narrative_summary_never_implies_a_clean_bill_of_health():
    """A no-findings result over a partial corpus must not read as 'no impact'."""
    from autopilot.assessment import narrative_summary

    cat = _catalog(
        Query(query_id="q_safe", sql="SELECT amount FROM sales.orders", platform="snowflake"),
        Query(query_id="q_jinja", sql=JINJA_SQL, platform="dbt"),
    )
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))
    assert report.counts()["breaks"] == 0 and report.counts()["degrades"] == 0
    summary = narrative_summary(report)
    assert "REVIEW REQUIRED" in summary
    assert "could NOT be assessed" in summary
    assert "1 of 2" in summary or "1 of 2 analysed" in summary


def test_planner_gives_every_unassessed_consumer_a_manual_review_step():
    """2e: an UNKNOWN consumer becomes a manual-review step — omitting it would
    imply no work is needed."""
    from autopilot.planner import build_plan, render_plan_md

    report = _mixed_report()
    plan = build_plan(report.change, report)

    unknown_names = {v.asset_name or v.query_id for v in report.unknown}
    step_names = {s.asset_name for s in plan.ordered_steps}
    assert unknown_names <= step_names, (
        f"unassessed consumers missing from the plan: {unknown_names - step_names}"
    )
    for s in plan.ordered_steps:
        if s.asset_name in unknown_names:
            assert "manual review" in s.action
            assert "could not be assessed" in s.action

    assert plan.risk_level.endswith("among assessed")
    assert any("REVIEW REQUIRED" in n for n in plan.notes)
    assert any("Coverage:" in n for n in plan.notes)

    md = render_plan_md(plan)
    assert "manual review" in md


def test_planner_stays_derived_only_with_unknowns():
    """2e guard: adding UNKNOWN steps must not introduce fabricated effort/timing."""
    import re

    from autopilot.planner import build_plan, render_plan_md

    md = render_plan_md(build_plan(_mixed_report().change, _mixed_report()))
    forbidden = re.findall(
        r"\b\d+\s*(?:hour|hours|hr|hrs|day|days|week|weeks|sprint)\b|\b\d+\s*%|"
        r"confidence[:=]\s*\d+", md, re.I)
    assert not forbidden, f"planner fabricated effort/timeline tokens: {forbidden}"


def test_html_report_surfaces_unassessed_and_coverage():
    """2e: the report must show coverage as its own dimension."""
    from autopilot.report_html import render_html

    html = render_html(_mixed_report())
    assert "UNKNOWN" in html
    assert "Unassessed" in html
    assert "2 of 4 analysed" in html
    assert "CRITICAL among assessed" in html or "among assessed" in html


def test_pr_comment_surfaces_review_required():
    """2e: the PR comment must tell a reviewer not to auto-apply."""
    from autopilot.report_pr import render_pr_comment

    md = render_pr_comment(_mixed_report())
    assert "REVIEW REQUIRED" in md
    assert "unassessed" in md.lower()
    assert "2 of 4 analysed" in md


def test_zero_coverage_reports_no_risk_level_at_all():
    """Edge case: if NOTHING could be assessed, quoting any risk level would be a
    number over an empty evidence set. Say we cannot assess it instead."""
    from autopilot.assessment import narrative_summary

    cat = _catalog(Query(query_id="q_jinja", sql=JINJA_SQL, platform="dbt"))
    report = compute_impact(cat, ChangeSpec.parse("sales.orders", "promotion_id", "drop"))
    assert report.coverage()["analysed"] == 0

    summary = narrative_summary(report)
    assert "UNABLE TO ASSESS" in summary
    assert "REVIEW REQUIRED" in summary
    # Must NOT present a reassuring level over zero evidence.
    assert "Risk among assessed: LOW" not in summary
    assert "Risk: LOW" not in summary
