"""B20.3 evidence — the human-approval audit, as it lands in DataHub.

Captures the four things B20.3 claims, on the REAL emit path:

    1. flagship REVIEW_REQUIRED -> manifest -> human-approved write, and the
       structured properties that actually crossed the SDK boundary
    2. the PASS auto-write path carrying NO approver field of any kind
    3. a partial failure recorded with the real numbers
    4. a refused approval recording nothing at all

The DataHub CLIENT is stubbed, and nothing above it is: `WriteBack._emit()` dispatches
for real, `_set_structured_properties()` defines-then-assigns for real, and real
`MetadataChangeProposalWrapper` / aspect classes are constructed. What is printed is
decoded from the aspect's own wire form (`to_obj()`), not from the local
`AssessmentDoc` — a document we return to ourselves proves nothing about the catalog.

`aspects` models the one DataHub behaviour that matters here: an emitted aspect
REPLACES the stored one, which is why the audit emit has to carry the base properties
along with it.

Run:  PATH=~/bra/venv/bin:$PATH python scripts/b20_3_approval_audit_run.py
Public/synthetic fixtures only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autopilot.approval import ApprovalError, load_manifest  # noqa: E402
from autopilot.catalog import load_catalog  # noqa: E402
from autopilot.fixgen import generate_fixes  # noqa: E402
from autopilot.impact import compute_impact  # noqa: E402
from autopilot.schema import ChangeSpec  # noqa: E402
from autopilot.verify import verify_migration  # noqa: E402
from autopilot.writeback import WriteBack  # noqa: E402

AUDIT_KEYS = [
    "blast_radius_approved_by",
    "blast_radius_approved_at",
    "blast_radius_manifest_id",
    "blast_radius_verification_status_at_approval",
    "blast_radius_approved_writes",
    "blast_radius_approved_failures",
]


class CapturingGraph:
    """Stands in for `DataHubGraph` at the client seam. Keeps every proposal."""

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


def decode(aspect) -> dict[str, str]:
    return {a["propertyUrn"].rsplit(":", 1)[-1]: a["values"][0]["string"]
            for a in aspect.to_obj()["properties"]}


def state(graph: CapturingGraph, urn: str) -> dict[str, str]:
    """What the catalog would hold for `urn` after every emit — the read-back."""
    aspect = graph.aspects.get((urn, "structuredProperties"))
    return decode(aspect) if aspect is not None else {}


def live(graph, out_dir: Path, dry_run: bool = False) -> WriteBack:
    wb = WriteBack(gms_url="http://stub-gms", token="stub", dry_run=dry_run,
                   assessment_dir=out_dir, manifest_dir=out_dir)
    wb._graph = graph
    return wb


def head(text: str) -> None:
    print("\n" + "=" * 88)
    print(f"  {text}")
    print("=" * 88)


def prepare(catalog_path: Path, change_str: str):
    catalog = load_catalog(catalog_path)
    change = ChangeSpec.parse(*_split(change_str))
    report = compute_impact(catalog, change)
    fixes = generate_fixes(catalog, change, report, catalog_path.parent)
    v = verify_migration(change, report, "".join(fx.diff for fx in fixes if fx.diff),
                         catalog_path.parent, catalog=catalog,
                         expected_files=[fx.path for fx in fixes if fx.path] or None)
    return report, fixes, v


def _split(change_str: str):
    op, target = change_str.split(" ", 1)
    dataset, column = target.rsplit(".", 1)
    return dataset, column, op


def show_properties(label: str, props: dict[str, str]) -> None:
    print(f"\n  {label}")
    for k in AUDIT_KEYS:
        mark = "AUDIT " if k in props else "absent"
        print(f"    [{mark}] {k:<48} {props.get(k, '—')}")
    base = [k for k in props if k not in AUDIT_KEYS]
    print(f"    base assessment properties still present: {len(base)}")
    print(f"      {', '.join(sorted(base)[:6])} …")


def main() -> int:
    out = ROOT / "out"
    scratch = out / "b20_3_scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    # ---- 1. flagship REVIEW_REQUIRED -> manifest -> approved write ---------------
    head("B20.3 (1) — flagship REVIEW_REQUIRED -> manifest -> HUMAN-APPROVED write")
    report, fixes, v = prepare(ROOT / "examples" / "showcase-ecommerce" / "catalog.json",
                               "drop analytics.fct_orders.customer_zip")
    print(f"  verification      {v.status}  ({', '.join(v.reasons)})")
    dry = WriteBack(dry_run=True, assessment_dir=scratch, manifest_dir=scratch)
    queued, _ = dry.run(report, fixes, verification=v)
    manifest_path = Path(queued.manifest_path)
    manifest = load_manifest(manifest_path)
    print(f"  manifest          {manifest.manifest_id}   "
          f"{len(manifest.mutations)} mutation(s) awaiting a human")
    print(f"  manifest discloses the audit? "
          f"{'blast_radius_approved_by' in manifest_path.with_suffix('.md').read_text()}")

    graph = CapturingGraph()
    res, doc = live(graph, scratch).approve(manifest_path, report, fixes, verification=v,
                                           approver="reviewer@example.com")
    emitted = state(graph, report.target_urn)
    show_properties("STRUCTURED PROPERTIES AS EMITTED (decoded from the aspect wire form):",
                    emitted)
    print(f"\n    approved set applied exactly?  "
          f"{res.written_human_approved == queued.queued_for_review}")
    print(f"    written_auto                   {len(res.written_auto)}")
    print(f"    written_human_approved         {len(res.written_human_approved)}")
    print(f"    reconciles()                   {res.reconciles()}")
    print(f"    audit_status                   {res.audit_status}")
    print(f"    recorded writes == real writes {emitted['blast_radius_approved_writes']}"
          f" == {len(res.written_human_approved)}")

    # ---- 2. the PASS auto-write path carries no approver field -------------------
    head("B20.3 (2) — PASS auto-write: NO approver field, anywhere (regression guard)")
    p_report, p_fixes, p_v = prepare(
        ROOT / "examples" / "verified-migration" / "catalog.json",
        "drop analytics.fct_signups.referrer_code")
    print(f"  verification      {p_v.status}  ({', '.join(p_v.reasons)})")
    p_graph = CapturingGraph()
    p_res, _p_doc = live(p_graph, scratch).run(p_report, p_fixes, verification=p_v)
    p_state = state(p_graph, p_report.target_urn)
    show_properties("STRUCTURED PROPERTIES AS EMITTED:", p_state)
    approvalish = sorted(k for k in p_state if "approv" in k.lower())
    print(f"\n    written_auto                   {len(p_res.written_auto)}")
    print(f"    written_human_approved         {len(p_res.written_human_approved)}")
    print(f"    audit_status                   {p_res.audit_status or '(none — no approval)'}")
    print(f"    approval-shaped keys emitted   {approvalish or 'NONE'}")

    # ---- 3. partial failure, recorded honestly ----------------------------------
    head("B20.3 (3) — partial failure: the recorded counts are the REAL counts")
    q_report, q_fixes, q_v = prepare(
        ROOT / "examples" / "showcase-ecommerce" / "catalog.json",
        "drop analytics.fct_orders.customer_zip")
    dry2 = WriteBack(dry_run=True, assessment_dir=scratch, manifest_dir=scratch)
    q_queued, _ = dry2.run(q_report, q_fixes, verification=q_v)
    f_graph = CapturingGraph(fail_aspects=("globalTags",))
    f_res, _f_doc = live(f_graph, scratch).approve(
        Path(q_queued.manifest_path), q_report, q_fixes, verification=q_v,
        approver="reviewer@example.com")
    f_state = state(f_graph, q_report.target_urn)
    print(f"\n    total approved                 {f_res.total}")
    print(f"    written_human_approved         {len(f_res.written_human_approved)}")
    print(f"    failed                         {len(f_res.failed)}")
    print(f"    reconciles()                   {f_res.reconciles()}")
    print(f"    recorded _approved_writes      {f_state['blast_radius_approved_writes']}")
    print(f"    recorded _approved_failures    {f_state['blast_radius_approved_failures']}")
    print(f"    writes+failures == total       "
          f"{int(f_state['blast_radius_approved_writes']) + int(f_state['blast_radius_approved_failures']) == f_res.total}")

    # ---- 4. refusals record nothing --------------------------------------------
    head("B20.3 (4) — a refused approval records NOTHING (no blank approver in the graph)")
    for label, kwargs, rep, ver in [
        ("no approver",      dict(approver=None),                   report, v),
        ("blank approver",   dict(approver="   "),                  report, v),
        ("against a FAIL",   dict(approver="reviewer@example.com"), report, _fail_v(report)),
    ]:
        r_graph = CapturingGraph()
        dry3 = WriteBack(dry_run=True, assessment_dir=scratch, manifest_dir=scratch)
        r_queued, _ = dry3.run(rep, fixes, verification=v)
        try:
            live(r_graph, scratch).approve(Path(r_queued.manifest_path), rep, fixes,
                                          verification=ver, **kwargs)
            print(f"    {label:<18} NOT REFUSED  <-- would be a bug")
        except ApprovalError as e:
            print(f"    {label:<18} REFUSED {e.code:<22} aspects emitted: "
                  f"{len(r_graph.mcps)}   audit recorded: "
                  f"{bool(state(r_graph, rep.target_urn))}")
    return 0


def _fail_v(report):
    """A FAIL verdict for the same change: a patch that cannot apply."""
    catalog = load_catalog(ROOT / "examples" / "showcase-ecommerce" / "catalog.json")
    return verify_migration(report.change, report,
                            "--- a/models/nope.sql\n+++ b/models/nope.sql\n@@ -1 +1 @@\n-a\n+b\n",
                            ROOT / "examples" / "showcase-ecommerce", catalog=catalog)


if __name__ == "__main__":
    raise SystemExit(main())
