"""CLI: gather -> compute blast radius -> generate fix -> write back.

Offline (the tested path) — assess a change against a JSON catalog + query log:

    autopilot --catalog examples/showcase-ecommerce/catalog.json \
              --change "drop analytics.fct_orders.customer_zip"

    autopilot --catalog ... --change "rename analytics.fct_orders.customer_zip postal_code" \
              --html out/report.html --pr-comment out/PR_COMMENT.md --write

Online — pull schema/lineage/queries from a live DataHub instance:

    autopilot --online --target-urn "urn:li:dataset:(...)" \
              --change "drop analytics.fct_orders.customer_zip" --write
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .assessment import narrative_summary
from .impact import compute_impact
from .schema import Catalog, ChangeSpec, Verdict


def _parse_change(args) -> ChangeSpec:
    if args.change:
        toks = args.change.split()
        op = toks[0].lower()
        ref = toks[1]
        dataset, _, column = ref.rpartition(".")
        new_name = toks[2] if len(toks) > 2 else args.new_name
        return ChangeSpec.parse(dataset, column, op, new_name)
    return ChangeSpec.parse(args.dataset, args.column, args.op, args.new_name)


def _load_catalog(args) -> Catalog:
    if args.online:
        from .catalog import DataHubCatalogReader

        reader = DataHubCatalogReader(os.getenv("DATAHUB_GMS_URL"), os.getenv("DATAHUB_TOKEN"))
        urn = args.target_urn
        target = reader.dataset(urn)
        queries = list(reader.dataset_queries(urn))
        for d in reader.downstream_urns(urn):
            queries += reader.dataset_queries(d)
        return Catalog(name=target.name, datasets=[target], queries=queries, assets=[])
    from .catalog import load_catalog

    return load_catalog(args.catalog, args.query_log)


_COLOR = {Verdict.BREAKS: "\033[91m", Verdict.DEGRADES: "\033[93m", Verdict.SAFE: "\033[92m",
          Verdict.UNKNOWN: "\033[90m"}
_RESET = "\033[0m"


def _print_blast_radius(report) -> None:
    c = report.counts()
    risk = report.risk()
    print("\n" + "=" * 72)
    print(f"  BLAST RADIUS — {report.change.describe()}   (catalog: {report.catalog})")
    print("=" * 72)
    print(f"  {narrative_summary(report)}")
    print("-" * 72)
    for v in report.impacted():
        col = _COLOR[v.verdict]
        label = v.asset_name or v.query_id
        kind = f" [{v.asset_type}]" if v.asset_type else ""
        print(f"  {col}{v.verdict.value:<9}{_RESET} {label}{kind}  · {v.team or '—'} · {v.runs} runs")
        print(f"            └ {v.reason}")
    if report.unknown:
        print("-" * 72)
        for v in report.unknown:
            label = v.asset_name or v.query_id
            print(f"  \033[90mUNKNOWN\033[0m   {label} · {v.reason}")
    if report.ambiguous:
        print("-" * 72)
        for v in report.ambiguous:
            print(f"  \033[90mLOW-CONF\033[0m  {v.query_id} · {v.reason}  (surfaced, not counted)")
    print("-" * 72)
    cov = report.coverage()
    print(
        f"  SCORECARD: risk {risk['level_qualifier']} ({risk['score']}/100)  |  "
        f"🔴 {c['breaks']} breaks  🟡 {c['degrades']} degrades  🟢 {c['safe']} safe  "
        f"⚪ {c['unknown']} unassessed  ◐ {c['ambiguous']} ambiguous  |  "
        f"{c['teams']} team(s)  ·  {c['runs_impacted']} impacted runs"
    )
    print(f"  COVERAGE:  {cov['line']} consumer(s)")
    if report.review_required():
        # Name the gap: unassessed and ambiguous are different failures of knowledge.
        gaps = []
        if cov["unassessed"]:
            gaps.append(f"{cov['unassessed']} consumer(s) could not be assessed")
        if report.ambiguous:
            gaps.append(f"{len(report.ambiguous)} reference(s) could not be attributed to a "
                        f"source table")
        print(f"  \033[93m⚠️  REVIEW REQUIRED\033[0m — {'; '.join(gaps)}. "
              f"Unresolved impact must not be auto-applied.")
    for n in report.notes:
        print(f"  note: {n}")
    print("=" * 72 + "\n")


_V_BADGE = {"PASS": "\033[92m✅ PASS\033[0m",
            "REVIEW_REQUIRED": "\033[93m⚠️  REVIEW REQUIRED\033[0m",
            "FAIL": "\033[91m❌ FAIL\033[0m"}


def _print_verification(v) -> None:
    """Before/after table + verdict. Static verification — nothing was executed."""
    from .verify import _REASON_TEXT

    d = v.deltas()
    print("=" * 72)
    print(f"  MIGRATION VERIFICATION (static)  —  {_V_BADGE.get(v.status, v.status)}")
    print("=" * 72)
    print(f"  {'metric':<14}{'before':>8}{'after':>8}{'delta':>8}")
    print("  " + "-" * 38)
    for key, label in [("breaks", "breaks"), ("degrades", "degrades"),
                       ("safe", "safe"), ("unknown", "unassessed"),
                       ("ambiguous", "ambiguous")]:
        print(f"  {label:<14}{v.before.get(key, 0):>8}{v.after.get(key, 0):>8}"
              f"{d.get(key, 0):>+8d}")
    print(f"  {'coverage':<14}{v.coverage_before.get('line', 'n/a'):>8} -> "
          f"{v.coverage_after.get('line', 'n/a')}")
    print("  " + "-" * 38)
    if v.transitions:
        print("  transitions:")
        for t in v.transitions:
            mark = "\033[91m!\033[0m" if t.regressed else " "
            print(f"    {mark} {t.describe()}")
    if v.parse_errors:
        print("  parse errors:")
        for e in v.parse_errors:
            print(f"    - {e}")
    if v.scope_violations:
        print("  scope violations:")
        for sv in v.scope_violations:
            print(f"    - {sv}")
    if v.residual_references:
        print("  fix incomplete — column still referenced after patching:")
        for rr in v.residual_references:
            print(f"    - {rr}")
    if v.unknown_consumers:
        print(f"  unassessed ({len(v.unknown_consumers)}): {', '.join(v.unknown_consumers[:6])}"
              + (" ..." if len(v.unknown_consumers) > 6 else ""))
    if v.ambiguous_consumers:
        print(f"  ambiguous — parsed but not attributable ({len(v.ambiguous_consumers)}): "
              + ", ".join(v.ambiguous_consumers[:6])
              + (" ..." if len(v.ambiguous_consumers) > 6 else ""))
    if not v.target_resolved:
        print(f"  \033[91mthe change did not resolve:\033[0m {v.target_problem}")
    elif not v.schema_known:
        print(f"  \033[93mthe target's schema is unknown:\033[0m {v.target_problem}")
    if v.unmapped_files:
        print("  patched files whose impact could NOT be recomputed (unmapped to any consumer):")
        for u in v.unmapped_files:
            print(f"    - {u}")
    if v.deleted_files:
        print("  files DELETED by the diff (a vanished consumer is not an unaffected one):")
        for d_ in v.deleted_files:
            print(f"    - {d_}")
    if v.renamed_files:
        print("  files MOVED by the diff:")
        for old, new in v.renamed_files:
            tag = ("recomputed at the new path" if (old, new) not in v.unresolved_renames
                   else "NOT re-analysable at the new path")
            print(f"    - {old} -> {new}  ({tag})")
    if v.file_query_map:
        print("  patched files recomputed: "
              + ", ".join(f"{rel} -> {qid}" for rel, qid in sorted(v.file_query_map.items())))
    if v.manual_work_remaining:
        print(f"  manual work: {', '.join(v.manual_work_remaining[:6])}"
              + (" ..." if len(v.manual_work_remaining) > 6 else ""))
    print("  why:")
    for r in v.reasons:
        print(f"    - {r} — {_REASON_TEXT.get(r, r)}")
    print(f"  files patched in isolation: {', '.join(v.files_patched) or '—'}")
    print("  scope: STATIC ONLY — no queries executed, no warehouse contacted, no data read.")
    print("=" * 72 + "\n")


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # noqa: BLE001
        pass

    ap = build_parser()
    args = ap.parse_args()
    return _main(args)


def build_parser() -> argparse.ArgumentParser:
    """The real flag list, exposed so a test can assert what the CLI does and does not
    offer. B19.5 asserts there is no flag here that applies a FAILED verification."""
    ap = argparse.ArgumentParser(description="Blast Radius Autopilot")
    ap.add_argument("--catalog", type=Path, help="Offline JSON catalog")
    ap.add_argument("--query-log", type=Path, help="Offline query log JSON (defaults to sibling query_log.json)")
    ap.add_argument("--online", action="store_true", help="Pull metadata from a live DataHub instance")
    ap.add_argument("--target-urn", help="Target dataset URN (with --online)")
    ap.add_argument("--change", help='e.g. "drop analytics.fct_orders.customer_zip" or "rename T.c new"')
    ap.add_argument("--dataset")
    ap.add_argument("--column")
    ap.add_argument("--op", default="drop", choices=["drop", "rename"])
    ap.add_argument("--new-name")
    ap.add_argument("--repo-root", type=Path, help="Root of the dbt repo for fix generation")
    ap.add_argument("--write", action="store_true", help="Apply write-back (default: dry run)")
    ap.add_argument("--require-review", action="store_true", help="Queue all writes for human review (regulated data)")
    ap.add_argument("--html", type=Path, help="Write a self-contained HTML report here")
    ap.add_argument("--pr-comment", type=Path, help="Write a CI-style PR comment here")
    ap.add_argument("--json", type=Path, help="Write the machine-readable report here")
    ap.add_argument("--fragility", action="store_true", help="Rank the riskiest columns catalog-wide (B13)")
    ap.add_argument("--top", type=int, help="Limit the fragility leaderboard to N rows")
    ap.add_argument("--loop", type=Path, help="Run every change in a loop config (YAML/JSON) across datasets (B6)")
    ap.add_argument("--out", type=Path, help="Output directory for --loop reports")
    ap.add_argument("--plan", action="store_true", help="Print a grounded migration plan + write MIGRATION_PLAN.md (B14)")
    ap.add_argument("--verify", action="store_true",
                    help="Statically verify the generated fix: apply it in isolation, re-parse, "
                         "re-run impact, compare before/after (B16). Writes out/VERIFICATION.md + "
                         "out/verification.json. No queries are executed.")
    ap.add_argument("--approve", type=Path,
                    help="Apply EXACTLY the mutations listed in an approval manifest emitted "
                         "by an earlier REVIEW_REQUIRED run (B19.4). Single-use and bound to "
                         "that change + verdict + queue. A FAILED verification can never be "
                         "approved. Requires --approver and --write.")
    ap.add_argument("--approver",
                    help="Who is approving (e.g. you@example.com). Also read from BRA_APPROVER. "
                         "Never inferred — no approver, no approval.")
    ap.add_argument("--manifest-dir", type=Path,
                    help="Where approval manifests are written/read (default: out/)")
    ap.add_argument("--sweep", action="store_true",
                    help="Overnight Catalog Sweep (B21): assess EVERY candidate column change "
                         "in the catalog with the same impact -> fix -> verify chain, and emit "
                         "a ranked ledger to out/SWEEP.md + out/SWEEP.html + out/sweep.json. "
                         "READ-ONLY — a sweep never writes to DataHub.")
    ap.add_argument("--sweep-limit", type=int,
                    help="Assess only the N riskiest candidates (fast demo run). The ledger "
                         "states that it is partial; unassessed candidates are not implied safe.")
    return ap


def apply_approval(wb, manifest_path, report, fixes, verification=None,
                   approver: str | None = None, now=None):
    """The CLI's approval entry point, factored out so it is directly testable.

    Deliberately thin: every refusal lives in `approval.validate_approval()`, so the CLI
    cannot accidentally be more permissive than the API. In particular a FAILED
    verification is refused here exactly as it is refused everywhere else — B19.5 tests
    this same function.
    """
    return wb.approve(manifest_path, report, fixes, verification=verification,
                      approver=approver, now=now)


def _main(args) -> None:
    if args.loop:
        from .loop import print_loop_summary, run_loop

        results = run_loop(
            args.loop, write=args.write, out_dir=args.out,
            gms_url=os.getenv("DATAHUB_GMS_URL", ""), token=os.getenv("DATAHUB_TOKEN", ""),
        )
        print_loop_summary(results)
        return

    catalog = _load_catalog(args)

    if args.fragility:
        from .fragility import fragility_leaderboard, render_html as frag_html, render_markdown, render_text

        rows = fragility_leaderboard(catalog, top=args.top)
        print(render_text(rows, catalog.name))
        if args.html:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(frag_html(rows, catalog.name))
            print(f"Fragility HTML -> {args.html}")
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps([r.__dict__ for r in rows], indent=2))
            print(f"Fragility JSON -> {args.json}")
        return

    if args.sweep:
        # B21 — the whole-catalog pass. Deliberately returns before any write-back code is
        # even reached: a sweep is read-only, and the clearest way to guarantee that is for
        # the write path to be unreachable from here.
        from .report_sweep import render_sweep_html, render_sweep_md, sweep_json
        from .sweep import BUCKET_LABEL, BUCKET_ORDER, sweep

        repo_root = args.repo_root or (args.catalog.parent if args.catalog else Path("."))
        res = sweep(catalog, limit=args.sweep_limit, repo_root=repo_root)

        print("\n" + "=" * 78)
        print(f"  CATALOG SWEEP — {catalog.name}")
        print("=" * 78)
        print(f"  {res.header_line()}")
        print("-" * 78)
        for b in BUCKET_ORDER:
            rows = res.by_bucket()[b]
            print(f"  {BUCKET_LABEL[b]:<22} {len(rows):>4}")
            for e in rows[:8]:
                extra = f" [{e.basis}]" if e.basis else ""
                print(f"       {e.ref:<34} {e.risk_level:<9} "
                      f"breaks={e.breaks} unknown={e.unknown}{extra}")
            if len(rows) > 8:
                print(f"       … {len(rows) - 8} more (see the ledger)")
        print("=" * 78)
        print("  READ-ONLY: nothing was written to DataHub. No query was executed.")
        print("=" * 78)

        outdir = Path("out")
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "SWEEP.md").write_text(render_sweep_md(res))
        (outdir / "SWEEP.html").write_text(render_sweep_html(res))
        (outdir / "sweep.json").write_text(json.dumps(sweep_json(res), indent=2))
        print(f"Sweep ledger -> {outdir / 'SWEEP.md'}  ·  {outdir / 'SWEEP.html'}  ·  "
              f"{outdir / 'sweep.json'}")
        return

    change = _parse_change(args)
    report = compute_impact(catalog, change)
    _print_blast_radius(report)

    # Generate mechanical fixes for impacted dbt models.
    from .fixgen import generate_fixes

    repo_root = args.repo_root or (args.catalog.parent if args.catalog else Path("."))
    fixes = generate_fixes(catalog, change, report, repo_root)
    for fx in fixes:
        state = "applicable" if fx.applicable and fx.changed else "needs review"
        print(f"FIX ({fx.method}, {state}): {fx.asset_name} — {fx.path}")
        if fx.diff:
            print(fx.diff)

    # Proof-carrying verification (B16) — STATIC: nothing is executed.
    verification = None
    if args.verify:
        from .verify import render_verification_md, verification_json, verify_migration

        combined = "".join(fx.diff for fx in fixes if fx.diff)
        verification = verify_migration(
            change, report, combined, repo_root, catalog=catalog,
            expected_files=[fx.path for fx in fixes if fx.path] or None,
        )
        _print_verification(verification)
        outdir = Path("out")
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "VERIFICATION.md").write_text(render_verification_md(verification))
        (outdir / "verification.json").write_text(
            json.dumps(verification_json(verification), indent=2))
        print(f"Verification -> {outdir / 'VERIFICATION.md'}  ·  {outdir / 'verification.json'}")

    # Grounded migration plan (B14) — derived facts only.
    plan = None
    if args.plan:
        from .planner import plan_from_report, render_plan_md

        plan = plan_from_report(report, fixes, verification=verification)
        plan_md = render_plan_md(plan)
        print("\n" + plan_md)
        plan_path = Path("MIGRATION_PLAN.md")
        plan_path.write_text(plan_md)
        print(f"Migration plan -> {plan_path}")

    # Write-back (gated dry-run by default).
    from .writeback import WriteBack

    wb = WriteBack(
        gms_url=os.getenv("DATAHUB_GMS_URL", ""),
        token=os.getenv("DATAHUB_TOKEN", ""),
        dry_run=not args.write,
        require_review=args.require_review,
        manifest_dir=args.manifest_dir,
    )
    print("\nWRITE-BACK" + (" (dry-run)" if not args.write else "") + ":")
    if verification is None:
        print("  gate: no verification was run (--verify not given) — nothing is auto-applied. "
              "A migration is written automatically only when static verification returns PASS.")
    elif not verification.auto_applicable:
        print(f"  gate: verification {verification.status} — every mutation queued for a human.")

    if args.approve:
        # B19.4/B19.5 — the human-approval route. Refusals are loud and apply nothing;
        # `validate_approval()` owns every rule, so the CLI cannot be more permissive
        # than the API.
        from .approval import ApprovalError

        approver = args.approver or os.getenv("BRA_APPROVER") or None
        try:
            res, assessment = apply_approval(wb, args.approve, report, fixes,
                                             verification=verification, approver=approver)
        except ApprovalError as e:
            print(f"\n  \033[91mAPPROVAL REFUSED\033[0m — {e}")
            print("  Nothing was applied.")
            raise SystemExit(2) from e
    else:
        # `wb.run()` prints the summary itself, straight from the counters, so no surface
        # here can restate it differently (B17.4).
        res, assessment = wb.run(report, fixes, verification=verification)

    # Optional reports.
    if args.html:
        from .report_html import render_html

        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(report, fixes, assessment, plan=plan,
                                         verification=verification, writeback=res))
        print(f"HTML report -> {args.html}")
    if args.pr_comment:
        from .report_pr import render_pr_comment

        args.pr_comment.parent.mkdir(parents=True, exist_ok=True)
        args.pr_comment.write_text(render_pr_comment(report, fixes, assessment,
                                                    verification=verification, writeback=res))
        print(f"PR comment -> {args.pr_comment}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = _report_json(report, fixes)
        if verification is not None:
            from .verify import verification_json

            payload["verification"] = verification_json(verification)
        payload["writeback"] = {**res.counts(), "dry_run": res.dry_run,
                                "summary": res.summary_line(), "failed": res.failed}
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"JSON report -> {args.json}")


def _report_json(report, fixes) -> dict:
    return {
        "change": report.change.describe(),
        "catalog": report.catalog,
        "target_urn": report.target_urn,
        "counts": report.counts(),
        "risk": report.risk(),
        "coverage": report.coverage(),
        "review_required": report.review_required(),
        "verdicts": [
            {
                "query_id": v.query_id,
                "verdict": v.verdict.value,
                "usage": v.usage,
                "clauses": v.clauses,
                "confidence": v.confidence,
                "team": v.team,
                "runs": v.runs,
                "asset": v.asset_name,
                "asset_type": v.asset_type,
                "reason": v.reason,
            }
            for v in report.verdicts
        ],
        "fixes": [
            {"asset": fx.asset_name, "path": fx.path, "method": fx.method,
             "applicable": fx.applicable, "needs_review": fx.needs_review}
            for fx in fixes
        ],
        "notes": report.notes,
    }


if __name__ == "__main__":
    main()
