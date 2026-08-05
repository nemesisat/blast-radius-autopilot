"""B21 — Overnight Catalog Sweep.

The per-change loop, generalised to the whole catalog: enumerate every candidate column
change, run the existing impact -> fixgen -> verify chain on each, and emit a ranked ledger.

FIVE RULES, and every test here is one of them:

    1. READ-ONLY. A sweep NEVER writes to DataHub — not gated, not queued, not at all. It is
       an assessment pass over a catalog, and an assessment that can mutate the thing it
       assesses is a different and much more dangerous tool.
    2. Same semantics as everywhere. PASS is the same sixteen-clause PASS; UNKNOWN is never
       counted as safe; nothing is inflated into a break. The sweep classifies, it does not
       re-decide.
    3. Resilient. One candidate raising must not abort the other N-1. It becomes an error row.
    4. Isolated. The real tree is never touched and no temp workspace survives the sweep.
    5. Ordered by the EXISTING fragility ranking — the riskiest columns first, because that is
       the order a human would want to read the ledger in.

All fixtures are synthetic.
"""

from __future__ import annotations

import itertools
import subprocess
import tempfile
from pathlib import Path

import pytest

from autopilot.fragility import fragility_leaderboard
from autopilot.schema import Asset, Catalog, Dataset, Query

# --- fixtures ------------------------------------------------------------------

ORDERS = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.orders,PROD)",
    name="orders", sql_name="analytics.orders", platform="snowflake",
    schema={"order_id": "NUMBER", "amount": "NUMBER", "customer_zip": "TEXT",
            "unused_note": "TEXT"},
)

DBT_REL = "models/rpt_orders.sql"
DBT_SQL = """-- rpt_orders
SELECT
    o.order_id,
    o.amount
FROM analytics.orders o
"""

# customer_zip appears ONLY in a WHERE clause. Dropping it makes this statement error, so it
# is a BREAK, not a degrade (B15). No mechanical fix rewrites a predicate (B4), so nothing
# can auto-fix it -> it is a landmine.
WHERE_ONLY_SQL = "SELECT o.order_id FROM analytics.orders o WHERE o.customer_zip = '94110'"

# Unrendered dbt Jinja: the parser cannot read it, so every verdict over this corpus is
# incomplete. UNKNOWN, never SAFE.
UNPARSEABLE_SQL = "SELECT * FROM {{ ref('orders') }} WHERE {% if x %}amount{% endif %} > 0"


def _clean_catalog() -> Catalog:
    """Fully parseable. `unused_note` is referenced by nothing at all."""
    return Catalog(
        name="sweep-clean",
        datasets=[ORDERS],
        queries=[
            Query(query_id="q_dbt", sql=DBT_SQL, platform="dbt", team="analytics-eng", runs=12),
            Query(query_id="q_where", sql=WHERE_ONLY_SQL, platform="looker",
                  team="bi", runs=7),
        ],
        assets=[
            Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.rpt_orders,PROD)",
                  name="rpt_orders", type="dbt_model", platform="dbt",
                  defining_query_id="q_dbt", dbt_path=DBT_REL),
            Asset(urn="urn:li:dashboard:(looker,zip_lookup)", name="ZIP Lookup",
                  type="looker_dashboard", platform="looker", defining_query_id="q_where"),
        ],
        sql_dialect="snowflake",
    )


def _broken_catalog() -> Catalog:
    """Carries a consumer whose SQL will not parse, so coverage can never be complete."""
    cat = _clean_catalog()
    cat.queries.append(Query(query_id="q_jinja", sql=UNPARSEABLE_SQL, platform="dbt",
                             team="data-eng", runs=3))
    cat.assets.append(
        Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.jinja,PROD)",
              name="jinja_model", type="dbt_model", platform="dbt",
              defining_query_id="q_jinja"))
    return cat


_REPO_SEQ = itertools.count()


def _repo(tmp_path: Path) -> Path:
    """A git repo holding the dbt model, so fixgen + verify have something real to patch.

    A fresh directory per call: two tests take both the `clean` and `broken` fixtures at once,
    and a second `git init` in the same directory would find nothing to commit.
    """
    repo = tmp_path / f"repo{next(_REPO_SEQ)}"
    (repo / "models").mkdir(parents=True, exist_ok=True)
    (repo / DBT_REL).write_text(DBT_SQL)
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=repo, check=True)
    return repo


@pytest.fixture
def clean(tmp_path):
    return _clean_catalog(), _repo(tmp_path)


@pytest.fixture
def broken(tmp_path):
    return _broken_catalog(), _repo(tmp_path)


# ==============================================================================
# Rule 5 — one entry per column, in fragility order
# ==============================================================================

def test_b21_sweep_produces_one_entry_per_column(clean):
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)

    expected = {(ds.name, col) for ds in catalog.datasets for col in ds.schema}
    got = {(e.dataset, e.column) for e in res.entries}
    assert got == expected, f"missing {expected - got}, extra {got - expected}"
    assert len(res.entries) == len(expected) == 4
    assert res.columns_assessed == 4
    assert res.datasets_scanned == 1


def test_b21_entries_are_ordered_by_the_existing_fragility_ranking(clean):
    """Reuse, not reimplementation: the order must BE fragility's order."""
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)

    fragility_order = [(r.dataset, r.column) for r in fragility_leaderboard(catalog)]
    sweep_order = [(e.dataset, e.column) for e in res.entries]
    assert sweep_order == fragility_order


def test_b21_sweep_limit_assesses_exactly_n_candidates(clean):
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo, limit=2)

    assert len(res.entries) == 2
    assert res.columns_assessed == 2
    # ...and they are the two riskiest, not an arbitrary two.
    fragility_order = [(r.dataset, r.column) for r in fragility_leaderboard(catalog)][:2]
    assert [(e.dataset, e.column) for e in res.entries] == fragility_order
    assert res.candidates_total == 4, "the total must still report what exists"


# ==============================================================================
# Rule 2 — same semantics: safe is proven, UNKNOWN is never safe
# ==============================================================================

def test_b21_column_with_zero_references_is_verified_safe(clean):
    """`unused_note` is referenced by nothing that parses. Dropping it is provably safe, and
    no patch is needed — so the ledger must say safe AND say why, not imply a patch was
    verified when none existed."""
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)
    e = next(x for x in res.entries if x.column == "unused_note")

    assert e.bucket == "verified_safe", (e.bucket, e.reasons)
    assert e.breaks == 0 and e.degrades == 0 and e.unknown == 0
    assert e.coverage_complete is True
    # The distinction that keeps this honest: nothing was patched, so nothing was verified.
    assert e.basis == "no_references"
    assert e.patch_path is None
    assert res.by_bucket()["verified_safe"]


def test_b21_where_only_reference_is_a_landmine(clean):
    """A WHERE-only reference breaks on a drop (B15) and no mechanical fix rewrites a
    predicate (B4), so nothing can auto-fix it. That is exactly what a landmine is."""
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)
    e = next(x for x in res.entries if x.column == "customer_zip")

    assert e.breaks >= 1, e.reasons
    assert e.bucket == "landmine", (e.bucket, e.reasons, e.verdict)
    assert e.unknown == 0
    assert "ZIP Lookup" in " ".join(e.blocking_consumers) or e.blocking_consumers


def test_b21_parse_failure_lands_in_unassessed_never_safe(broken):
    """The single most important assertion in the file. A consumer we could not read is a
    blind spot; a sweep that files it under 'safe' would be worse than no sweep."""
    from autopilot.sweep import sweep

    catalog, repo = broken
    res = sweep(catalog, repo_root=repo)

    unassessed = res.by_bucket()["unassessed"]
    assert unassessed, "a parse failure must surface somewhere"
    for e in unassessed:
        assert e.unknown >= 1
        assert e.coverage_complete is False
        assert e.bucket != "verified_safe"

    # And NOTHING in this catalog may be called verified-safe, because every candidate is
    # assessed over a corpus with an unreadable consumer in it.
    assert res.by_bucket()["verified_safe"] == [], (
        "zero breaks over a partial corpus is never 'safe'"
    )


def test_b21_buckets_partition_the_entries(clean, broken):
    """Every entry is in exactly one bucket and the totals reconcile — the same discipline
    as the write-back counters (B17.4)."""
    from autopilot.sweep import sweep

    for catalog, repo in (clean, broken):
        res = sweep(catalog, repo_root=repo)
        by = res.by_bucket()
        assert set(by) == {"verified_safe", "needs_review", "landmine", "unassessed", "error"}
        total = sum(len(v) for v in by.values())
        assert total == len(res.entries) == res.columns_assessed
        seen = [id(e) for v in by.values() for e in v]
        assert len(seen) == len(set(seen)), "an entry appears in two buckets"


# ==============================================================================
# Rule 1 — READ-ONLY: zero write calls across a full sweep
# ==============================================================================

def test_b21_a_full_sweep_makes_zero_write_calls(clean, broken, monkeypatch):
    """Assert on the write layer itself, not on the absence of an import. Anything that
    reaches DataHub is a hard failure, including the gated/queued paths."""
    from autopilot import writeback as wb_mod
    from autopilot.sweep import sweep

    calls: list[str] = []

    def boom(name):
        def _f(*a, **k):
            calls.append(name)
            raise AssertionError(f"a sweep must never call {name}")
        return _f

    for attr in ("run", "approve", "_emit", "_emit_into", "_append_description",
                 "_add_tags", "_save_document", "_set_structured_properties",
                 "ensure_property_definitions", "_record_approval_audit"):
        monkeypatch.setattr(wb_mod.WriteBack, attr, boom(f"WriteBack.{attr}"), raising=False)
    monkeypatch.setattr(wb_mod, "plan_mutations", boom("plan_mutations"))

    # ...and the DataHub client may not even be constructed.
    import datahub.ingestion.graph.client as gc
    monkeypatch.setattr(gc.DataHubGraph, "__init__", boom("DataHubGraph.__init__"))

    for catalog, repo in (clean, broken):
        res = sweep(catalog, repo_root=repo)
        assert res.entries

    assert calls == [], f"sweep touched the write layer: {calls}"


def test_b21_sweep_result_exposes_no_write_affordance():
    """Structural: nothing in the sweep's own API offers a way to write. A read-only tool
    that grows a `--write` next month is no longer read-only, and this fails if it does."""
    import inspect
    import re

    from autopilot import sweep as sweep_mod

    FORBIDDEN = re.compile(r"write|emit|approve|mutat|apply", re.I)
    for name, fn in inspect.getmembers(sweep_mod, inspect.isfunction):
        if getattr(fn, "__module__", None) != sweep_mod.__name__:
            continue
        for param in inspect.signature(fn).parameters:
            assert not FORBIDDEN.search(param), f"sweep.{name} exposes '{param}'"

    src = inspect.getsource(sweep_mod)
    assert "WriteBack" not in src, "sweep must not reference the write layer at all"
    assert "plan_mutations" not in src


# ==============================================================================
# Rule 3 — one bad candidate must not abort the sweep
# ==============================================================================

def test_b21_a_raising_candidate_becomes_an_error_row_and_the_sweep_completes(clean,
                                                                             monkeypatch):
    from autopilot import sweep as sweep_mod

    catalog, repo = clean
    real = sweep_mod.verify_migration
    # `amount` is projected by the dbt model, so it DOES reach verification — a column with
    # no generated patch never calls verify, so patching it there would prove nothing.
    target_col = "amount"

    def flaky(change, *a, **k):
        if change.column == target_col:
            raise RuntimeError("synthetic explosion inside verification")
        return real(change, *a, **k)

    monkeypatch.setattr(sweep_mod, "verify_migration", flaky)

    res = sweep_mod.sweep(catalog, repo_root=repo)

    # Every candidate is still accounted for.
    assert len(res.entries) == 4
    errors = res.by_bucket()["error"]
    assert len(errors) == 1
    err = errors[0]
    assert err.column == target_col
    assert err.bucket == "error"
    assert "synthetic explosion" in err.error
    # ...and the others were assessed normally.
    assert any(e.bucket == "verified_safe" for e in res.entries)
    assert res.errors == 1


def test_b21_an_error_row_never_claims_a_verdict(clean, monkeypatch):
    """An error means we do not know. It must not borrow a verdict from anywhere."""
    from autopilot import sweep as sweep_mod

    catalog, repo = clean
    monkeypatch.setattr(sweep_mod, "verify_migration",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))

    res = sweep_mod.sweep(catalog, repo_root=repo)
    assert res.by_bucket()["error"]
    for e in res.by_bucket()["error"]:
        assert e.verdict in (None, "", "ERROR"), e.verdict
        assert e.bucket == "error"



def test_b21_a_failure_in_the_first_stage_is_also_contained(clean, monkeypatch):
    """Resilience must not depend on which stage broke. `compute_impact` runs for every
    candidate, so a failure there is the earliest one possible."""
    from autopilot import sweep as sweep_mod

    catalog, repo = clean
    real = sweep_mod.compute_impact

    def flaky(cat, change, *a, **k):
        if change.column == "customer_zip":
            raise ValueError("synthetic explosion inside impact analysis")
        return real(cat, change, *a, **k)

    monkeypatch.setattr(sweep_mod, "compute_impact", flaky)

    res = sweep_mod.sweep(catalog, repo_root=repo)

    assert len(res.entries) == 4, "the sweep must still cover every candidate"
    errs = res.by_bucket()["error"]
    assert [e.column for e in errs] == ["customer_zip"]
    assert "synthetic explosion inside impact analysis" in errs[0].error
    assert errs[0].verdict is None and errs[0].basis == ""
    # The counts stay at their zero defaults rather than being half-filled with junk.
    assert errs[0].breaks == 0 and errs[0].coverage == ""
    assert res.reconciles()

# ==============================================================================
# Rule 4 — isolation: real tree untouched, no temp workspaces left behind
# ==============================================================================

def test_b21_isolation_real_tree_untouched_and_no_temp_dirs_leak(clean):
    from autopilot.sweep import sweep

    catalog, repo = clean
    before_sql = (repo / DBT_REL).read_text()
    tmp_root = Path(tempfile.gettempdir())
    before_dirs = {p.name for p in tmp_root.iterdir()} if tmp_root.exists() else set()

    res = sweep(catalog, repo_root=repo)
    assert res.entries

    assert (repo / DBT_REL).read_text() == before_sql, "the real model was modified"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                            capture_output=True, text=True, check=True)
    assert status.stdout.strip() == "", f"real repo is dirty: {status.stdout}"

    after_dirs = {p.name for p in tmp_root.iterdir()} if tmp_root.exists() else set()
    leaked = [d for d in (after_dirs - before_dirs) if "verify" in d.lower()
              or "sweep" in d.lower()]
    assert leaked == [], f"temp workspaces left behind: {leaked}"


# ==============================================================================
# The ledger
# ==============================================================================

def test_b21_ledger_header_totals_are_real(clean):
    from autopilot.report_sweep import render_sweep_md
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)
    md = render_sweep_md(res)

    assert f"{res.datasets_scanned}" in md
    assert f"{res.columns_assessed}" in md
    assert res.duration_seconds >= 0
    # The duration must be reported, and as a real measured number.
    assert "duration" in md.lower() or "elapsed" in md.lower()
    # Every bucket that has entries is named in the ledger.
    for bucket, entries in res.by_bucket().items():
        if entries:
            assert bucket.replace("_", " ") in md.lower() or bucket in md


def test_b21_ledger_renders_html_and_json_without_inventing_numbers(clean):
    import json

    from autopilot.report_sweep import render_sweep_html, sweep_json
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)

    html = render_sweep_html(res)
    assert html.lstrip().startswith("<!doctype html")
    assert "sweep" in html.lower()

    blob = json.loads(json.dumps(sweep_json(res)))
    assert blob["columns_assessed"] == res.columns_assessed == len(blob["entries"])
    assert blob["datasets_scanned"] == res.datasets_scanned
    assert set(blob["totals"]) == {"verified_safe", "needs_review", "landmine",
                                   "unassessed", "error"}
    assert sum(blob["totals"].values()) == res.columns_assessed


def test_b21_every_entry_with_a_patch_records_where_it_is(clean):
    """The ledger promises each row links to its patch. A row claiming a fix without a path
    to it is a claim a reviewer cannot check."""
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)

    for e in res.entries:
        if e.patch_generated:
            assert e.patch_path, f"{e.column} claims a patch with no path"
            assert Path(e.patch_path).exists(), f"{e.patch_path} does not exist"
            assert Path(e.patch_path).read_text().strip(), "the patch file is empty"
        else:
            assert e.patch_path is None


def test_b21_a_verified_patch_is_marked_as_such(clean):
    """The other half of the honesty split: when a fix WAS generated and verification
    PASSed, the basis must say so — distinct from `no_references`."""
    from autopilot.sweep import sweep

    catalog, repo = clean
    res = sweep(catalog, repo_root=repo)

    # `amount` is projected by the dbt model, so a mechanical fix exists for it.
    e = next(x for x in res.entries if x.column == "amount")
    assert e.patch_generated is True, e.reasons
    if e.bucket == "verified_safe":
        assert e.basis == "verified_patch"
        assert e.verdict == "PASS"
