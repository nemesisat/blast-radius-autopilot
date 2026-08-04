"""B19.3–B19.6 + B20.3 — the human-approval path, and the line it must never cross.

Five rules, and every test here is one of them:

    1. No PASS, no automatic write. Absence of a verification is not permission.
    2. A REVIEW_REQUIRED run is not a dead end — a human may approve it, through a
       manifest that is BOUND to that exact change and queue, and usable ONCE.
    3. A FAIL can never be approved. Not by a flag, not by an env var, not by any
       entry point that can write.
    4. The record always says which path applied a mutation: a machine decided it,
       or a human approved it. Never both, never ambiguous.
    5. (B20.3) The GRAPH ITSELF records who approved what, and how it turned out —
       asserted against the payload that actually leaves the process, never against
       the local document we happen to return to the caller.

All fixtures are synthetic.
"""

from __future__ import annotations

import difflib
import itertools
import json
import re
import subprocess
from pathlib import Path

import pytest

from autopilot.assessment import build_assessment
from autopilot.impact import compute_impact
from autopilot.schema import Asset, Catalog, ChangeSpec, Dataset, Query
from autopilot.verify import verify_migration
from autopilot.writeback import WriteBack, plan_mutations

# --- fixtures ------------------------------------------------------------------

ORDERS = Dataset(
    urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,synthetic.orders,PROD)",
    name="orders", sql_name="analytics.orders", platform="snowflake",
    schema={"order_id": "NUMBER", "customer_zip": "TEXT", "amount": "NUMBER",
            "status": "TEXT"},
)
MODEL_A = "models/rpt_a.sql"
SQL_A = """-- rpt_a
SELECT
    o.order_id,
    o.customer_zip,
    o.amount
FROM analytics.orders o
"""
FIXED_A = SQL_A.replace("    o.customer_zip,\n", "")
DROP_ZIP = ChangeSpec.parse("analytics.orders", "customer_zip", "drop")


def _diff(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=3))


_REPO_SEQ = itertools.count()


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    # A fresh directory per call: several tests use two fixtures at once, and two
    # `git init`s in one directory would leave the second with nothing to commit.
    repo = tmp_path / f"repo{next(_REPO_SEQ)}"
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


def _catalog(models: dict[str, str], extra_queries=None, extra_assets=None) -> Catalog:
    queries, assets = [], []
    for rel, sql in models.items():
        name = Path(rel).stem
        qid = f"q_{name}"
        queries.append(Query(query_id=qid, sql=sql, platform="dbt", team="analytics-eng", runs=3))
        assets.append(Asset(urn=f"urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.{name},PROD)",
                            name=name, type="dbt_model", platform="dbt",
                            defining_query_id=qid, dbt_path=rel))
    return Catalog(name="synthetic-approval", datasets=[ORDERS],
                   queries=queries + (extra_queries or []),
                   assets=assets + (extra_assets or []), sql_dialect="snowflake")


@pytest.fixture
def passing(tmp_path):
    """A clean run whose verification PASSes — the only shape allowed to auto-write."""
    models = {MODEL_A: SQL_A}
    repo = _repo(tmp_path, models)
    catalog = _catalog(models)
    report = compute_impact(catalog, DROP_ZIP)
    v = verify_migration(DROP_ZIP, report, _diff(MODEL_A, SQL_A, FIXED_A),
                         repo, catalog=catalog)
    assert v.status == "PASS", v.reasons
    return report, v


@pytest.fixture
def reviewing(tmp_path):
    """A run that improved things but left an unassessable consumer -> REVIEW_REQUIRED."""
    models = {MODEL_A: SQL_A}
    repo = _repo(tmp_path, models)
    jinja = Query(query_id="q_jinja",
                  sql="SELECT * FROM {{ ref('orders') }} WHERE customer_zip = '1'",
                  platform="dbt", team="data-eng", runs=9)
    jinja_asset = Asset(urn="urn:li:dataset:(urn:li:dataPlatform:dbt,synthetic.jinja,PROD)",
                        name="jinja_model", type="dbt_model", platform="dbt",
                        defining_query_id="q_jinja")
    catalog = _catalog(models, extra_queries=[jinja], extra_assets=[jinja_asset])
    report = compute_impact(catalog, DROP_ZIP)
    v = verify_migration(DROP_ZIP, report, _diff(MODEL_A, SQL_A, FIXED_A),
                         repo, catalog=catalog)
    assert v.status == "REVIEW_REQUIRED", v.reasons
    return report, v


@pytest.fixture
def failing(tmp_path):
    """A run whose patch does not apply -> FAIL. Never approvable, by anything."""
    models = {MODEL_A: SQL_A}
    repo = _repo(tmp_path, models)
    catalog = _catalog(models)
    report = compute_impact(catalog, DROP_ZIP)
    v = verify_migration(DROP_ZIP, report, _diff(MODEL_A, "nope\n", "nah\n"),
                         repo, catalog=catalog)
    assert v.status == "FAIL", v.reasons
    return report, v


class _StubWriteBack:
    """A live-mode WriteBack with the DataHub SDK swapped out at the lowest level, so the
    real dispatch and the real accounting are exercised and nothing leaves the process."""

    def __new__(cls, assessment_dir=None, manifest_dir=None, fail_tools=()):
        obj = object.__new__(type("StubWB", (WriteBack,), dict(
            _append_description=lambda self, urn, footer: self._record("update_description", urn),
            _add_tags=lambda self, urn, tags: self._record("add_tags", urn),
            _save_document=lambda self, urn, title, url: self._record("save_document", urn),
            _set_structured_properties=lambda self, urn, props: self._record(
                "add_structured_properties", urn),
            _record=_record,
        )))
        obj.gms_url, obj.token, obj.dry_run, obj.require_review = "", "", False, False
        obj.assessment_dir = assessment_dir
        obj.manifest_dir = manifest_dir
        obj.fail_tools = set(fail_tools)
        obj.emitted = []
        obj._graph = None
        return obj


def _record(self, tool: str, urn: str) -> None:
    if tool in self.fail_tools:
        raise RuntimeError(f"GMS rejected {tool} on {urn}")
    self.emitted.append(f"{tool}:{urn}")


# ==============================================================================
# B19.3 — no verification, no automatic write
# ==============================================================================

def test_b19_3_no_verification_queues_everything(tmp_path, passing):
    """THE FALSE WRITE. A run with no `--verify` had never proven anything, yet it
    auto-applied. Absence of evidence is not permission to write."""
    report, _v = passing
    doc = build_assessment(report, [])
    muts = plan_mutations(report, doc, assessment_dir=tmp_path, verification=None)

    assert muts
    assert all(not m.auto for m in muts), "an unverified run must not auto-apply"
    assert all(m.queue_reason == "not_verified" for m in muts), (
        [m.queue_reason for m in muts]
    )


def test_b19_3_unverified_run_writes_nothing_live(tmp_path, passing):
    report, _v = passing
    wb = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=None)

    assert res.written_auto == []
    assert res.written_human_approved == []
    assert len(res.queued_for_review) == res.total
    assert wb.emitted == [], "nothing may reach the catalog without a PASS"
    assert "not_verified" in res.queue_reasons


@pytest.mark.parametrize("fixture_name", ["reviewing", "failing"])
def test_b19_3_non_pass_verification_queues_everything(tmp_path, request, fixture_name):
    report, v = request.getfixturevalue(fixture_name)
    muts = plan_mutations(report, build_assessment(report, [], verification=v),
                          verification=v, assessment_dir=tmp_path)
    assert muts and all(not m.auto for m in muts)
    # The verification gate is reported FIRST, because it is what must change first.
    # Other gates that also apply (e.g. unresolved impact) are appended, not hidden.
    for m in muts:
        assert m.queue_reason.split("+")[0] == f"verification_{v.status.lower()}", m.queue_reason


def test_b19_3_pass_verification_still_auto_writes(tmp_path, passing):
    """The gate must not be a blanket block: a PASS is exactly what earns the write."""
    report, v = passing
    muts = plan_mutations(report, build_assessment(report, [], verification=v),
                          verification=v, assessment_dir=tmp_path)
    assert muts and all(m.auto for m in muts)
    assert all(m.queue_reason == "" for m in muts)

    wb = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)
    assert len(res.written_auto) == res.total
    assert res.written_human_approved == []
    assert res.queued_for_review == []


def test_b19_3_queue_reason_reaches_every_surface(tmp_path, passing):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment

    report, _v = passing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, doc = wb.run(report, [], verification=None)

    assert "not_verified" in doc.markdown
    assert "not_verified" in render_html(report, [], writeback=res)
    assert "not_verified" in render_pr_comment(report, [], writeback=res)
    assert doc.properties["blast_radius_writeback_queue_reason"] == "not_verified"


# ==============================================================================
# B19.4 — approval manifests: bound, single-use, explicit
# ==============================================================================

def test_b19_4_review_required_emits_a_manifest(tmp_path, reviewing):
    from autopilot.approval import load_manifest

    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    assert res.manifest_path, "a REVIEW_REQUIRED run must offer a way forward"
    m = load_manifest(Path(res.manifest_path))
    assert m.verification_status == "REVIEW_REQUIRED"
    assert m.change == report.change.describe()
    assert m.fingerprint
    assert m.created_at
    assert m.consumed_at is None
    assert m.approver is None
    # Every queued mutation is listed, with what it would do.
    assert len(m.mutations) == len(res.queued_for_review)
    for qm in m.mutations:
        assert qm.tool and qm.target_urn and qm.payload_summary
    assert {qm.mutation_id for qm in m.mutations} == set(res.queued_for_review)


def test_b19_4_approving_applies_exactly_the_queued_mutations(tmp_path, reviewing):
    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)
    queued = list(res.queued_for_review)

    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    applied, _doc = live.approve(Path(res.manifest_path), report, [], verification=v,
                                approver="reviewer@example.com")

    assert applied.written_human_approved == queued, "exactly those, in that order"
    assert applied.written_auto == [], "an approved write is never an automatic one"
    assert set(live.emitted) == set(queued), "no more, no fewer"
    assert applied.approver == "reviewer@example.com"
    assert applied.manifest_id


def test_b19_4_manifest_is_single_use(tmp_path, reviewing):
    from autopilot.approval import ApprovalError

    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    first = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    first.approve(Path(res.manifest_path), report, [], verification=v, approver="a@example.com")

    second = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        second.approve(Path(res.manifest_path), report, [], verification=v,
                       approver="a@example.com")
    assert ei.value.code == "already_consumed"
    assert second.emitted == [], "a replayed approval must apply nothing"


def test_b19_4_manifest_is_bound_to_the_change(tmp_path, reviewing):
    """An approval is consent to one specific migration, not a standing permission."""
    from autopilot.approval import ApprovalError

    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    other = compute_impact(report_catalog(report), ChangeSpec.parse(
        "analytics.orders", "amount", "drop"))
    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        live.approve(Path(res.manifest_path), other, [], verification=v,
                     approver="a@example.com")
    assert ei.value.code == "manifest_stale"
    assert live.emitted == []


def test_b19_4_manifest_is_bound_to_the_queued_set(tmp_path, reviewing):
    """If the queue changed since the human looked at it, their approval no longer
    describes what would happen."""
    from autopilot.approval import ApprovalError

    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    # Tamper: drop one queued mutation from the manifest.
    path = Path(res.manifest_path)
    raw = json.loads(path.read_text())
    raw["mutations"] = raw["mutations"][:-1]
    path.write_text(json.dumps(raw))

    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        live.approve(path, report, [], verification=v, approver="a@example.com")
    assert ei.value.code == "manifest_stale"
    assert live.emitted == []


def test_b19_4_manifest_is_bound_to_the_verification_status(tmp_path, reviewing, passing):
    from autopilot.approval import ApprovalError

    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    _r2, other_v = passing        # a different verdict for the same change
    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        live.approve(Path(res.manifest_path), report, [], verification=other_v,
                     approver="a@example.com")
    assert ei.value.code == "manifest_stale"
    assert live.emitted == []


def test_b19_4_approval_needs_a_manifest_that_exists(tmp_path, reviewing):
    from autopilot.approval import ApprovalError

    report, v = reviewing
    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        live.approve(tmp_path / "no-such-manifest.json", report, [], verification=v,
                     approver="a@example.com")
    assert ei.value.code == "no_manifest"
    assert live.emitted == []


def test_b19_4_approver_is_never_invented(tmp_path, reviewing):
    from autopilot.approval import ApprovalError

    report, v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    for bad in (None, "", "   "):
        with pytest.raises(ApprovalError) as ei:
            live.approve(Path(res.manifest_path), report, [], verification=v, approver=bad)
        assert ei.value.code == "no_approver"
    assert live.emitted == []


def report_catalog(report):
    """Rebuild a minimal catalog that resolves the same dataset (test helper)."""
    return Catalog(name=report.catalog, datasets=[ORDERS], queries=[], assets=[])


# ==============================================================================
# B19.5 — a FAIL can never be approved, by anything
# ==============================================================================

def test_b19_5_fail_emits_no_manifest(tmp_path, failing):
    report, v = failing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(report, [], verification=v)

    assert res.manifest_path is None, "a FAIL offers no approval route at all"
    assert list(tmp_path.glob("APPROVAL-*.json")) == []


def test_b19_5_build_manifest_refuses_a_fail(tmp_path, failing):
    from autopilot.approval import build_manifest

    report, v = failing
    assert build_manifest(report, v, [], manifest_dir=tmp_path) is None
    assert list(tmp_path.glob("APPROVAL-*.json")) == []


def test_b19_5_writeback_api_refuses_to_approve_a_fail(tmp_path, reviewing, failing):
    """The nastiest attempt: take a legitimate manifest from a REVIEW_REQUIRED run and
    present it while the verification is a FAIL."""
    from autopilot.approval import ApprovalError

    review_report, review_v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(review_report, [], verification=review_v)

    _fr, fail_v = failing
    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        live.approve(Path(res.manifest_path), review_report, [], verification=fail_v,
                     approver="a@example.com")
    assert ei.value.code == "fail_not_approvable"
    assert live.emitted == [], "zero mutations applied"


def test_b19_5_cli_refuses_to_approve_a_fail(tmp_path, reviewing, failing):
    from autopilot.approval import ApprovalError
    from autopilot.run import apply_approval

    review_report, review_v = reviewing
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = wb.run(review_report, [], verification=review_v)

    _fr, fail_v = failing
    live = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    with pytest.raises(ApprovalError) as ei:
        apply_approval(live, Path(res.manifest_path), review_report, [],
                       verification=fail_v, approver="a@example.com")
    assert ei.value.code == "fail_not_approvable"
    assert live.emitted == []


def test_b19_5_no_entry_point_offers_a_fail_override():
    """There must be no flag, env var, or parameter anywhere that applies a FAIL.

    Asserted structurally rather than by trying every string: the signatures of the
    three things that can write, plus the CLI's own flag list.
    """
    import inspect

    from autopilot import loop as loop_mod
    from autopilot import run as run_mod
    from autopilot import writeback as wb_mod

    FORBIDDEN = re.compile(
        r"force|override|ignore_fail|skip_verif|allow_fail|no_verify|unsafe|yolo", re.I)

    for fn in (wb_mod.WriteBack.__init__, wb_mod.WriteBack.run,
               wb_mod.WriteBack.approve, wb_mod.plan_mutations,
               loop_mod.run_loop, run_mod.apply_approval):
        for name in inspect.signature(fn).parameters:
            assert not FORBIDDEN.search(name), f"{fn.__qualname__} exposes '{name}'"

    # The CLI's flags, read off the parser it actually builds.
    for opt in run_mod.build_parser()._option_string_actions:
        assert not FORBIDDEN.search(opt), f"CLI exposes {opt}"

    # And no environment variable is consulted to bypass the gate.
    src = "".join(inspect.getsource(m) for m in (wb_mod, run_mod, loop_mod))
    for env in re.findall(r"getenv\(\s*[\"']([A-Z0-9_]+)", src):
        assert not FORBIDDEN.search(env), f"env var {env} looks like an override"


def test_b19_5_loop_never_auto_writes_without_a_pass(tmp_path):
    """The batch entry point. `--loop` does not verify, so by rule 1 it can only queue —
    and it has no approval route of its own."""
    import inspect

    from autopilot.loop import run_loop

    config = tmp_path / "loop.json"
    ex = Path(__file__).resolve().parents[1] / "examples" / "showcase-ecommerce" / "catalog.json"
    config.write_text(json.dumps([{
        "name": "ecom", "catalog": str(ex),
        "change": "drop analytics.fct_orders.customer_zip",
    }]))

    results = run_loop(config, write=True)
    assert results
    for r in results:
        assert r.written == 0, f"{r.name} wrote without a PASS"
        assert r.written_auto == 0
        assert r.written_human_approved == 0
        assert r.queued == r.total
    assert "approve" not in inspect.signature(run_loop).parameters


# ==============================================================================
# B19.6 — the record distinguishes machine decisions from human approvals
# ==============================================================================

def test_b19_6_auto_and_human_buckets_are_disjoint_and_reconcile(tmp_path, passing, reviewing):
    auto_report, auto_v = passing
    auto = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    auto_res, _ = auto.run(auto_report, [], verification=auto_v)

    rev_report, rev_v = reviewing
    dry = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    queued_res, _ = dry.run(rev_report, [], verification=rev_v)
    human = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    human_res, _ = human.approve(Path(queued_res.manifest_path), rev_report, [],
                                 verification=rev_v, approver="a@example.com")

    for res in (auto_res, queued_res, human_res):
        assert not (set(res.written_auto) & set(res.written_human_approved))
        assert res.reconciles(), f"{res.counts()} vs total {res.total}"
        c = res.counts()
        assert (c["written_auto"] + c["written_human_approved"] + c["queued_for_review"]
                + c["failed"] + c["planned"] + c["skipped"]) == res.total
        assert c["written"] == c["written_auto"] + c["written_human_approved"]

    assert auto_res.written_auto and not auto_res.written_human_approved
    assert human_res.written_human_approved and not human_res.written_auto


def test_b19_6_no_surface_calls_a_human_approval_automatic(tmp_path, reviewing):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment

    report, v = reviewing
    dry = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    queued, _ = dry.run(report, [], verification=v)
    human = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, doc = human.approve(Path(queued.manifest_path), report, [], verification=v,
                             approver="reviewer@example.com")

    n = len(res.written_human_approved)
    surfaces = {
        "summary_line": res.summary_line(),
        "assessment": doc.markdown,
        "html": render_html(report, [], writeback=res),
        "pr": render_pr_comment(report, [], writeback=res),
    }
    for name, text in surfaces.items():
        assert "human-approved" in text.lower(), f"{name} hides the approval path"
        assert "reviewer@example.com" in text, f"{name} omits the approver"
        # ...and never claims these were automatic.
        assert not re.search(rf"\b{n}\s+written\s*\(auto", text), f"{name} miscredits auto"
        assert re.search(r"0\s+written\s*\(auto", text), f"{name} should show 0 auto"


def test_b19_6_no_surface_calls_an_auto_write_human_approved(tmp_path, passing):
    from autopilot.report_html import render_html
    from autopilot.report_pr import render_pr_comment

    report, v = passing
    wb = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, doc = wb.run(report, [], verification=v)

    for name, text in {
        "summary_line": res.summary_line(),
        "assessment": doc.markdown,
        "html": render_html(report, [], writeback=res),
        "pr": render_pr_comment(report, [], writeback=res),
    }.items():
        assert re.search(r"0\s+written\s*\(human-approved", text), f"{name}: {text[:200]}"
        assert res.approver is None
        assert "approver" not in text.lower() or "—" in text or "n/a" in text.lower()


def test_b19_6_structured_properties_record_the_applying_path(tmp_path, passing, reviewing):
    auto_report, auto_v = passing
    auto = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    _res, auto_doc = auto.run(auto_report, [], verification=auto_v)
    assert auto_doc.properties["blast_radius_writeback_applied_by"] == "auto"
    assert auto_doc.properties["blast_radius_writeback_written_auto"] == _res.total
    assert auto_doc.properties["blast_radius_writeback_written_human_approved"] == 0
    assert auto_doc.properties["blast_radius_approval_manifest_id"] == ""
    assert auto_doc.properties["blast_radius_writeback_approver"] == ""

    rev_report, rev_v = reviewing
    dry = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    queued, _ = dry.run(rev_report, [], verification=rev_v)
    human = _StubWriteBack(assessment_dir=tmp_path, manifest_dir=tmp_path)
    hres, hdoc = human.approve(Path(queued.manifest_path), rev_report, [],
                               verification=rev_v, approver="reviewer@example.com")
    assert hdoc.properties["blast_radius_writeback_applied_by"] == "human-approved"
    assert hdoc.properties["blast_radius_writeback_written_auto"] == 0
    assert hdoc.properties["blast_radius_writeback_written_human_approved"] == hres.total
    assert hdoc.properties["blast_radius_approval_manifest_id"] == hres.manifest_id
    assert hdoc.properties["blast_radius_writeback_approver"] == "reviewer@example.com"


def test_b19_4_fingerprint_is_bound_to_the_decision_not_the_clock(tmp_path, reviewing):
    """A manifest written now must still be approvable in a minute.

    The first cut of `fingerprint_for()` hashed the structured-property payload summary
    including `blast_radius_assessed_at` — a timestamp — so the fingerprint changed on
    every run and NO manifest could ever be approved from a second process. An approval
    is consent to a decision; it must not expire because the clock moved.
    """
    from autopilot.approval import fingerprint_for, queued_from

    report, v = reviewing
    dry = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = dry.run(report, [], verification=v)

    # Re-plan from scratch, as a separate `--approve` invocation would.
    later = plan_mutations(report, build_assessment(report, [], verification=v),
                           verification=v, assessment_dir=tmp_path)
    assert fingerprint_for(report, v, queued_from(later)) == \
        json.loads(Path(res.manifest_path).read_text())["fingerprint"]

    # ...and it still refuses when something that MATTERS changes.
    mutated = [m for m in later if m.tool != "add_tags"]
    assert fingerprint_for(report, v, queued_from(mutated)) != \
        json.loads(Path(res.manifest_path).read_text())["fingerprint"]


# ==============================================================================
# B20.3 — the approval trail lives in the GRAPH, not just in local counters
# ==============================================================================
#
# B19.4–B19.6 made the approval bound, single-use, attributed and separately
# accounted — but all of that lived in a manifest file and an in-memory
# `WriteBackResult`. The catalog, which is the thing every other human actually
# looks at, learned nothing about who consented to the write.
#
# THE TRAP THESE TESTS EXIST TO AVOID. `WriteBack` builds the assessment TWICE
# (B17.4): the copy EMITTED to the catalog is built without write-back counters,
# and the copy RETURNED to the caller carries them. So a test that asserts on
# `doc.properties` — as `test_b19_6_structured_properties_record_the_applying_path`
# does — proves only that we can format a dict. It cannot distinguish "recorded in
# DataHub" from "recorded in a variable we then threw away". Every test below
# therefore reads the aspect that crossed the SDK boundary, in its wire form.

_AUDIT_KEYS = (
    "blast_radius_approved_by",
    "blast_radius_approved_at",
    "blast_radius_manifest_id",
    "blast_radius_verification_status_at_approval",
    "blast_radius_approved_writes",
    "blast_radius_approved_failures",
)


class _CapturingGraph:
    """A stand-in for `DataHubGraph` at the LOWEST seam — the client itself.

    Everything above it is the real code path: `WriteBack._emit()` dispatches,
    `_set_structured_properties()` defines-then-assigns, and real
    `MetadataChangeProposalWrapper` / aspect classes are constructed. We keep the
    proposals so a test can read what would have gone over the wire.

    `aspects` models the one DataHub behaviour that matters here: an emitted aspect
    REPLACES the stored one. That is what makes a second structured-properties emit
    dangerous, and it is why `structured_properties_state()` is the read-back.
    """

    def __init__(self, fail_aspects: tuple[str, ...] = ()):
        self.mcps: list = []
        self.aspects: dict[tuple[str, str], object] = {}
        self.fail_aspects = set(fail_aspects)

    def get_aspect(self, urn: str, aspect_type):
        return self.aspects.get((urn, aspect_type.ASPECT_NAME))

    def emit(self, mcp) -> None:
        name = type(mcp.aspect).ASPECT_NAME
        if name in self.fail_aspects:
            raise RuntimeError(f"GMS rejected aspect {name} on {mcp.entityUrn}")
        self.mcps.append(mcp)
        self.aspects[(mcp.entityUrn, name)] = mcp.aspect


def _live(assessment_dir, manifest_dir, graph) -> WriteBack:
    """A real live-mode WriteBack with only the DataHub client swapped out."""
    wb = WriteBack(gms_url="http://stub", token="stub", dry_run=False,
                   assessment_dir=assessment_dir, manifest_dir=manifest_dir)
    wb._graph = graph
    return wb


def _decode(aspect) -> dict[str, str]:
    """Structured properties as they serialise for the wire, keyed by property name."""
    return {
        a["propertyUrn"].rsplit(":", 1)[-1]: a["values"][0]["string"]
        for a in aspect.to_obj()["properties"]
    }


def structured_properties_emitted(graph, urn: str | None = None) -> list[dict[str, str]]:
    """Every structured-properties payload that actually crossed the SDK boundary."""
    return [
        _decode(m.aspect) for m in graph.mcps
        if type(m.aspect).ASPECT_NAME == "structuredProperties"
        and (urn is None or m.entityUrn == urn)
    ]


def structured_properties_state(graph, urn: str) -> dict[str, str]:
    """The read-back: what the catalog would hold for `urn` after every emit."""
    aspect = graph.aspects.get((urn, "structuredProperties"))
    return _decode(aspect) if aspect is not None else {}


def defined_properties(graph) -> list[str]:
    """Property names DEFINED over the wire, in emit order. Values cannot be set
    before the definition exists (a hard-won B5 fact), so ordering is load-bearing."""
    return [m.aspect.qualifiedName for m in graph.mcps
            if type(m.aspect).ASPECT_NAME == "propertyDefinition"]


def _queued_run(report, v, tmp_path):
    """The dry REVIEW_REQUIRED run that produces the manifest a human then approves."""
    dry = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    res, _doc = dry.run(report, [], verification=v)
    assert res.manifest_path
    return res


def test_b20_3_human_approved_write_records_the_audit_in_the_emitted_payload(tmp_path, reviewing):
    """THE POINT OF B20.3. Approve, then read the payload that left the process.

    Asserting on the returned `AssessmentDoc` would pass even if nothing were ever
    emitted, because the emitted copy is a DIFFERENT object built without write-back
    context. So this reads the `structuredProperties` aspect off the captured
    proposals, in the form it serialises to.
    """
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    res, _doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                           approver="reviewer@example.com")

    emitted = structured_properties_state(graph, report.target_urn)
    assert emitted, "nothing at all reached the catalog"
    missing = [k for k in _AUDIT_KEYS if k not in emitted]
    assert not missing, f"approval audit never left the process: missing {missing}"

    assert emitted["blast_radius_approved_by"] == "reviewer@example.com"
    assert emitted["blast_radius_manifest_id"] == res.manifest_id != ""
    assert emitted["blast_radius_verification_status_at_approval"] == "REVIEW_REQUIRED"
    assert emitted["blast_radius_approved_writes"] == str(len(res.written_human_approved))
    assert emitted["blast_radius_approved_failures"] == "0"
    # A real timestamp, not a placeholder.
    from datetime import datetime
    datetime.fromisoformat(emitted["blast_radius_approved_at"])


def test_b20_3_audit_does_not_wipe_the_base_properties(tmp_path, reviewing):
    """A structured-properties emit REPLACES the aspect. Recording the approval must
    therefore not cost the assessment: risk, counts and verification have to survive
    alongside the audit, or B20.3 would trade one record for another."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    wb.approve(Path(queued.manifest_path), report, [], verification=v,
               approver="reviewer@example.com")

    final = structured_properties_state(graph, report.target_urn)
    for key in ("blast_radius_status", "blast_radius_risk", "blast_radius_breaks",
                "blast_radius_coverage", "blast_radius_verification_status",
                "blast_radius_approved_by", "blast_radius_approved_writes"):
        assert key in final, f"{key} is not in the catalog's final state"
    assert final["blast_radius_status"] == "pending-change"
    assert final["blast_radius_verification_status"] == "REVIEW_REQUIRED"


def test_b20_3_audit_properties_are_defined_before_they_are_set(tmp_path, reviewing):
    """Structured-property VALUES cannot be set before the property is DEFINED — a bug
    already paid for once against a live instance. New property names must not
    reintroduce it."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    wb.approve(Path(queued.manifest_path), report, [], verification=v,
               approver="reviewer@example.com")

    defined = defined_properties(graph)
    for key in _AUDIT_KEYS:
        assert key in defined, f"{key} was set without ever being defined"

    # ...and the definition precedes the assignment that carries the audit.
    audit_at = next(i for i, m in enumerate(graph.mcps)
                    if type(m.aspect).ASPECT_NAME == "structuredProperties"
                    and "blast_radius_approved_by" in _decode(m.aspect))
    for key in _AUDIT_KEYS:
        def_at = next(i for i, m in enumerate(graph.mcps)
                      if type(m.aspect).ASPECT_NAME == "propertyDefinition"
                      and m.aspect.qualifiedName == key)
        assert def_at < audit_at, f"{key} defined after it was assigned"


def test_b20_3_auto_applied_pass_write_carries_no_approver_fields(tmp_path, passing):
    """The two paths must stay distinguishable IN THE CATALOG (B19.6). A machine
    decision has no approver, so an automatic write must carry no approver field —
    not blank, not 'system', not absent-but-implied. Read off the wire."""
    report, v = passing
    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    res, _doc = wb.run(report, [], verification=v)
    assert res.written_auto and not res.written_human_approved

    payloads = structured_properties_emitted(graph)
    assert payloads, "the PASS path must still auto-write"
    for payload in payloads:
        for key in _AUDIT_KEYS:
            assert key not in payload, f"an automatic write carried {key}"
        # Nothing approval-shaped under any other name, either.
        assert not [k for k in payload if re.search(r"approv", k, re.I)], payload

    state = structured_properties_state(graph, report.target_urn)
    assert state["blast_radius_status"] == "pending-change"
    assert not [k for k in state if re.search(r"approv", k, re.I)]


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_b20_3_a_refused_approval_records_no_approver_at_all(tmp_path, reviewing, bad):
    """No approver, no approval — and therefore no audit entry naming nobody. An
    'unknown'/blank approver in the graph would be worse than no record."""
    from autopilot.approval import ApprovalError

    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    with pytest.raises(ApprovalError) as ei:
        wb.approve(Path(queued.manifest_path), report, [], verification=v, approver=bad)
    assert ei.value.code == "no_approver"
    assert graph.mcps == [], "a refused approval emitted something"
    assert structured_properties_state(graph, report.target_urn) == {}


def test_b20_3_a_fail_records_no_audit(tmp_path, reviewing, failing):
    """A FAIL is never approvable, so there is nothing to audit — and the refusal must
    not leave a half-written trail suggesting otherwise."""
    from autopilot.approval import ApprovalError

    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    _fr, fail_v = failing
    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    with pytest.raises(ApprovalError) as ei:
        wb.approve(Path(queued.manifest_path), report, [], verification=fail_v,
                   approver="reviewer@example.com")
    assert ei.value.code == "fail_not_approvable"
    assert graph.mcps == []


def test_b20_3_partial_outcome_is_recorded_honestly(tmp_path, reviewing):
    """Some mutations failed. The audit in the catalog must say so — the real numbers,
    reconciling with the counters, not the count a happy path would have produced."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph(fail_aspects=("globalTags",))
    wb = _live(tmp_path, tmp_path, graph)
    res, _doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                           approver="reviewer@example.com")

    assert res.failed, "fixture should have produced real failures"
    assert res.written_human_approved, "and real successes, so the split is visible"
    assert res.reconciles()

    state = structured_properties_state(graph, report.target_urn)
    assert state["blast_radius_approved_writes"] == str(len(res.written_human_approved))
    assert state["blast_radius_approved_failures"] == str(len(res.failed))
    # The recorded numbers are the ones that happened, not the ones planned.
    assert int(state["blast_radius_approved_writes"]) < res.total
    assert (int(state["blast_radius_approved_writes"])
            + int(state["blast_radius_approved_failures"])) == res.total


def test_b20_3_total_failure_still_records_that_a_human_approved(tmp_path, reviewing):
    """Every approved mutation failed. A human still consented, and that consent —
    plus the fact that it achieved nothing — is exactly what an audit is for."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph(fail_aspects=("globalTags", "institutionalMemory",
                                          "editableDatasetProperties"))
    wb = _live(tmp_path, tmp_path, graph)
    res, _doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                           approver="reviewer@example.com")

    state = structured_properties_state(graph, report.target_urn)
    assert state["blast_radius_approved_by"] == "reviewer@example.com"
    assert state["blast_radius_approved_failures"] == str(len(res.failed))
    assert int(state["blast_radius_approved_failures"]) > 0


def test_b20_3_a_failed_audit_emit_is_reported_not_swallowed(tmp_path, reviewing):
    """If the audit itself cannot be written, the run must say so. Silently losing the
    approval trail while reporting a successful approval would be the same class of
    lie B17.4 removed from the write counters."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph(fail_aspects=("structuredProperties",))
    wb = _live(tmp_path, tmp_path, graph)
    res, _doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                           approver="reviewer@example.com")

    assert res.audit_status == "failed", res.audit_status
    assert res.audit_error
    assert structured_properties_state(graph, report.target_urn) == {}


def test_b20_3_a_dry_run_approval_records_nothing(tmp_path, reviewing):
    """A dry run must not claim an audit was recorded, for the same reason it must not
    claim a write was performed."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = WriteBack(dry_run=True, assessment_dir=tmp_path, manifest_dir=tmp_path)
    wb._graph = graph
    res, _doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                           approver="reviewer@example.com")

    assert res.audit_status == "planned"
    assert graph.mcps == []
    assert res.written_human_approved == [] and res.planned


def test_b20_3_the_manifest_tells_the_approver_their_name_is_recorded(tmp_path, reviewing):
    """Consent to a write is not consent to be named in a shared catalog unless you were
    told. The manifest a human reads before approving must say that approving records
    their identity in the graph."""
    from autopilot.approval import load_manifest, render_manifest_md

    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    manifest = load_manifest(Path(queued.manifest_path))
    md = render_manifest_md(manifest)
    assert re.search(r"record", manifest.note, re.I), manifest.note
    assert re.search(r"approver|identity|who approved", manifest.note, re.I)
    assert re.search(r"blast_radius_approved_by", md), "the .md must name the property"


def test_b20_3_the_writeback_property_family_is_report_only(tmp_path, reviewing):
    """A claim corrected by B20.3, and pinned here so it cannot be re-made.

    B19.6's docs said the catalog carried `blast_radius_writeback_applied_by` /
    `_approver` / `blast_radius_approval_manifest_id`. It never did: those keys live in
    the assessment built WITH write-back context, and the copy that is emitted is
    deliberately built WITHOUT it (B17.4 — a document cannot honestly report the outcome
    of the write that saves it). They are report-only, and the catalog-resident record of
    who approved what is the B20.3 audit family instead.
    """
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    _res, doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                           approver="reviewer@example.com")

    state = structured_properties_state(graph, report.target_urn)
    assert not [k for k in state if k.startswith("blast_radius_writeback_")], (
        "the write-back family is report-only; if it now lands, the docs must say so"
    )
    assert "blast_radius_approval_manifest_id" not in state
    # ...and it is still in the returned document, where the reports read it from.
    assert doc.properties["blast_radius_writeback_applied_by"] == "human-approved"
    # The catalog can still tell the paths apart — by the audit family.
    assert state["blast_radius_approved_by"] == "reviewer@example.com"


def test_b20_3_manifest_id_is_consistent_across_property_families(tmp_path, reviewing):
    """`blast_radius_manifest_id` (approval audit) and
    `blast_radius_approval_manifest_id` (write-back run) describe the same approval.
    They may not drift."""
    report, v = reviewing
    queued = _queued_run(report, v, tmp_path)

    graph = _CapturingGraph()
    wb = _live(tmp_path, tmp_path, graph)
    res, doc = wb.approve(Path(queued.manifest_path), report, [], verification=v,
                          approver="reviewer@example.com")

    assert doc.properties["blast_radius_manifest_id"] == \
        doc.properties["blast_radius_approval_manifest_id"] == res.manifest_id
    assert doc.properties["blast_radius_approved_by"] == \
        doc.properties["blast_radius_writeback_approver"] == "reviewer@example.com"
