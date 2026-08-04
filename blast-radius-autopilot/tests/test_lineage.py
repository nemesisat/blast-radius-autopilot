"""Unit tests for the column-usage engine — the novel core.

Covers the four outcomes (select/filter/none/ambiguous), the RENAME vs DROP
severity split, star projections, and the WHERE/JOIN raw-scan gap closure.
"""

from __future__ import annotations

import pytest

from autopilot.lineage import analyze_query, raw_reference_scan
from autopilot.schema import Catalog, Dataset


@pytest.fixture
def catalog() -> Catalog:
    fct = Dataset(
        urn="urn:fct_orders",
        name="fct_orders",
        sql_name="analytics.fct_orders",
        platform="snowflake",
        schema={
            "order_id": "NUMBER",
            "customer_id": "NUMBER",
            "order_date": "DATE",
            "amount": "FLOAT",
            "customer_zip": "VARCHAR",
            "ship_state": "VARCHAR",
            "status": "VARCHAR",
        },
    )
    dim = Dataset(
        urn="urn:dim_customer",
        name="dim_customer",
        sql_name="analytics.dim_customer",
        platform="snowflake",
        schema={"customer_id": "NUMBER", "customer_zip": "VARCHAR", "customer_segment": "VARCHAR"},
    )
    return Catalog(name="t", datasets=[fct, dim], sql_dialect="snowflake")


@pytest.fixture
def fct(catalog) -> Dataset:
    return catalog.dataset_by_sql_name("analytics.fct_orders")


def u(catalog, fct, sql, col="customer_zip"):
    return analyze_query(sql, fct, col, catalog)


def test_projected_column_is_select(catalog, fct):
    r = u(catalog, fct, "SELECT customer_zip, SUM(amount) FROM analytics.fct_orders GROUP BY customer_zip")
    assert r.usage == "select"      # projection wins over the GROUP BY reference
    assert r.confidence == "high"


def test_derived_projection_is_select(catalog, fct):
    r = u(catalog, fct, "SELECT LEFT(customer_zip, 3) AS zip3 FROM analytics.fct_orders")
    assert r.usage == "select"


def test_qualified_projection_is_select(catalog, fct):
    r = u(catalog, fct, "SELECT o.order_id, o.customer_zip FROM analytics.fct_orders o WHERE o.status='complete'")
    assert r.usage == "select"
    assert r.confidence == "high"


def test_filter_only_where_is_filter(catalog, fct):
    r = u(catalog, fct, "SELECT ship_state, SUM(amount) FROM analytics.fct_orders WHERE customer_zip IS NOT NULL GROUP BY ship_state")
    assert r.usage == "filter"
    assert "where" in r.clauses


def test_join_only_is_filter(catalog, fct):
    r = u(
        catalog, fct,
        "SELECT c.customer_segment, SUM(f.amount) FROM analytics.fct_orders f "
        "JOIN analytics.dim_customer c ON f.customer_zip = c.customer_zip GROUP BY c.customer_segment",
    )
    # f.customer_zip is a JOIN-only reference on the target table -> filter
    # (B15: a resolved filter reference BREAKS on a drop — the JOIN would error)
    assert r.usage == "filter"
    assert "join" in r.clauses


def test_unreferenced_is_none(catalog, fct):
    r = u(catalog, fct, "SELECT order_date, COUNT(*) FROM analytics.fct_orders GROUP BY order_date")
    assert r.usage == "none"


def test_table_not_in_query_is_none(catalog, fct):
    r = u(catalog, fct, "SELECT customer_zip FROM analytics.dim_customer")
    assert r.usage == "none"      # customer_zip here belongs to dim_customer, not the target


def test_ambiguous_unqualified_is_low_confidence(catalog, fct):
    r = u(
        catalog, fct,
        "SELECT customer_zip FROM analytics.fct_orders f JOIN analytics.dim_customer c ON f.customer_id = c.customer_id",
    )
    assert r.usage == "select"
    assert r.confidence == "low"  # both tables provide customer_zip -> gated out of definite counts


def test_star_projection_is_star(catalog, fct):
    """B15: a bare `*` carries the column but never names it, so the statement still
    executes after a drop — its output shape just changes. Distinct from `select`."""
    r = u(catalog, fct, "SELECT * FROM analytics.fct_orders WHERE status = 'complete'")
    assert r.usage == "star"
    assert "select(*)" in r.clauses


def test_qualified_star_is_star(catalog, fct):
    r = u(catalog, fct, "SELECT o.* FROM analytics.fct_orders o JOIN analytics.dim_customer c ON o.customer_id=c.customer_id")
    assert r.usage == "star"


def test_explicit_projection_outranks_star(catalog, fct):
    """A star must not soften an explicit reference sitting alongside it."""
    r = u(catalog, fct, "SELECT *, customer_zip FROM analytics.fct_orders")
    assert r.usage == "select"


def test_raw_scan_catches_group_by_gap(catalog, fct):
    # customer_zip used ONLY in GROUP BY (not projected) — the documented parser gap.
    clauses = raw_reference_scan(
        "SELECT COUNT(*) FROM analytics.fct_orders GROUP BY customer_zip", fct, "customer_zip", catalog
    )
    assert "group" in clauses


def test_parse_error_is_its_own_state_not_none(catalog, fct):
    """B15: unparseable SQL must NOT collapse into "none". "none" is proof the column
    is untouched; a parse error is proof of nothing. Conflating them scored a Jinja dbt
    model SAFE while it referenced the column 4x (PROGRESS.md 2026-07-29)."""
    r = u(catalog, fct, "SELECT customer_zip FROM WHERE ORDER BADSQL(((")
    assert r.usage == "parse_error"
    assert r.usage != "none"
    assert r.confidence == "low"
    assert "parse_error" in r.note
    assert r.references is False        # we cannot claim a reference...
    assert r.assessable is False        # ...nor claim we assessed it


def test_other_column_unaffected(catalog, fct):
    r = analyze_query("SELECT customer_zip FROM analytics.fct_orders", fct, "amount", catalog)
    assert r.usage == "none"      # we asked about `amount`, query only uses customer_zip
