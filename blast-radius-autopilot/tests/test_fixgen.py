"""Tests for mechanical fix generation: the rewritten SQL is valid, drops/renames
the right column, and the diff actually applies."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import sqlglot

from autopilot.catalog import load_catalog
from autopilot.fixgen import generate_fix
from autopilot.schema import ChangeSpec

EX = Path(__file__).resolve().parents[1] / "examples" / "showcase-ecommerce"


@pytest.fixture
def catalog():
    return load_catalog(EX / "catalog.json")


@pytest.fixture
def dbt_asset(catalog):
    return next(a for a in catalog.assets if a.dbt_path)


def test_drop_removes_column_from_projection(catalog, dbt_asset):
    change = ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop")
    fx = generate_fix(catalog, change, dbt_asset, EX)
    assert fx is not None and fx.applicable
    assert "customer_zip" not in fx.new_sql
    assert "order_id" in fx.new_sql and "amount" in fx.new_sql   # siblings preserved
    sqlglot.parse_one(fx.new_sql, read="snowflake")             # valid SQL
    assert fx.diff and fx.changed


def test_rename_updates_reference(catalog, dbt_asset):
    change = ChangeSpec.parse("analytics.fct_orders", "customer_zip", "rename", new_name="postal_code")
    fx = generate_fix(catalog, change, dbt_asset, EX)
    assert fx is not None and fx.applicable
    assert "postal_code" in fx.new_sql
    assert "customer_zip" not in fx.new_sql


def test_generated_diff_applies_with_git(tmp_path, catalog, dbt_asset):
    # Stage the model in a throwaway git repo and prove the diff applies cleanly.
    repo = tmp_path / "repo"
    (repo / dbt_asset.dbt_path).parent.mkdir(parents=True)
    original = (EX / dbt_asset.dbt_path).read_text()
    (repo / dbt_asset.dbt_path).write_text(original)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)

    change = ChangeSpec.parse("analytics.fct_orders", "customer_zip", "drop")
    fx = generate_fix(catalog, change, dbt_asset, repo)
    (repo / "fix.patch").write_text(fx.diff)

    check = subprocess.run(["git", "apply", "--check", "fix.patch"], cwd=repo, capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    subprocess.run(["git", "apply", "fix.patch"], cwd=repo, check=True)
    assert "customer_zip" not in (repo / dbt_asset.dbt_path).read_text()
