"""Tests for the differentiated core: contradiction detection, evidence-bound
abstention, and health bucketing.

    PYTHONPATH=src python -m pytest -q
"""

from necromancer.evidence import Evidence
from necromancer.health import Health, classify, coverage, leaderboard
from necromancer.investigator import detect_contradictions, investigate


# --- zombie / contradiction detection -------------------------------------- #
def test_source_mismatch_zombie():
    ev = Evidence(
        urn="urn:1", name="fct_revenue",
        current_description="Revenue sourced from Oracle ERP.",
        lineage_sources=["snowflake.raw_billing"], query_count=340, downstream_count=2,
        schema_fields=["revenue"],
    )
    kinds = {c.kind for c in detect_contradictions(ev)}
    assert "source_mismatch" in kinds
    assert investigate(ev).is_zombie


def test_false_deprecation_zombie():
    ev = Evidence(
        urn="urn:2", name="dim_customer_legacy",
        current_description="Deprecated, do not use.",
        lineage_sources=["snowflake.raw_customers"], query_count=120, downstream_count=3,
        schema_fields=["customer_id"],
    )
    kinds = {c.kind for c in detect_contradictions(ev)}
    assert "false_deprecation" in kinds


def test_stale_column_zombie():
    ev = Evidence(
        urn="urn:3", name="t",
        current_description="Keyed on `old_id` from the legacy load.",
        schema_fields=["new_id", "value"], lineage_sources=["snowflake.x"],
    )
    kinds = {c.kind for c in detect_contradictions(ev)}
    assert "stale_column" in kinds


def test_consistent_description_has_no_contradiction():
    ev = Evidence(
        urn="urn:4", name="dim_date",
        current_description="Standard date dimension.",
        lineage_sources=["dbt.stg_date"], schema_fields=["date_key"], query_count=60,
    )
    assert detect_contradictions(ev) == []


# --- evidence-bound abstention (anti-hallucination) ------------------------ #
def test_abstains_when_evidence_thin():
    ev = Evidence(urn="urn:5", name="mystery_blob")  # nothing but a name
    inv = investigate(ev)
    assert inv.action == "abstain"
    assert inv.confidence == "none"


def test_writes_when_strongly_corroborated():
    ev = Evidence(
        urn="urn:6", name="dim_product",
        lineage_sources=["snowflake.raw_products", "dbt.stg_products"],
        schema_fields=["product_id", "category"], sibling_terms=["Product"],
    )
    inv = investigate(ev)
    assert inv.evidence_strength >= 3
    assert inv.action == "write"


def test_documented_and_contradicted_goes_to_review_not_overwrite():
    ev = Evidence(
        urn="urn:7", name="stg_marketing_spend",
        current_description="Loaded from Salesforce.",
        lineage_sources=["s3.marketing_raw"], schema_fields=["campaign"], query_count=3,
    )
    assert investigate(ev).action == "review"


# --- health bucketing + leaderboard ---------------------------------------- #
def _classify(ev):
    return classify(ev, investigate(ev)).status


def test_health_buckets():
    critical = Evidence(urn="c", name="x", lineage_sources=["snowflake.raw"],
                        downstream_count=4, query_count=200, schema_fields=["a"])  # heavy + undocumented
    forgotten = Evidence(urn="f", name="y", lineage_sources=["snowflake.raw"],
                         schema_fields=["a"], sibling_terms=["T"])  # undocumented, low use
    healthy = Evidence(urn="h", name="z", current_description="Clean.",
                       lineage_sources=["dbt.s"], schema_fields=["a"], query_count=10)
    zombie = Evidence(urn="rev", name="w", current_description="From Oracle.",
                      lineage_sources=["snowflake.raw"], schema_fields=["a"], query_count=2)

    assert _classify(critical) == Health.CRITICAL
    assert _classify(forgotten) == Health.FORGOTTEN
    assert _classify(healthy) == Health.HEALTHY
    assert _classify(zombie) == Health.NEEDS_REVIEW


def test_leaderboard_orders_worst_first_and_coverage():
    evs = [
        Evidence(urn="h", name="z", current_description="Clean.", lineage_sources=["dbt.s"],
                 schema_fields=["a"], query_count=10),
        Evidence(urn="c", name="x", lineage_sources=["snowflake.raw"], downstream_count=4,
                 query_count=200, schema_fields=["a"]),
    ]
    results = [classify(e, investigate(e)) for e in evs]
    ordered = leaderboard(results)
    assert ordered[0].status == Health.CRITICAL      # worst first
    assert ordered[-1].status == Health.HEALTHY
    assert coverage(results)["assets"] == 2
