"""Write-back tests: dry-run plans the intended mutations without touching a
catalog, and the approve-before-write / require-review gate queues instead of
writing for regulated data."""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.assessment import build_assessment
from autopilot.catalog import load_catalog
from autopilot.impact import compute_impact
from autopilot.schema import ChangeSpec
from autopilot.writeback import WriteBack, plan_mutations

EX = Path(__file__).resolve().parents[1] / "examples" / "showcase-ecommerce"


@pytest.fixture
def report():
    catalog = load_catalog(EX / "catalog.json")
    return compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))


def test_plan_includes_all_write_tools(report):
    doc = build_assessment(report, [])
    muts = plan_mutations(report, doc)
    tools = {m.tool for m in muts}
    assert {"add_structured_properties", "add_tags", "save_document", "update_description"} <= tools
    # One structured-property write carries the risk + counts.
    sp = next(m for m in muts if m.tool == "add_structured_properties")
    assert sp.payload["blast_radius_status"] == "pending-change"
    assert sp.payload["blast_radius_breaks"] == 6   # B15: filter-only refs break on a drop
    # B15: coverage travels into the catalog alongside the verdict.
    assert sp.payload["blast_radius_unassessed"] == 0
    assert sp.payload["blast_radius_coverage"] == "10 of 10 analysed"
    # B17.1: so does the count of references we could not attribute — and it is the
    # reason this fully-parsed catalog still requires a human.
    assert sp.payload["blast_radius_ambiguous"] == 1
    assert sp.payload["blast_radius_review_required"] is True


def test_impacted_assets_get_tagged(report):
    doc = build_assessment(report, [])
    muts = plan_mutations(report, doc)
    tag_targets = {m.target_urn for m in muts if m.tool == "add_tags"}
    # The dbt model + Looker/PowerBI consumers that break/degrade are tagged.
    assert any("rpt_orders_by_region" in t for t in tag_targets)


@pytest.fixture
def clean_report():
    """A fully-resolved report (no unassessed, no ambiguous), so the auto-write path
    is reachable and the dry-run accounting is visible."""
    catalog = load_catalog(EX / "catalog.json")
    catalog.queries = [q for q in catalog.queries if q.query_id != "q_adhoc_ambiguous_zip"]
    report = compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))
    assert report.review_required() is False, report.counts()
    return report


def test_unverified_run_queues_and_writes_nothing(clean_report, capsys, tmp_path):
    """B19.3: complete coverage is not permission. With no verification there is nothing
    proven, so every mutation queues with `not_verified` — the dry-run/auto-write
    accounting for a genuinely verified PASS is covered in tests/test_approval.py."""
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, doc = wb.run(clean_report, [])
    out = capsys.readouterr().out
    assert "QUEUE for review (not_verified)" in out
    assert res.queued_for_review and not res.planned
    assert res.written == [] and res.failed == []
    assert res.queue_reason_line() == "not_verified"
    assert res.reconciles()
    assert "0 written (auto)" in out and "0 written (human-approved)" in out
    assert doc.title.startswith("Blast Radius Assessment")
    # An unverified run gets no approval manifest either: there is no verdict to
    # approve against. The route forward is `--verify`, not a signature.
    assert res.manifest_path is None


def test_require_review_queues_everything(report, capsys, tmp_path):
    wb = WriteBack(dry_run=True, require_review=True, assessment_dir=tmp_path,
                   manifest_dir=tmp_path)
    res, _ = wb.run(report, [])
    out = capsys.readouterr().out
    assert "QUEUE for review" in out
    assert res.queued_for_review and not res.written     # gate: nothing auto-written
    assert res.planned == []                             # queued, not merely unattempted
    assert res.reconciles()
