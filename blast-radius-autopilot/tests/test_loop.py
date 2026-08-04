"""B6 + B7 — the dataset-agnostic loop runs the SAME code across 5 very different
datasets, unchanged, and gates regulated ones for review."""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.loop import run_loop

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "loop.config.yaml"


@pytest.fixture(scope="module")
def results():
    return run_loop(CONFIG, write=False)


def test_loop_runs_all_five_datasets(results):
    names = {r.name for r in results}
    assert names == {
        "ecommerce-drop-zip",
        "nyc-taxi-drop-distance",
        "healthcare-rename-dx",
        "fiction-retail-drop-tier",
        "finance-rename-revenue",
    }


def test_every_dataset_finds_impact(results):
    # Each configured change breaks or degrades at least one real consumer.
    for r in results:
        assert r.counts["breaks"] + r.counts["degrades"] >= 1, r.name


def test_regulated_datasets_queue_for_review(results):
    by = {r.name: r for r in results}
    # Healthcare + finance are require_review -> everything queued, nothing written.
    for name in ("healthcare-rename-dx", "finance-rename-revenue"):
        assert by[name].require_review
        assert by[name].queued > 0 and by[name].written == 0
    # The ecommerce flagship is not regulated, but it carries one unattributable
    # column reference, so B17.1 queues it for a human anyway.
    ecom = by["ecommerce-drop-zip"]
    assert ecom.require_review is False
    assert ecom.counts["ambiguous"] == 1
    assert ecom.queued > 0 and ecom.written == 0


def test_loop_never_reports_a_dry_run_as_written(results):
    """B17.4: `run_loop(write=False)` touches no catalog, so every run must report
    0 written — and its buckets must add up to what it planned."""
    for r in results:
        assert r.dry_run is True
        assert r.written == 0, f"{r.name} reported writes during a dry run"
        assert r.failed == 0
        assert r.planned + r.queued + r.written + r.failed == r.total, r.name
        assert "0 written" in r.writeback_summary, r.writeback_summary


def test_each_dbt_model_gets_a_fix(results):
    # Every dataset here has one impacted dbt model that is auto-fixed.
    for r in results:
        assert r.fixes >= 1, r.name


def test_reports_written_when_out_dir(tmp_path):
    results = run_loop(CONFIG, write=False, out_dir=tmp_path)
    for r in results:
        assert Path(r.reports["html"]).exists()
        assert Path(r.reports["pr_comment"]).exists()
