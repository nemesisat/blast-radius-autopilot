"""B16 — Proof-Carrying Migrations: a generated fix is not trusted, it is VERIFIED.

The verifier applies the patch in an ISOLATED copy, re-parses every patched SQL file,
re-runs the SAME impact analyzer over the patched corpus, and compares before/after.

WHAT THIS PROVES (and only this): the patch applies cleanly, the patched SQL parses,
the diff stays in scope, and the recomputed column-level impact improved. It is STATIC
verification — no query is ever executed, no warehouse is touched, no data is read.
A PASS means "the analyzer can no longer find broken consumers", never "this was run".

Fail-closed is the load-bearing property: any UNKNOWN/unassessed consumer or incomplete
coverage CANNOT yield PASS, because the verifier re-runs the same analyzer whose blind
spots B15 made visible. Absence of evidence is not proof of safety.

All fixtures are synthetic.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

import pytest

from autopilot.impact import compute_impact
from autopilot.schema import Asset, Catalog, ChangeSpec, Dataset, Query
from autopilot.verify import VerificationResult, verify_migration

# --- fixtures ------------------------------------------------------------------

ORDERS = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.orders,PROD)",
    name="orders",
    sql_name="analytics.orders",
    platform="snowflake",
    schema={"order_id": "NUMBER", "customer_id": "NUMBER", "customer_zip": "TEXT",
            "amount": "NUMBER", "status": "TEXT"},
)

# Three dbt models that all project customer_zip -> all BREAK on a drop.
MODEL_A = "models/rpt_a.sql"
MODEL_B = "models/rpt_b.sql"
MODEL_C = "models/rpt_c.sql"

SQL_A = """-- rpt_a
SELECT
    o.order_id,
    o.customer_zip,
    o.amount
FROM analytics.orders o
WHERE o.status = 'complete'
"""
SQL_B = """-- rpt_b
SELECT
    o.customer_id,
    o.customer_zip,
    SUM(o.amount) AS total
FROM analytics.orders o
GROUP BY o.customer_id, o.customer_zip
"""
SQL_C = """-- rpt_c
SELECT
    o.order_id,
    o.customer_zip
FROM analytics.orders o
"""
# A model that does NOT touch customer_zip -> SAFE.
MODEL_SAFE = "models/rpt_safe.sql"
SQL_SAFE = """-- rpt_safe
SELECT
    o.order_id,
    o.amount
FROM analytics.orders o
"""

# Patched versions with customer_zip removed.
FIXED_A = SQL_A.replace("    o.customer_zip,\n", "")
FIXED_B = """-- rpt_b
SELECT
    o.customer_id,
    SUM(o.amount) AS total
FROM analytics.orders o
GROUP BY o.customer_id
"""
FIXED_C = """-- rpt_c
SELECT
    o.order_id
FROM analytics.orders o
"""


def _diff(path: str, before: str, after: str) -> str:
    """A unified diff `git apply` accepts."""
    d = difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=3,
    )
    return "".join(d)


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """A throwaway git repo with the given files committed."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


def _catalog(models: dict[str, str], extra_queries: list[Query] | None = None,
             extra_assets: list[Asset] | None = None,
             extra_datasets: list[Dataset] | None = None) -> Catalog:
    """Build a catalog whose queries mirror the on-disk dbt models.

    The link the verifier relies on: Asset.dbt_path -> Asset.defining_query_id.
    """
    queries, assets = [], []
    for rel, sql in models.items():
        name = Path(rel).stem
        qid = f"q_{name}"
        queries.append(Query(query_id=qid, sql=sql, platform="dbt", team="analytics-eng", runs=3))
        assets.append(Asset(urn=f"urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.{name},PROD)",
                            name=name, type="dbt_model", platform="dbt",
                            defining_query_id=qid, dbt_path=rel))
    queries += extra_queries or []
    assets += extra_assets or []
    return Catalog(name="synthetic-verify", datasets=[ORDERS, *(extra_datasets or [])],
                   queries=queries, assets=assets, sql_dialect="snowflake")


DROP_ZIP = ChangeSpec.parse("analytics.orders", "customer_zip", "drop")

# --- B17 fixtures ---------------------------------------------------------------
# B17.1: a SECOND table that also provides customer_zip. An unqualified reference
# across the join cannot be attributed to either table -> low confidence/ambiguous.
BONUS = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.bonus,PROD)",
    name="bonus",
    sql_name="analytics.bonus",
    platform="snowflake",
    schema={"id": "NUMBER", "customer_zip": "TEXT", "bonus_amount": "NUMBER"},
)
AMBIGUOUS_SQL = (
    "SELECT o.order_id\n"
    "FROM analytics.orders o\n"
    "JOIN analytics.bonus b ON o.order_id = b.id\n"
    "WHERE customer_zip IS NOT NULL\n"
)

# B17.2: a consumer that keeps executing but silently loses a field -> DEGRADES.
MODEL_STAR = "models/rpt_star.sql"
SQL_STAR = """-- rpt_star
SELECT *
FROM analytics.orders
"""

# B17.3: a patched .sql file the catalog knows nothing about -> unmappable.
MODEL_ORPHAN = "models/rpt_orphan.sql"
SQL_ORPHAN = """-- rpt_orphan
SELECT 1 AS x
FROM analytics.orders
"""
FIXED_ORPHAN = """-- rpt_orphan
SELECT 1 AS x, 2 AS y
FROM analytics.orders
"""


def _before(catalog: Catalog):
    return compute_impact(catalog, DROP_ZIP)


def _git_status(repo: Path) -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()


# --- (a) clean fix across all breaking consumers -> PASS -----------------------

def test_a_clean_dbt_fix_eliminates_breaks_and_passes(tmp_path):
    models = {MODEL_A: SQL_A, MODEL_B: SQL_B, MODEL_C: SQL_C}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    assert before.counts()["breaks"] == 3, before.counts()
    assert before.counts()["unknown"] == 0

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _diff(MODEL_B, SQL_B, FIXED_B)
             + _diff(MODEL_C, SQL_C, FIXED_C))

    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert isinstance(res, VerificationResult)
    assert res.status == "PASS", f"expected PASS, got {res.status}: {res.reasons}"
    assert res.patch_applied is True
    assert res.parse_ok is True
    assert res.after["breaks"] == 0
    assert res.after["unknown"] == 0
    assert res.deltas()["breaks"] == -3
    assert "breaks_eliminated" in res.reasons
    assert res.passed is True
    # Every previously-breaking consumer improved.
    improved = {t.consumer for t in res.transitions if t.improved}
    assert improved == {"rpt_a", "rpt_b", "rpt_c"}
    assert not any(t.regressed for t in res.transitions)


def test_a_static_verification_never_claims_execution(tmp_path):
    """HONESTY: nothing in the result may imply a query was run."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    res = verify_migration(DROP_ZIP, _before(catalog),
                           _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=catalog)
    blob = " ".join([res.status, *res.reasons, *res.notes, res.method]).lower()
    # AFFIRMATIVE claims of execution only. The disclaimer legitimately contains
    # "executed" inside "no queries were executed", so each pattern excludes the
    # negated form rather than banning the word outright.
    for forbidden in [
        r"(?<!no )queries were executed",
        r"(?<!no )query was executed",
        r"executed successfully",
        r"successfully executed",
        r"(?<!not )ran the quer",
        r"\bwe ran\b",
        r"tested against",
        r"validated against",
        r"dry run against",
        r"runtime test",
    ]:
        assert not re.search(forbidden, blob), f"result implies execution: {forbidden!r}"
    assert res.method == "static"
    # ...and the disclaimer must actually be there.
    notes = " ".join(res.notes).lower()
    assert "no queries were executed" in notes
    assert "no warehouse was contacted" in notes
    assert "static verification only" in notes


# --- (b) patch that does not apply -> FAIL, real tree untouched ---------------

def test_b_non_applying_patch_fails_and_leaves_tree_untouched(tmp_path):
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)

    # A diff whose context does not match what is on disk.
    bogus = _diff(MODEL_A, "SELECT something_else FROM nowhere\n", "SELECT nothing\n")
    res = verify_migration(DROP_ZIP, before, bogus, repo, catalog=catalog)

    assert res.status == "FAIL", f"expected FAIL, got {res.status}"
    assert res.patch_applied is False
    assert "patch_apply_failed" in res.reasons
    assert _git_status(repo) == "", "the real repo must be untouched"
    assert (repo / MODEL_A).read_text() == SQL_A, "the real file must be unchanged"


def test_b_empty_patch_fails(tmp_path):
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    res = verify_migration(DROP_ZIP, _before(catalog), "", repo, catalog=catalog)
    assert res.status == "FAIL"
    assert "no_patch_provided" in res.reasons


# --- (c) patch producing unparseable SQL -> FAIL ------------------------------

def test_c_unparseable_patched_sql_fails(tmp_path):
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)

    broken = "-- rpt_a\nSELECT FROM WHERE ORDER BADSQL((( \n"
    patch = _diff(MODEL_A, SQL_A, broken)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.status == "FAIL", f"expected FAIL, got {res.status}: {res.reasons}"
    assert res.patch_applied is True          # it applied; the RESULT is invalid
    assert res.parse_ok is False
    assert "patched_sql_unparseable" in res.reasons
    assert any(MODEL_A in e for e in res.parse_errors)
    assert _git_status(repo) == ""


# --- (d) breaks reduced but not eliminated -> REVIEW_REQUIRED -----------------

def test_d_partial_fix_is_review_required(tmp_path):
    models = {MODEL_A: SQL_A, MODEL_B: SQL_B, MODEL_C: SQL_C}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    assert before.counts()["breaks"] == 3

    # Fix only two of the three.
    patch = _diff(MODEL_A, SQL_A, FIXED_A) + _diff(MODEL_B, SQL_B, FIXED_B)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.status == "REVIEW_REQUIRED", f"got {res.status}: {res.reasons}"
    assert res.after["breaks"] == 1
    assert res.deltas()["breaks"] == -2
    assert "breaks_remaining" in res.reasons
    assert "breaks_eliminated" not in res.reasons
    assert res.passed is False


# --- (e) THE FAIL-CLOSED TEST: zero breaks but an UNKNOWN -> not PASS ---------

def test_e_unknown_consumer_blocks_pass_even_with_zero_breaks(tmp_path):
    """The most important property. The verifier re-runs the SAME analyzer, so a
    consumer it cannot read is a blind spot, not a clean result. Zero breaks over an
    incomplete corpus must never be reported as PASS."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    # An extra consumer whose SQL cannot be parsed (unrendered dbt Jinja).
    jinja = Query(query_id="q_jinja", sql="SELECT * FROM {{ ref('orders') }} WHERE customer_zip = '1'",
                  platform="dbt", team="data-eng", runs=9)
    jinja_asset = Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.jinja_model,PROD)",
                        name="jinja_model", type="dbt_model", platform="dbt",
                        defining_query_id="q_jinja")
    catalog = _catalog(models, extra_queries=[jinja], extra_assets=[jinja_asset])
    before = _before(catalog)
    assert before.counts()["unknown"] == 1

    patch = _diff(MODEL_A, SQL_A, FIXED_A)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.after["breaks"] == 0, "the only parseable breaking consumer was fixed"
    assert res.after["unknown"] == 1
    assert res.status == "REVIEW_REQUIRED", (
        f"zero breaks + an unassessed consumer must NOT be PASS, got {res.status}"
    )
    assert res.status != "PASS"
    assert res.passed is False
    assert "unknown_consumers_present" in res.reasons
    assert "coverage_incomplete" in res.reasons
    assert res.coverage_after["unassessed"] == 1


def test_e_incomplete_coverage_alone_blocks_pass(tmp_path):
    """Same property via the other route: a consumer with no SQL definition at all."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    no_sql = Asset(urn="urn:li:dataset:(urn:li:dataPlatform:powerbi,synthetic.kpis,PROD)",
                   name="Essential KPI Measures", type="powerbi_report", platform="powerbi",
                   defining_query_id=None)
    catalog = _catalog(models, extra_assets=[no_sql])
    before = _before(catalog)

    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=catalog)
    assert res.after["breaks"] == 0
    assert res.status == "REVIEW_REQUIRED", f"got {res.status}: {res.reasons}"
    assert "coverage_incomplete" in res.reasons


# --- (f) non-dbt consumers still needing manual work -> REVIEW_REQUIRED -------

def test_f_manual_work_on_non_dbt_consumers_is_review_required(tmp_path):
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    # A Looker dashboard that breaks and has no dbt file to patch.
    looker = Query(query_id="q_looker", sql="SELECT customer_zip, COUNT(*) FROM analytics.orders GROUP BY customer_zip",
                   platform="looker", team="growth", runs=12)
    looker_asset = Asset(urn="urn:li:dataset:(urn:li:dataPlatform:looker,synthetic.zip_dash,PROD)",
                         name="Sales by ZIP", type="looker_dashboard", platform="looker",
                         defining_query_id="q_looker")   # no dbt_path -> not mechanically fixable
    catalog = _catalog(models, extra_queries=[looker], extra_assets=[looker_asset])
    before = _before(catalog)
    assert before.counts()["breaks"] == 2

    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=catalog)

    assert res.status == "REVIEW_REQUIRED", f"got {res.status}: {res.reasons}"
    assert res.after["breaks"] == 1
    assert "manual_work_remaining" in res.reasons
    assert "Sales by ZIP" in res.manual_work_remaining


# --- (g) a previously-SAFE consumer regressing -> FAIL ------------------------

def test_g_regressing_a_safe_consumer_fails(tmp_path):
    """A fix that drags an unaffected consumer into the blast radius is worse than
    no fix, even if the headline break count fell."""
    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    assert before.counts()["breaks"] == 1
    assert before.counts()["safe"] == 1

    # Fixes rpt_a but "helpfully" adds customer_zip to the previously-safe model.
    regressed_safe = SQL_SAFE.replace("    o.amount\n", "    o.amount,\n    o.customer_zip\n")
    patch = _diff(MODEL_A, SQL_A, FIXED_A) + _diff(MODEL_SAFE, SQL_SAFE, regressed_safe)

    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.status == "FAIL", f"expected FAIL, got {res.status}: {res.reasons}"
    assert "safe_consumer_regressed" in res.reasons
    regressed = [t for t in res.transitions if t.regressed]
    assert [t.consumer for t in regressed] == ["rpt_safe"]
    assert regressed[0].before == "SAFE"
    assert regressed[0].after == "BREAKS"


# --- (h) isolation: the real repo is never mutated ----------------------------

@pytest.mark.parametrize("scenario", ["clean", "non_applying", "unparseable", "regressing"])
def test_h_real_repo_is_never_mutated(tmp_path, scenario):
    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    originals = {rel: (repo / rel).read_text() for rel in models}

    patches = {
        "clean": _diff(MODEL_A, SQL_A, FIXED_A),
        "non_applying": _diff(MODEL_A, "totally different\n", "other\n"),
        "unparseable": _diff(MODEL_A, SQL_A, "SELECT FROM WHERE ((( \n"),
        "regressing": _diff(MODEL_SAFE, SQL_SAFE,
                            SQL_SAFE.replace("    o.amount\n", "    o.amount,\n    o.customer_zip\n")),
    }
    verify_migration(DROP_ZIP, before, patches[scenario], repo, catalog=catalog)

    assert _git_status(repo) == "", f"{scenario}: real repo dirty after verification"
    for rel, content in originals.items():
        assert (repo / rel).read_text() == content, f"{scenario}: {rel} was mutated"


def test_h_isolation_workspace_is_cleaned_up(tmp_path):
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    res = verify_migration(DROP_ZIP, _before(catalog),
                           _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=catalog)
    assert res.isolation_dir, "the isolation location should be recorded for the audit trail"
    assert not Path(res.isolation_dir).exists(), "the temp workspace must be removed"


# --- scope guard ---------------------------------------------------------------

def test_scope_violation_is_caught(tmp_path):
    """The diff must touch only files the fix is supposed to touch."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, {**models, "config/prod.yml": "secret: 1\n"})
    catalog = _catalog(models)
    before = _before(catalog)

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _diff("config/prod.yml", "secret: 1\n", "secret: 2\n"))
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A])

    assert res.scope_ok is False
    assert "scope_violation" in res.reasons
    assert res.status == "FAIL"
    assert any("config/prod.yml" in v for v in res.scope_violations)


# --- wiring: write-back gate, planner, reports (B16 steps 3-4) ----------------

def _pass_and_review_results(tmp_path):
    """Two real VerificationResults from the same fixtures: one PASS, one REVIEW."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    clean_cat = _catalog(models)
    passing = verify_migration(DROP_ZIP, _before(clean_cat),
                              _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=clean_cat)
    jinja = Query(query_id="q_jinja", sql="SELECT * FROM {{ ref('o') }} WHERE customer_zip = '1'",
                  platform="dbt", runs=4)
    jinja_asset = Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.jinja,PROD)",
                        name="jinja_model", type="dbt_model", platform="dbt",
                        defining_query_id="q_jinja")
    unk_cat = _catalog(models, extra_queries=[jinja], extra_assets=[jinja_asset])
    review = verify_migration(DROP_ZIP, _before(unk_cat),
                              _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=unk_cat)
    return (clean_cat, passing), (unk_cat, review)


def test_writeback_auto_applies_only_on_pass(tmp_path):
    """B16 gate: a PASS may auto-apply; REVIEW_REQUIRED/FAIL must not."""
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    (clean_cat, passing), (unk_cat, review) = _pass_and_review_results(tmp_path)
    assert passing.status == "PASS"
    assert review.status == "REVIEW_REQUIRED"

    before_clean = _before(clean_cat)
    muts = plan_mutations(before_clean, build_assessment(before_clean, [], verification=passing),
                          verification=passing)
    assert muts and all(m.auto for m in muts), "a verified-clean migration may auto-apply"

    before_unk = _before(unk_cat)
    muts = plan_mutations(before_unk, build_assessment(before_unk, [], verification=review),
                          verification=review)
    assert muts and all(not m.auto for m in muts), (
        "REVIEW_REQUIRED must queue every mutation for a human"
    )


def test_writeback_queues_on_verification_fail(tmp_path):
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    failed = verify_migration(DROP_ZIP, before, _diff(MODEL_A, "nope\n", "nah\n"),
                              repo, catalog=catalog)
    assert failed.status == "FAIL"
    muts = plan_mutations(before, build_assessment(before, [], verification=failed),
                          verification=failed)
    assert all(not m.auto for m in muts), "a FAILED verification must never auto-apply"


def test_verification_structured_properties(tmp_path):
    from autopilot.assessment import build_assessment

    (clean_cat, passing), _ = _pass_and_review_results(tmp_path)
    doc = build_assessment(_before(clean_cat), [], verification=passing)
    p = doc.properties
    assert p["blast_radius_verification_status"] == "PASS"
    assert p["blast_radius_verification_breaks_before"] == 1
    assert p["blast_radius_verification_breaks_after"] == 0
    assert p["blast_radius_verification_coverage"] == passing.coverage_after["line"]
    assert p["blast_radius_verification_method"] == "static"
    assert p["blast_radius_verified_at"]
    # The evidence must reach the document a human reads, with the scope disclaimer.
    assert "Migration verification (static)" in doc.markdown
    assert "no queries were executed" in doc.markdown.lower()


def test_assessment_doc_flags_non_passing_verification(tmp_path):
    from autopilot.assessment import build_assessment

    _, (unk_cat, review) = _pass_and_review_results(tmp_path)
    doc = build_assessment(_before(unk_cat), [], verification=review)
    assert "REVIEW_REQUIRED" in doc.markdown
    assert "must not" in doc.markdown.lower()


def test_planner_records_per_step_verification_state(tmp_path):
    from autopilot.planner import build_plan, render_plan_md

    _, (unk_cat, review) = _pass_and_review_results(tmp_path)
    before = _before(unk_cat)
    plan = build_plan(before.change, before, verification=review)

    states = {s.asset_name: s.verified for s in plan.ordered_steps}
    assert "jinja_model" in states
    assert "unassessed" in states["jinja_model"], states
    assert any("Static verification: REVIEW_REQUIRED" in n for n in plan.notes)
    assert any("No queries were executed" in n for n in plan.notes)
    md = render_plan_md(plan)
    assert "static verification:" in md


def test_planner_stays_derived_only_with_verification(tmp_path):
    """B16 must not smuggle fabricated effort/timeline into the plan."""
    from autopilot.planner import build_plan, render_plan_md

    _, (unk_cat, review) = _pass_and_review_results(tmp_path)
    before = _before(unk_cat)
    md = render_plan_md(build_plan(before.change, before, verification=review))
    forbidden = re.findall(
        r"\b\d+\s*(?:hour|hours|hr|hrs|day|days|week|weeks|sprint)\b|\b\d+\s*%|"
        r"confidence[:=]\s*\d+", md, re.I)
    assert not forbidden, f"planner fabricated tokens: {forbidden}"


def test_html_report_has_verification_section(tmp_path):
    from autopilot.report_html import render_html

    (clean_cat, passing), _ = _pass_and_review_results(tmp_path)
    html = render_html(_before(clean_cat), [], verification=passing)
    assert "Verification — proof-carrying migration" in html
    assert "PASS" in html
    assert "no queries were executed" in html.lower() or "No queries were executed" in html
    # The scope disclaimer is mandatory.
    assert "static" in html.lower()


def test_pr_comment_has_verification_verdict_and_deltas(tmp_path):
    from autopilot.report_pr import render_pr_comment

    _, (unk_cat, review) = _pass_and_review_results(tmp_path)
    md = render_pr_comment(_before(unk_cat), [], verification=review)
    assert "Migration verification (static)" in md
    assert "REVIEW REQUIRED" in md
    assert "| Metric | Before | After | Δ |" in md
    assert "no queries were executed" in md.lower()
    assert "Verification returned REVIEW_REQUIRED" in md


def test_reports_omit_verification_when_not_run(tmp_path):
    """--verify is opt-in: without it, no verification claims appear anywhere."""
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment

    models = {MODEL_A: SQL_A}
    _make_repo(tmp_path, models)
    before = _before(_catalog(models))
    html = render_html(before, [])
    md = render_pr_comment(before, [])
    assert "proof-carrying migration" not in html
    assert "Migration verification" not in md


# ==============================================================================
# B17 — closing the remaining false-PASS paths.
#
# Each block below reproduces a CONFIRMED false PASS: a run where the verifier
# reported PASS while a known consumer had not been confidently assessed. The
# governing rule is one sentence: a migration may PASS only when every known
# consumer is confidently assessed and no unresolved impact remains. Absence of
# evidence is never proof of safety.
# ==============================================================================

# --- B17.1: ambiguous references must block PASS -------------------------------

def _ambiguous_setup(tmp_path):
    """One breaking dbt model (patchable) + one consumer whose unqualified column
    reference could belong to either joined table.

    Reproduces the plan's verified false PASS:
        before: breaks 1, ambiguous 1
        after:  breaks 0, ambiguous 1   -> was PASS, must be REVIEW_REQUIRED
    """
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    amb = Query(query_id="q_ambiguous", sql=AMBIGUOUS_SQL, platform="snowflake",
                team="growth", runs=7)
    catalog = _catalog(models, extra_queries=[amb], extra_datasets=[BONUS])
    return repo, catalog


def test_b17_1_ambiguous_reference_forces_impact_review(tmp_path):
    """The impact report itself must fail closed on ambiguity: a reference we
    cannot attribute is unresolved impact, not a clean result."""
    _repo, catalog = _ambiguous_setup(tmp_path)
    report = _before(catalog)
    assert report.ambiguous, "fixture must produce an ambiguous consumer"
    assert report.counts()["ambiguous"] == 1
    assert report.counts()["breaks"] == 1
    assert report.review_required() is True
    assert report.auto_applicable() is False


def test_b17_1_ambiguous_reference_blocks_verification_pass(tmp_path):
    """THE FALSE PASS. Zero breaks after the patch, but one reference still cannot
    be attributed to a source table -> REVIEW_REQUIRED, never PASS."""
    repo, catalog = _ambiguous_setup(tmp_path)
    before = _before(catalog)
    assert before.counts()["breaks"] == 1
    assert before.counts()["ambiguous"] == 1

    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    assert res.after["breaks"] == 0
    assert res.after["ambiguous"] == 1
    assert res.status == "REVIEW_REQUIRED", (
        f"an unattributable reference must NOT be PASS, got {res.status}: {res.reasons}"
    )
    assert res.status != "PASS"
    assert res.passed is False
    assert "ambiguous_consumers_present" in res.reasons
    assert res.auto_applicable is False


def test_b17_1_ambiguous_is_distinct_from_unknown(tmp_path):
    """Ambiguous is its own state: the SQL PARSED, so it is not unassessed — but it
    is not safe and not a proven break either. It must never be inflated into a
    break, folded into UNKNOWN, or counted as safe."""
    _repo, catalog = _ambiguous_setup(tmp_path)
    c = _before(catalog).counts()
    assert c["ambiguous"] == 1
    assert c["unknown"] == 0, "a parsed-but-unattributable ref is not 'unassessed'"
    assert c["breaks"] == 1, "ambiguity must not be inflated into a break"
    assert c["safe"] == 0, "ambiguity must never be counted as safe"
    # ...and it does not distort the coverage line, which measures parseability.
    assert _before(catalog).coverage()["unassessed"] == 0


def test_b17_1_ambiguous_verification_queues_all_writeback(tmp_path):
    """The gate must reach write-back: nothing auto-applies while a reference is
    unattributed."""
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    repo, catalog = _ambiguous_setup(tmp_path)
    before = _before(catalog)
    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)
    assert res.status == "REVIEW_REQUIRED"

    muts = plan_mutations(before, build_assessment(before, [], verification=res),
                          verification=res)
    assert muts, "expected mutations to be planned"
    assert all(not m.auto for m in muts), (
        "an ambiguous verification must queue every mutation for a human"
    )


def test_b17_1_ambiguous_count_reaches_every_surface(tmp_path):
    """A gate the reader cannot see is not a gate."""
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment
    from autopilot.verify import render_verification_md, verification_json

    repo, catalog = _ambiguous_setup(tmp_path)
    before = _before(catalog)
    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    payload = verification_json(res)
    assert payload["after"]["ambiguous"] == 1
    assert "ambiguous_consumers_present" in payload["reasons"]
    assert payload["auto_applicable"] is False

    md = render_verification_md(res)
    assert "Ambiguous" in md
    assert "ambiguous_consumers_present" in md

    html = render_html(before, [], verification=res)
    assert "Ambiguous" in html

    pr = render_pr_comment(before, [], verification=res)
    assert "Ambiguous" in pr


# --- B17.2: remaining DEGRADES must block PASS ---------------------------------

def _degrades_setup(tmp_path):
    """One breaking dbt model (patchable) + one `SELECT *` consumer that keeps
    running but silently loses the dropped column.

    Reproduces the plan's verified false PASS:
        before: breaks 1, degrades 1
        after:  breaks 0, degrades 1   -> was PASS, must be REVIEW_REQUIRED
    """
    models = {MODEL_A: SQL_A, MODEL_STAR: SQL_STAR}
    repo = _make_repo(tmp_path, models)
    return repo, _catalog(models)


def test_b17_2_existing_degrade_blocks_pass(tmp_path):
    """THE FALSE PASS. A dropped column that a `SELECT *` still carries changes the
    consumer's output schema — a downstream contract can break on that."""
    repo, catalog = _degrades_setup(tmp_path)
    before = _before(catalog)
    assert before.counts()["breaks"] == 1
    assert before.counts()["degrades"] == 1

    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    assert res.after["breaks"] == 0
    assert res.after["degrades"] == 1
    assert res.status == "REVIEW_REQUIRED", (
        f"a remaining degradation must NOT be PASS, got {res.status}: {res.reasons}"
    )
    assert "degrades_remaining" in res.reasons
    assert res.auto_applicable is False


def test_b17_2_remaining_degrade_is_not_downgraded_to_fail(tmp_path):
    """Calibration matters as much as strictness. A pre-existing degradation the
    patch did not introduce is unresolved impact, not a broken patch — over-failing
    it would teach reviewers to ignore FAIL."""
    repo, catalog = _degrades_setup(tmp_path)
    res = verify_migration(DROP_ZIP, _before(catalog), _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)
    assert res.status != "FAIL", f"pre-existing degrade must not FAIL: {res.reasons}"
    assert res.status == "REVIEW_REQUIRED"
    assert "new_degrades" not in res.reasons, "this degrade was not introduced by the patch"
    assert res.regressions() == [], "nothing regressed — the degrade was already there"


def test_b17_2_new_degrade_is_a_failure(tmp_path):
    """The contrast case: a patch that DRAGS a clean consumer into DEGRADES made
    things worse and must FAIL, not merely ask for review."""
    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    assert before.counts()["safe"] == 1
    assert before.counts()["degrades"] == 0

    # Rewrites the previously-SAFE model to `SELECT *` -> it now carries the column.
    degraded_safe = "-- rpt_safe\nSELECT *\nFROM analytics.orders o\n"
    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _diff(MODEL_SAFE, SQL_SAFE, degraded_safe))
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.after["degrades"] == 1
    assert res.status == "FAIL", f"a NEW degrade must FAIL, got {res.status}: {res.reasons}"
    assert "new_degrades" in res.reasons


# --- B17.3: unmapped patched SQL must block PASS -------------------------------

def _unmapped_setup(tmp_path):
    """A patch that touches a .sql file the catalog cannot connect to any consumer.

    The verifier maps patched files through Asset.dbt_path -> defining_query_id ->
    Query. When that link is missing the patched file's effect on impact is NOT
    recomputed — so the recomputed blast radius is silently incomplete.
    """
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, {**models, MODEL_ORPHAN: SQL_ORPHAN})
    catalog = _catalog(models)          # deliberately does NOT know MODEL_ORPHAN
    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _diff(MODEL_ORPHAN, SQL_ORPHAN, FIXED_ORPHAN))
    return repo, catalog, patch


def test_b17_3_unmapped_patched_sql_blocks_pass(tmp_path):
    """THE FALSE PASS. Part of the patch was excluded from the recomputed impact,
    so the 'zero breaks' result does not cover the whole diff."""
    repo, catalog, patch = _unmapped_setup(tmp_path)
    before = _before(catalog)

    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_ORPHAN])

    assert res.scope_ok is True, "both files were declared in scope — this is a mapping gap"
    assert res.after["breaks"] == 0
    assert res.unmapped_files == [MODEL_ORPHAN], res.unmapped_files
    assert res.status == "REVIEW_REQUIRED", (
        f"an unmapped patched file must NOT be PASS, got {res.status}: {res.reasons}"
    )
    assert "patched_file_unmapped" in res.reasons
    assert res.auto_applicable is False


def test_b17_3_mapping_is_tracked_explicitly(tmp_path):
    """Coverage of the DIFF is tracked, not inferred: every patched .sql file is
    either mapped to a named query or listed as a gap."""
    repo, catalog, patch = _unmapped_setup(tmp_path)
    res = verify_migration(DROP_ZIP, _before(catalog), patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_ORPHAN])
    assert res.file_query_map == {MODEL_A: "q_rpt_a"}, res.file_query_map
    assert set(res.files_patched) == {MODEL_A, MODEL_ORPHAN}
    # Every patched SQL file is accounted for exactly once.
    assert (set(res.file_query_map) | set(res.unmapped_files)) == set(res.files_patched)


def test_b17_3_unmapped_files_are_named_in_every_output(tmp_path):
    """The reviewer must be told WHICH file was not recomputed, by name."""
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment
    from autopilot.verify import render_verification_md, verification_json

    repo, catalog, patch = _unmapped_setup(tmp_path)
    before = _before(catalog)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_ORPHAN])

    payload = verification_json(res)
    assert "unmapped_files" in payload
    assert payload["unmapped_files"] == [MODEL_ORPHAN]
    assert "file_query_map" in payload

    md = render_verification_md(res)
    assert "could not be mapped" in md
    assert MODEL_ORPHAN in md, "the unmapped file must be named in VERIFICATION.md"

    html = render_html(before, [], verification=res)
    assert MODEL_ORPHAN in html

    pr = render_pr_comment(before, [], verification=res)
    assert MODEL_ORPHAN in pr


# --- B17.4: truthful write-back accounting -------------------------------------

class _StubWriteBack:
    """A live-mode WriteBack with the DataHub SDK swapped out at the LOWEST level.

    The real `_emit()` dispatch is exercised deliberately: the defect being fixed is
    that `_emit()` swallowed its own exceptions, so a failed live mutation was still
    counted as written. Stubbing `_emit` itself would hide exactly that.
    """

    def __new__(cls, fail_tools=(), assessment_dir=None, manifest_dir=None):
        from autopilot.writeback import WriteBack

        obj = object.__new__(type("StubWB", (WriteBack,), dict(
            _append_description=lambda self, urn, footer: self._record("update_description", urn),
            _add_tags=lambda self, urn, tags: self._record("add_tags", urn),
            _save_document=lambda self, urn, title, content: self._record("save_document", urn),
            _set_structured_properties=lambda self, urn, props: self._record(
                "add_structured_properties", urn),
            _record=_record,
        )))
        obj.gms_url, obj.token, obj.dry_run, obj.require_review = "", "", False, False
        obj.assessment_dir = assessment_dir
        obj.manifest_dir = manifest_dir or assessment_dir
        obj._graph = None
        obj.fail_tools = set(fail_tools)
        obj.emitted = []
        return obj


def _record(self, tool: str, urn: str) -> None:
    if tool in self.fail_tools:
        raise RuntimeError(f"GMS rejected {tool} on {urn}: 422 unknown aspect version")
    self.emitted.append(f"{tool}:{urn}")


def _wb_report():
    """A fully-assessed report, so nothing is queued and the accounting is visible."""
    models = {MODEL_A: SQL_A}
    return _before(_catalog(models))


@pytest.fixture
def wb_pass(tmp_path):
    """A report plus a PASSing verification of it.

    B19.3 made a PASS the ONLY licence to auto-write, so every test below that needs
    the write path must supply a real one — an unverified run now queues, by design.
    """
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path / "wbrepo", models)
    catalog = _catalog(models)
    report = _before(catalog)
    v = verify_migration(DROP_ZIP, report, _diff(MODEL_A, SQL_A, FIXED_A),
                         repo, catalog=catalog)
    assert v.status == "PASS", v.reasons
    return report, v


@pytest.fixture
def wb_dir(tmp_path):
    """Somewhere disposable for the persisted assessment body (B18.3), so the tests
    never write into the project's real `out/`."""
    return tmp_path / "wb"


def test_b17_4_dry_run_reports_planned_not_written(capsys, wb_dir, wb_pass):
    """THE FALSE CLAIM. A dry run wrote nothing, so it may not report writes."""
    from autopilot.writeback import WriteBack

    report, v = wb_pass
    res, _doc = WriteBack(dry_run=True, assessment_dir=wb_dir).run(
        report, [], verification=v)
    out = capsys.readouterr().out

    assert res.total > 0
    assert len(res.planned) == res.total
    assert res.written == [], "a dry run writes nothing"
    assert res.failed == []
    assert res.queued_for_review == []
    assert "[dry-run] would apply" in out
    # A dry run may say "0 written" / "nothing was written" — both are true. What it
    # may never do is claim a nonzero write, or narrate a mutation in the past tense.
    assert not re.search(r"\b[1-9]\d*\s+written\b", out), (
        f"a dry run reported writes it did not perform:\n{out}"
    )
    assert "0 written" in out
    assert f"{res.total} planned" in out
    assert "[write]" not in out, f"a dry run must not use the live-write prefix:\n{out}"


def test_b17_4_successful_live_emit_counts_written(wb_dir, wb_pass):
    report, v = wb_pass
    wb = _StubWriteBack(assessment_dir=wb_dir)
    res, _doc = wb.run(report, [], verification=v)

    assert res.written and len(res.written) == res.total
    assert res.written == res.written_auto, "a verified PASS writes on the automatic path"
    assert res.planned == [], "nothing is merely 'planned' on a live run"
    assert res.failed == []
    assert len(wb.emitted) == res.total


def test_b17_4_failed_emit_is_not_counted_as_written(wb_dir, wb_pass):
    """A mutation that raises is FAILED. Counting it written is a lie about the
    catalog's state, and `_emit` must therefore stop swallowing its errors."""
    report, v = wb_pass
    wb = _StubWriteBack(fail_tools={"add_tags"}, assessment_dir=wb_dir)
    res, _doc = wb.run(report, [], verification=v)

    failed_ids = [f["mutation"] for f in res.failed]
    assert failed_ids, "the raising mutation must be recorded as failed"
    assert all(f.startswith("add_tags:") for f in failed_ids), failed_ids
    for fid in failed_ids:
        assert fid not in res.written
    # Each failure carries enough context to act on.
    for f in res.failed:
        assert f["tool"] == "add_tags"
        assert f["target_urn"]
        assert "GMS rejected" in f["error"]


def test_b17_4_partial_write_failure_is_reported_honestly(wb_dir, wb_pass):
    report, v = wb_pass
    wb = _StubWriteBack(fail_tools={"add_tags", "save_document"}, assessment_dir=wb_dir)
    res, _doc = wb.run(report, [], verification=v)

    n_tags = sum(1 for m in _planned_for(report, verification=v) if m.tool == "add_tags")
    n_docs = sum(1 for m in _planned_for(report, verification=v) if m.tool == "save_document")
    assert len(res.failed) == n_tags + n_docs
    assert len(res.written) == res.total - (n_tags + n_docs)
    assert res.written, "the surviving mutations still counted as written"


def _planned_for(report, assessment_dir=None, verification=None):
    """Counting helper. `assessment_dir` keeps the persisted assessment body out of the
    project's real `out/` when a test only needs the mutation COUNT."""
    import tempfile

    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    return plan_mutations(report, build_assessment(report, []), verification=verification,
                          assessment_dir=assessment_dir or tempfile.mkdtemp())


def test_b17_4_totals_reconcile_on_every_path(tmp_path, wb_dir, wb_pass):
    """Every planned mutation lands in exactly one bucket, on every path: dry-run,
    clean live, partially-failed live, queued-for-review, and unverified."""
    from autopilot.writeback import WriteBack

    report, v = wb_pass
    total = len(_planned_for(report, verification=v))

    runs = {
        "dry_run": WriteBack(dry_run=True, assessment_dir=wb_dir).run(
            report, [], verification=v)[0],
        "live_clean": _StubWriteBack(assessment_dir=wb_dir).run(
            report, [], verification=v)[0],
        "live_partial": _StubWriteBack(fail_tools={"add_tags"}, assessment_dir=wb_dir).run(
            report, [], verification=v)[0],
        "queued": WriteBack(dry_run=True, require_review=True, assessment_dir=wb_dir).run(
            report, [], verification=v)[0],
        # B19.3 — the unverified path is an outcome too, and it must reconcile.
        "unverified": WriteBack(dry_run=True, assessment_dir=wb_dir).run(report, [])[0],
    }
    for label, res in runs.items():
        assert res.total == total, label
        assert res.reconciles(), f"{label}: {res.counts()} does not reconcile with {res.total}"
        assert sum(res.counts()[k] for k in
                   ("written_auto", "written_human_approved", "queued_for_review",
                    "failed", "planned", "skipped")) == res.total, label
        assert res.counts()["written"] == (res.counts()["written_auto"]
                                           + res.counts()["written_human_approved"]), label

    # A live run has no "planned" residue: written + queued + failed == planned total.
    live = runs["live_partial"]
    assert len(live.written) + len(live.queued_for_review) + len(live.failed) == live.total
    assert runs["unverified"].queued_for_review and not runs["unverified"].planned


def test_b17_4_cli_summary_prints_the_real_counters(tmp_path, capsys, wb_dir, wb_pass):
    """The CLI summary line must be derived from the counters, not from intent — and
    since B19.6 it always names BOTH write paths, so a zero is as explicit as a count."""
    from autopilot.writeback import WriteBack

    report, v = wb_pass
    res, _doc = WriteBack(dry_run=True, assessment_dir=wb_dir).run(
        report, [], verification=v)
    assert res.summary_line() == (
        f"{res.total} planned, 0 written (auto), 0 written (human-approved), "
        f"0 queued, 0 failed, 0 skipped"), res.summary_line()

    live, _doc = _StubWriteBack(fail_tools={"add_tags"}, assessment_dir=wb_dir).run(
        report, [], verification=v)
    n_tags = sum(1 for m in _planned_for(report, verification=v) if m.tool == "add_tags")
    assert f"{n_tags} failed" in live.summary_line()
    assert f"{live.total - n_tags} written (auto)" in live.summary_line()
    assert "0 written (human-approved)" in live.summary_line()
    assert "0 planned" in live.summary_line()


def test_b17_4_assessment_and_reports_carry_writeback_counters(tmp_path, wb_dir, wb_pass):
    """The numbers a human reads must be the numbers the run produced."""
    from autopilot.assessment import build_assessment
    from autopilot.writeback import WriteBack

    report, v = wb_pass
    res, _doc = WriteBack(dry_run=True, assessment_dir=wb_dir).run(
        report, [], verification=v)
    doc = build_assessment(report, [], writeback=res)
    assert f"{res.total} planned" in doc.markdown
    assert "0 written" in doc.markdown
    assert doc.properties["blast_radius_writeback_written"] == 0
    assert doc.properties["blast_radius_writeback_planned"] == res.total
    assert doc.properties["blast_radius_writeback_applied_by"] == "none"


# --- the guard against over-tightening: PASS must stay reachable ---------------

def test_b17_pass_conjunction_is_still_reachable(tmp_path):
    """Every new gate satisfied at once -> PASS. If this test ever fails, PASS has
    become unreachable and the gates are wrong, not the fixture."""
    models = {MODEL_A: SQL_A, MODEL_B: SQL_B, MODEL_C: SQL_C}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _diff(MODEL_B, SQL_B, FIXED_B)
             + _diff(MODEL_C, SQL_C, FIXED_C))
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    # Assert each clause of the conjunction independently, so a future failure says
    # WHICH gate closed rather than just "not PASS".
    assert res.patch_applied is True
    assert res.parse_ok is True
    assert res.scope_ok is True
    assert res.after["breaks"] == 0
    assert res.after["degrades"] == 0
    assert res.after["unknown"] == 0
    assert res.after["ambiguous"] == 0
    assert res.coverage_after["unassessed"] == 0
    assert res.unmapped_files == []
    assert res.manual_work_remaining == []
    assert res.residual_references == []
    assert res.regressions() == []
    assert res.status == "PASS", f"PASS became unreachable: {res.reasons}"
    assert res.auto_applicable is True


def test_b17_pass_still_auto_applies_write_back(tmp_path):
    """...and a PASS still flows through the write-back gate."""
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)
    assert res.status == "PASS", res.reasons
    muts = plan_mutations(before, build_assessment(before, [], verification=res),
                          verification=res)
    assert muts and all(m.auto for m in muts)


# ==============================================================================
# B18 — final correctness round: the change itself, destructive diffs, and what
# actually lands in the catalog.
#
# B17 hardened the verdict once the change and the diff were both well-formed.
# B18 covers the two cases where they are not: a change that does not resolve
# against the catalog at all, and a diff that DELETES or MOVES a consumer's
# defining SQL rather than editing it. Same governing rule: a migration may PASS
# only when every known consumer is confidently assessed and no unresolved impact
# remains. A consumer whose file vanished is not a consumer that became safe.
# ==============================================================================

# --- B18.1: the change must resolve before any verdict means anything ---------

MISSING_DATASET = ChangeSpec.parse("analytics.no_such_table", "customer_zip", "drop")
MISSING_COLUMN = ChangeSpec.parse("analytics.orders", "no_such_column", "drop")


def test_b18_1_unresolvable_target_dataset_fails(tmp_path):
    """THE FALSE PASS. Nothing was assessed because the target was never found, so
    every count is 0 — which the gates read as 'no impact remains'."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = compute_impact(catalog, MISSING_DATASET)
    assert before.target_urn is None, "fixture must fail to resolve the dataset"
    assert before.counts()["queries_total"] == 0

    res = verify_migration(MISSING_DATASET, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    assert res.status != "PASS", (
        f"a change whose target is not in the catalog must never PASS, got {res.status}"
    )
    assert res.status == "FAIL", f"got {res.status}: {res.reasons}"
    assert "target_not_found" in res.reasons
    assert res.auto_applicable is False
    assert res.target_resolved is False
    # The reviewer must be told WHICH name did not resolve.
    assert "analytics.no_such_table" in res.target_problem, res.target_problem


def test_b18_1_unresolvable_target_is_named_in_every_output(tmp_path):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment
    from autopilot.verify import render_verification_md, verification_json

    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = compute_impact(catalog, MISSING_DATASET)
    res = verify_migration(MISSING_DATASET, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    payload = verification_json(res)
    assert payload["target_resolved"] is False
    assert "analytics.no_such_table" in payload["target_problem"]
    for text in (render_verification_md(res),
                 render_html(before, [], verification=res),
                 render_pr_comment(before, [], verification=res)):
        assert "analytics.no_such_table" in text


def test_b18_1_missing_column_fails_with_its_own_reason(tmp_path):
    """A resolved TABLE with an unresolved COLUMN is a different mistake from an
    unresolved table, and conflating them would send a reviewer to the wrong place."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = compute_impact(catalog, MISSING_COLUMN)
    assert before.target_urn is not None, "the dataset itself resolves fine"

    res = verify_migration(MISSING_COLUMN, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    assert res.status != "PASS"
    assert res.status == "FAIL", f"got {res.status}: {res.reasons}"
    assert "column_not_found" in res.reasons
    assert "target_not_found" not in res.reasons, "the two reasons must stay distinct"
    assert "no_such_column" in res.target_problem
    assert res.auto_applicable is False


def test_b18_1_resolving_target_is_unaffected(tmp_path):
    """Guard: the new gates must not fire on a change that resolves normally."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    res = verify_migration(DROP_ZIP, _before(catalog), _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)
    assert res.target_resolved is True
    assert res.target_problem == ""
    assert "target_not_found" not in res.reasons
    assert "column_not_found" not in res.reasons
    assert res.status == "PASS", res.reasons


# --- B18.2: a diff that deletes or moves a consumer's SQL ---------------------

MODEL_MOVED = "models/rpt_safe_moved.sql"


def _delete_diff(path: str, content: str) -> str:
    """A git diff that DELETES `path`. `difflib` cannot express this."""
    lines = content.splitlines(keepends=True)
    body = "".join(f"-{ln}" if ln.endswith("\n") else f"-{ln}\n" for ln in lines)
    return (f"diff --git a/{path} b/{path}\n"
            f"deleted file mode 100644\n"
            f"--- a/{path}\n"
            f"+++ /dev/null\n"
            f"@@ -1,{len(lines)} +0,0 @@\n"
            f"{body}")


def _rename_diff(old: str, new: str) -> str:
    """A pure git rename (no content change)."""
    return (f"diff --git a/{old} b/{new}\n"
            f"similarity index 100%\n"
            f"rename from {old}\n"
            f"rename to {new}\n")


def _rename_with_content_diff(old: str, new: str, before: str, after: str) -> str:
    """A git rename that also edits the file."""
    hunk = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{old}", tofile=f"b/{new}", n=3,
    ))
    return (f"diff --git a/{old} b/{new}\n"
            f"similarity index 50%\n"
            f"rename from {old}\n"
            f"rename to {new}\n"
            f"{hunk}")


def test_b18_2_deleting_a_consumers_sql_file_blocks_pass(tmp_path):
    """THE FALSE PASS. The break count fell to zero while a *different* consumer's
    defining SQL was deleted out from under the catalog. A deleted `+++ /dev/null`
    file never appeared in `files_patched` at all, so nothing saw it."""
    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    assert before.counts()["breaks"] == 1
    assert before.counts()["safe"] == 1

    patch = _diff(MODEL_A, SQL_A, FIXED_A) + _delete_diff(MODEL_SAFE, SQL_SAFE)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.patch_applied is True
    assert res.after["breaks"] == 0
    assert res.deleted_files == [MODEL_SAFE], res.deleted_files
    assert res.status != "PASS", (
        f"deleting a consumer's defining SQL must never PASS, got {res.status}"
    )
    assert "patched_file_deleted" in res.reasons
    assert res.auto_applicable is False


def test_b18_2_deleted_file_is_named_in_every_output(tmp_path):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment
    from autopilot.verify import render_verification_md, verification_json

    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    patch = _diff(MODEL_A, SQL_A, FIXED_A) + _delete_diff(MODEL_SAFE, SQL_SAFE)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    payload = verification_json(res)
    assert payload["deleted_files"] == [MODEL_SAFE]
    for text in (render_verification_md(res),
                 render_html(before, [], verification=res),
                 render_pr_comment(before, [], verification=res)):
        assert MODEL_SAFE in text, "the deleted path must be named"


def test_b18_2_renaming_a_consumers_sql_file_blocks_pass(tmp_path):
    """A pure rename produces no `+++ b/...` line for the OLD path and no hunk at
    all, so the move was completely invisible: the catalog's `dbt_path` now dangles
    and the verifier reported a clean bill of health."""
    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)

    patch = _diff(MODEL_A, SQL_A, FIXED_A) + _rename_diff(MODEL_SAFE, MODEL_MOVED)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_SAFE, MODEL_MOVED])

    assert res.patch_applied is True
    assert res.after["breaks"] == 0
    assert res.renamed_files == [(MODEL_SAFE, MODEL_MOVED)], res.renamed_files
    assert res.status != "PASS", (
        f"moving a consumer's defining SQL must never PASS, got {res.status}"
    )
    assert "patched_file_renamed" in res.reasons
    assert res.auto_applicable is False


def test_b18_2_renamed_paths_are_named_in_every_output(tmp_path):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment
    from autopilot.verify import render_verification_md, verification_json

    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    patch = _diff(MODEL_A, SQL_A, FIXED_A) + _rename_diff(MODEL_SAFE, MODEL_MOVED)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_SAFE, MODEL_MOVED])

    payload = verification_json(res)
    assert payload["renamed_files"] == [[MODEL_SAFE, MODEL_MOVED]]
    for text in (render_verification_md(res),
                 render_html(before, [], verification=res),
                 render_pr_comment(before, [], verification=res)):
        assert MODEL_SAFE in text and MODEL_MOVED in text


def test_b18_2_rename_to_a_mapped_path_is_recomputed_not_skipped(tmp_path):
    """The gate must not be a blanket block. When the rename's NEW path is a path the
    catalog maps to a query, the moved file's content is the consumer's new
    definition — it must be re-analysed, and the run stays eligible to PASS."""
    # The catalog records the consumer at its NEW location; the repo still has the
    # file at the old one, and the diff is the move that reconciles them.
    old_path = "staging/rpt_a_wip.sql"
    new_path = "models/rpt_a.sql"
    repo = _make_repo(tmp_path, {old_path: SQL_A})
    catalog = Catalog(
        name="synthetic-verify", datasets=[ORDERS],
        queries=[Query(query_id="q_rpt_a", sql=SQL_A, platform="dbt",
                       team="analytics-eng", runs=3)],
        assets=[Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.rpt_a,PROD)",
                      name="rpt_a", type="dbt_model", platform="dbt",
                      defining_query_id="q_rpt_a", dbt_path=new_path)],
        sql_dialect="snowflake",
    )
    before = compute_impact(catalog, DROP_ZIP)
    assert before.counts()["breaks"] == 1

    patch = _rename_with_content_diff(old_path, new_path, SQL_A, FIXED_A)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[old_path, new_path])

    assert res.renamed_files == [(old_path, new_path)]
    # RECOMPUTED, not skipped: the moved content drove the new impact result.
    assert res.file_query_map == {new_path: "q_rpt_a"}, res.file_query_map
    assert res.after["breaks"] == 0
    assert res.unmapped_files == []
    assert "patched_file_renamed" not in res.reasons, (
        "a rename whose new path is mapped and recomputed is not a coverage gap"
    )
    assert res.status == "PASS", f"got {res.status}: {res.reasons}"


def test_b18_2_every_diff_path_lands_in_exactly_one_bucket(tmp_path):
    """The partition invariant, extended. Every path the diff touches is accounted
    for exactly once across mapped / unmapped / deleted / renamed."""
    models = {MODEL_A: SQL_A, MODEL_SAFE: SQL_SAFE, MODEL_B: SQL_B}
    repo = _make_repo(tmp_path, {**models, MODEL_ORPHAN: SQL_ORPHAN})
    catalog = _catalog(models)
    before = _before(catalog)

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)                       # mapped + recomputed
             + _diff(MODEL_ORPHAN, SQL_ORPHAN, FIXED_ORPHAN)      # unmapped
             + _delete_diff(MODEL_SAFE, SQL_SAFE)                 # deleted
             + _rename_diff(MODEL_B, MODEL_MOVED))                # renamed
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_ORPHAN, MODEL_SAFE,
                                           MODEL_B, MODEL_MOVED])

    buckets = {
        "mapped": set(res.file_query_map),
        "unmapped": set(res.unmapped_files),
        "deleted": set(res.deleted_files),
        "renamed": {old for old, _new in res.renamed_files},
    }
    assert buckets["mapped"] == {MODEL_A}
    assert buckets["unmapped"] == {MODEL_ORPHAN}
    assert buckets["deleted"] == {MODEL_SAFE}
    assert buckets["renamed"] == {MODEL_B}
    # Disjoint...
    seen: set[str] = set()
    for name, paths in buckets.items():
        overlap = seen & paths
        assert not overlap, f"{name} overlaps an earlier bucket: {overlap}"
        seen |= paths
    # ...and complete: every .sql path the diff touched is in exactly one bucket.
    assert seen == set(res.diff_sql_paths), (seen, res.diff_sql_paths)
    assert res.status != "PASS"
    for code in ("patched_file_unmapped", "patched_file_deleted", "patched_file_renamed"):
        assert code in res.reasons


# --- B18.3: what we CLAIM lands in the catalog must be what lands ------------

def test_b18_3_institutional_memory_stores_only_a_link_and_the_claim_says_so():
    """DataHub OSS's `institutionalMemory` aspect holds `url` + `description` — there
    is NO document-body field. So the assessment MARKDOWN cannot live in that aspect,
    and nothing in the product may claim it does."""
    from datahub.metadata.schema_classes import InstitutionalMemoryMetadataClass

    stored = {f.name for f in InstitutionalMemoryMetadataClass.RECORD_SCHEMA.fields}
    assert stored == {"url", "description", "createStamp", "updateStamp", "settings"}, stored
    assert not {"content", "body", "text", "document"} & stored, (
        "if a body field ever appears, revisit this and store the assessment properly"
    )


def test_b18_3_assessment_body_is_persisted_and_its_location_named(tmp_path):
    """The full assessment must be retrievable *somewhere*, and the mutation that
    links to it must name that somewhere."""
    from autopilot.assessment import build_assessment
    from autopilot.writeback import plan_mutations

    models = {MODEL_A: SQL_A}
    catalog = _catalog(models)
    report = _before(catalog)
    doc = build_assessment(report, [])
    out_dir = tmp_path / "artifacts"
    muts = plan_mutations(report, doc, assessment_dir=out_dir)

    link = next(m for m in muts if m.tool == "save_document")
    body_path = Path(link.payload["body_path"])
    assert body_path.exists(), "the assessment body must be written where it can live"
    assert body_path.read_text() == doc.markdown, "the FULL assessment, not a summary"
    # The mutation carries only what the aspect can actually hold, plus a pointer.
    assert set(link.payload) >= {"url", "description", "body_path"}
    assert link.payload["url"].startswith("file://") or "://" in link.payload["url"]
    assert str(body_path) in link.payload["url"]
    assert str(body_path) in link.summary, link.summary
    assert "link" in link.summary.lower()


def test_b18_3_no_surface_claims_the_catalog_stores_the_document_body(tmp_path):
    """HONESTY: 'the full Impact Assessment is written back to the catalog' is a claim
    the OSS aspect cannot support. Every surface must say link + title."""
    import autopilot.writeback as wb_mod
    from autopilot.writeback import WriteBack

    models = {MODEL_A: SQL_A}
    report = _before(_catalog(models))
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path / "artifacts")
    res, doc = wb.run(report, [])

    blob = " ".join([
        wb_mod.__doc__ or "", doc.markdown,
        *(m.summary for m in wb_mod.plan_mutations(report, doc,
                                                  assessment_dir=tmp_path / "artifacts")),
    ]).lower()
    for forbidden in [
        r"save[s]? the full impact assessment (?:in|into|to) the catalog",
        r"full impact assessment document\b(?!.{0,80}link)",
        r"stores the (?:assessment|document) (?:body|content|markdown) in datahub",
    ]:
        assert not re.search(forbidden, blob), f"unsupported persistence claim: {forbidden!r}"
    # ...and the true statement is present, with the location.
    assert "institutional memory" in blob or "institutionalmemory" in blob
    assert "artifacts" in blob, "the body's location must be stated"


# ==============================================================================
# B19.1 + B19.2 — the last two ways the verifier could be wrong about its own inputs:
# a dataset whose schema it cannot see, and a diff whose paths it cannot read.
# ==============================================================================

# --- B19.1: an unknown schema is not proof of anything ------------------------

ORDERS_NO_SCHEMA = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.orders,PROD)",
    name="orders",
    sql_name="analytics.orders",
    platform="snowflake",
    schema={},          # the catalog knows the table exists and nothing about its columns
)


def _schemaless_setup(tmp_path):
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    catalog.datasets = [ORDERS_NO_SCHEMA]
    return repo, catalog


def test_b19_1_unknown_schema_forces_review_not_pass(tmp_path):
    """THE FALSE PASS. The dataset resolves, the column reference is fixed, breaks go to
    zero — but we never knew the table's columns, so we cannot claim the migration is
    complete. Absence of evidence is not proof of safety."""
    repo, catalog = _schemaless_setup(tmp_path)
    before = compute_impact(catalog, DROP_ZIP)

    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    assert res.schema_known is False
    assert res.status == "REVIEW_REQUIRED", f"got {res.status}: {res.reasons}"
    assert "schema_unknown" in res.reasons
    assert res.auto_applicable is False


def test_b19_1_unknown_schema_is_not_a_missing_column(tmp_path):
    """B18 FAILs a column that is provably absent. An EMPTY schema proves nothing, so it
    must not borrow that verdict — a FAIL says 'this change is wrong', and we do not
    know that."""
    repo, catalog = _schemaless_setup(tmp_path)
    res = verify_migration(DROP_ZIP, compute_impact(catalog, DROP_ZIP),
                           _diff(MODEL_A, SQL_A, FIXED_A), repo, catalog=catalog)

    assert res.status != "FAIL", "an unknown schema is not evidence the change is wrong"
    assert res.status != "PASS", "...but it is not evidence the change is complete either"
    assert "column_not_found" not in res.reasons
    assert "target_not_found" not in res.reasons
    assert res.target_resolved is True, "the DATASET resolved; only its schema is unknown"
    # And the reviewer is told which dataset's schema is missing.
    assert "analytics.orders" in res.target_problem, res.target_problem


def test_b19_1_unknown_schema_is_named_in_every_output(tmp_path):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment
    from autopilot.verify import render_verification_md, verification_json

    repo, catalog = _schemaless_setup(tmp_path)
    before = compute_impact(catalog, DROP_ZIP)
    res = verify_migration(DROP_ZIP, before, _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)

    assert verification_json(res)["schema_known"] is False
    for text in (render_verification_md(res),
                 render_html(before, [], verification=res),
                 render_pr_comment(before, [], verification=res)):
        assert "schema" in text.lower()
        assert "analytics.orders" in text


def test_b19_1_populated_schema_is_unaffected(tmp_path):
    """Guard: the gate must only fire when the schema is genuinely empty."""
    models = {MODEL_A: SQL_A}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    res = verify_migration(DROP_ZIP, _before(catalog), _diff(MODEL_A, SQL_A, FIXED_A),
                           repo, catalog=catalog)
    assert res.schema_known is True
    assert "schema_unknown" not in res.reasons
    assert res.status == "PASS", res.reasons


# --- B19.2: git quotes paths, and we were reading the quotes -------------------

UNICODE_MODEL = "models/résumé.sql"
SPACED_MODEL = "models/my report.sql"
SPACED_MOVED = "models/renamed café.sql"
SQL_UNICODE = """-- résumé
SELECT
    o.order_id,
    o.customer_zip
FROM analytics.orders o
"""
SQL_SPACED = """-- my report
SELECT
    o.order_id
FROM analytics.orders o
"""


def _git_quoted_delete(path_octal: str, content: str) -> str:
    """A deletion exactly as real `git diff` emits it with core.quotepath=true — the
    quotes wrap the `a/` prefix too."""
    lines = content.splitlines(keepends=True)
    body = "".join(f"-{ln}" if ln.endswith("\n") else f"-{ln}\n" for ln in lines)
    return (f'diff --git "a/{path_octal}" "b/{path_octal}"\n'
            f"deleted file mode 100644\n"
            f"index 2e3761f..0000000\n"
            f'--- "a/{path_octal}"\n'
            f"+++ /dev/null\n"
            f"@@ -1,{len(lines)} +0,0 @@\n"
            f"{body}")


def _git_quoted_rename(old_plain: str, new_octal: str) -> str:
    """A rename as real git emits it: the plain (space-containing) source stays bare,
    the unicode destination is quoted."""
    return (f'diff --git a/{old_plain} "b/{new_octal}"\n'
            f"similarity index 100%\n"
            f"rename from {old_plain}\n"
            f'rename to "{new_octal}"\n')


# The exact octal escapes git produced for these names (verified against `git diff`).
OCTAL_UNICODE = r"models/r\303\251sum\303\251.sql"
OCTAL_SPACED_MOVED = r"models/renamed caf\303\251.sql"


def test_b19_2_git_quoted_path_decodes_to_the_real_name():
    """The unit fact everything else rests on."""
    from autopilot.verify import unquote_git_path

    assert unquote_git_path(f'"a/{OCTAL_UNICODE}"') == f"a/{UNICODE_MODEL}"
    assert unquote_git_path(f'"b/{OCTAL_SPACED_MOVED}"') == f"b/{SPACED_MOVED}"
    # Unquoted forms (core.quotepath=false) pass through untouched.
    assert unquote_git_path(f"a/{UNICODE_MODEL}") == f"a/{UNICODE_MODEL}"
    assert unquote_git_path(f"a/{SPACED_MODEL}") == f"a/{SPACED_MODEL}"
    # C-style escapes other than octal.
    assert unquote_git_path(r'"a/we\"ird.sql"') == 'a/we"ird.sql'
    assert unquote_git_path(r'"a/tab\there.sql"') == "a/tab\there.sql"


def test_b19_2_quoted_and_raw_diffs_decode_identically():
    """core.quotepath is a display setting. The same deletion must be understood the
    same way whichever form the caller's git produced."""
    from autopilot.verify import parse_diff

    quoted = parse_diff(_git_quoted_delete(OCTAL_UNICODE, SQL_UNICODE))
    raw = parse_diff(_git_quoted_delete(UNICODE_MODEL, SQL_UNICODE).replace('"', ""))
    assert quoted.deleted == [UNICODE_MODEL], quoted.deleted
    assert raw.deleted == [UNICODE_MODEL], raw.deleted
    assert quoted.deleted == raw.deleted


def test_b19_2_deleting_a_quoted_unicode_path_blocks_pass(tmp_path):
    """THE FALSE PASS. The deletion was invisible because the path never matched any
    catalog `dbt_path` — we were comparing `models/r\\303\\251sum...` to `models/résumé...`."""
    models = {MODEL_A: SQL_A, UNICODE_MODEL: SQL_UNICODE}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)
    assert before.counts()["breaks"] == 2, "both models project the column"

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _git_quoted_delete(OCTAL_UNICODE, SQL_UNICODE))
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog)

    assert res.patch_applied is True
    assert res.deleted_files == [UNICODE_MODEL], res.deleted_files
    assert "\\303" not in " ".join(res.deleted_files), "the path must be DECODED, not raw"
    assert res.status != "PASS"
    assert "patched_file_deleted" in res.reasons


def test_b19_2_renaming_quoted_and_spaced_paths_is_detected(tmp_path):
    models = {MODEL_A: SQL_A, SPACED_MODEL: SQL_SPACED}
    repo = _make_repo(tmp_path, models)
    catalog = _catalog(models)
    before = _before(catalog)

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)
             + _git_quoted_rename(SPACED_MODEL, OCTAL_SPACED_MOVED))
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, SPACED_MODEL, SPACED_MOVED])

    assert res.renamed_files == [(SPACED_MODEL, SPACED_MOVED)], res.renamed_files
    assert res.status != "PASS"
    assert "patched_file_renamed" in res.reasons
    # BOTH decoded paths reach the reviewer.
    from autopilot.verify import render_verification_md
    md = render_verification_md(res)
    assert SPACED_MODEL in md and SPACED_MOVED in md
    assert "\\303" not in md


def test_b19_2_partition_invariant_holds_with_unicode_and_spaces(tmp_path):
    """B18's partition, re-asserted over paths that need decoding."""
    models = {MODEL_A: SQL_A, UNICODE_MODEL: SQL_UNICODE, SPACED_MODEL: SQL_SPACED}
    repo = _make_repo(tmp_path, {**models, MODEL_ORPHAN: SQL_ORPHAN})
    catalog = _catalog(models)
    before = _before(catalog)

    patch = (_diff(MODEL_A, SQL_A, FIXED_A)                              # mapped
             + _diff(MODEL_ORPHAN, SQL_ORPHAN, FIXED_ORPHAN)             # unmapped
             + _git_quoted_delete(OCTAL_UNICODE, SQL_UNICODE)            # deleted (unicode)
             + _git_quoted_rename(SPACED_MODEL, OCTAL_SPACED_MOVED))     # renamed (spaces)
    res = verify_migration(DROP_ZIP, before, patch, repo, catalog=catalog,
                           expected_files=[MODEL_A, MODEL_ORPHAN, UNICODE_MODEL,
                                           SPACED_MODEL, SPACED_MOVED])

    buckets = {
        "mapped": set(res.file_query_map),
        "unmapped": set(res.unmapped_files),
        "deleted": set(res.deleted_files),
        "renamed": {old for old, _new in res.renamed_files},
    }
    assert buckets["mapped"] == {MODEL_A}
    assert buckets["unmapped"] == {MODEL_ORPHAN}
    assert buckets["deleted"] == {UNICODE_MODEL}
    assert buckets["renamed"] == {SPACED_MODEL}
    seen: set[str] = set()
    for name, paths in buckets.items():
        assert not (seen & paths), f"{name} overlaps an earlier bucket"
        seen |= paths
    assert seen == set(res.diff_sql_paths), (seen, res.diff_sql_paths)
    assert res.scope_ok is True, res.scope_violations
