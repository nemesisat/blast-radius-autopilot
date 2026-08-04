"""Tests for the reports: self-contained HTML (B11), CI-style PR comment + a real
local-git PR (B12)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autopilot.catalog import load_catalog
from autopilot.fixgen import generate_fixes
from autopilot.impact import compute_impact
from autopilot.report_html import render_html
from autopilot.report_pr import open_local_pr, render_pr_comment
from autopilot.schema import ChangeSpec

EX = Path(__file__).resolve().parents[1] / "examples" / "showcase-ecommerce"


@pytest.fixture
def report():
    catalog = load_catalog(EX / "catalog.json")
    return compute_impact(catalog, ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop"))


@pytest.fixture
def fixes(report):
    catalog = load_catalog(EX / "catalog.json")
    return generate_fixes(catalog, report.change, report, EX)


def test_html_is_self_contained_and_complete(report, fixes):
    html = render_html(report, fixes)
    assert html.strip().startswith("<!doctype html>")
    assert "<svg" in html                        # the lineage graph
    # no external network references (allow the W3C xmlns and the local placeholder url)
    external = html.count("http://") + html.count("https://")
    external -= html.count("http://www.w3")
    external -= html.count("blast-radius-autopilot.local")
    assert external == 0
    for tok in ["BREAKS", "DEGRADES", "SAFE", "Change risk", "CRITICAL", "customer_zip", "rpt_orders_by_region"]:
        assert tok in html


def test_html_colors_pair_with_glyphs(report, fixes):
    html = render_html(report, fixes)
    # status colours are always shown with a glyph label, never colour alone
    assert "#d03b3b" in html and "✕" in html      # breaks
    assert "#fab219" in html                        # degrades
    assert "#0ca30c" in html and "✓" in html       # safe


def test_pr_comment_has_badge_table_and_diff(report, fixes):
    md = render_pr_comment(report, fixes)
    assert "Blast Radius Autopilot" in md
    assert "CRITICAL" in md
    assert "```diff" in md and "customer_zip" in md
    assert "Reviewer checklist" in md
    assert "| Impact | Consumer | Team | Uses column | Runs |" in md


def test_open_local_pr_branches_applies_and_comments(tmp_path, report, fixes):
    repo = tmp_path / "dbt_repo"
    (repo / fixes[0].path).parent.mkdir(parents=True)
    (repo / fixes[0].path).write_text(fixes[0].original_sql)

    info = open_local_pr(repo, report, fixes)
    assert info["branch"].startswith("blast-radius/")
    assert info["applied"] == [fixes[0].path]
    assert Path(info["comment_path"]).exists()
    # the fix is committed on the new branch and the column is gone
    assert "customer_zip" not in (repo / fixes[0].path).read_text()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert branch == info["branch"]
    assert info["commit"]
