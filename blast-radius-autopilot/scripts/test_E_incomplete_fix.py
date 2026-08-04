"""TEST E — the incomplete-fix path: the exact `file:line` is named.

Repeatable version of what `out/verification_partial_run.txt` captured (that artifact predates
B18/B19 and its write-back wording is stale). Takes the PASS example and patches only ONE of
the two breaking consumers, plus deliberately leaves a `GROUP BY` reference behind in the other
— exactly the shape a half-finished migration has.

WHAT THIS DEMONSTRATES, PRECISELY:

    an incomplete fix -> REVIEW_REQUIRED, with `fix_incomplete_column_still_referenced`
                         and the residual reference reported as `path:line: <the text>`

It is **not** a FAIL, and that is a deliberate B16 decision, not a gap. The first cut of the
scope check failed any diff whose *added* lines mentioned the dropped column, which misfired on
a legitimately regenerated rewrite and turned a partial fix into a bogus FAIL with the wrong
reason ("files outside scope"). It was split in two: a file-level scope violation is a FAIL,
while a residual column reference is an *observation* that names the line and lets the impact
re-run decide severity. Here the re-run still finds a breaking consumer, so the verdict is
REVIEW_REQUIRED — improved but incomplete, which is what actually happened.

An incomplete fix DOES contribute to a FAIL when the impact re-run shows the breaks did not
move at all: the live MCP ORDER_DETAILS target fails on `breaks_not_reduced` +
`fix_incomplete_column_still_referenced` together (`out/b20_mcp_live_run.txt`).

Run: python scripts/test_E_incomplete_fix.py
"""

from __future__ import annotations

import difflib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autopilot.catalog import load_catalog  # noqa: E402
from autopilot.impact import compute_impact  # noqa: E402
from autopilot.schema import ChangeSpec  # noqa: E402
from autopilot.verify import render_verification_md, verify_migration  # noqa: E402

EX = ROOT / "examples" / "verified-migration"
CHANGE = ChangeSpec.parse("analytics.fct_signups", "referrer_code", "drop")


def main() -> int:
    catalog = load_catalog(EX / "catalog.json")
    report = compute_impact(catalog, CHANGE)
    print(f"BEFORE   breaks={report.counts()['breaks']}  "
          f"coverage={report.coverage()['line']}")

    # A git repo the patch can be applied into, so `git apply` behaves as in a real run.
    tmp = Path(tempfile.mkdtemp())
    repo = tmp / "repo"
    shutil.copytree(EX, repo)
    for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=repo, check=True)

    # THE INCOMPLETE FIX, hand-authored so it is unambiguous:
    #
    #   rpt_signups_by_plan.sql  fully fixed — the projection is dropped, nothing left behind
    #   rpt_referrals.sql        HALF fixed — the projection is dropped, but the rewrite leaves
    #                            a WHERE that still filters on the dropped column. This is the
    #                            realistic shape: a regenerated model whose SELECT was updated
    #                            and whose predicate was not.
    # Derived from the real file contents (not hand-typed) so the diff always applies.
    PLAN = "dbt_project/models/rpt_signups_by_plan.sql"
    REFS = "dbt_project/models/rpt_referrals.sql"

    def transform(rel: str, src: str) -> str:
        # Drop the projection line in both files...
        kept = [ln for ln in src.splitlines(keepends=True)
                if ln.strip().rstrip(",") != "s.referrer_code"]
        out = "".join(kept)
        if rel == REFS:
            # ...and in this one, leave the predicate behind: half-migrated.
            if not out.endswith("\n"):
                out += "\n"
            out += "WHERE s.referrer_code IS NOT NULL\n"
        return out

    diffs = []
    for rel in (PLAN, REFS):
        src = (repo / rel).read_text()
        after = transform(rel, src)
        assert after != src, rel
        diffs.append("".join(difflib.unified_diff(
            src.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3)))

    patch = "".join(diffs)
    print(f"PATCH    {len(diffs)} file(s), {len(patch.splitlines())} diff lines")

    v = verify_migration(CHANGE, report, patch, repo, catalog=catalog)

    print(f"\nVERDICT  {v.status}")
    print(f"         breaks {v.before.get('breaks')} -> {v.after.get('breaks')}   "
          f"coverage {v.coverage_after.get('line')}")
    print("         reasons:")
    for r in v.reasons:
        print(f"           - {r}")

    residual = getattr(v, "residual_references", None) or []
    print("\nRESIDUAL REFERENCES — the exact file:line the fix missed:")
    if not residual:
        print("           (none reported)")
    for item in residual:
        print(f"           {item}")

    (ROOT / "out" / "test_E_incomplete_fix.md").write_text(render_verification_md(v))
    shutil.rmtree(tmp, ignore_errors=True)

    # What this test asserts: an incomplete fix names its residual line, and is
    # REVIEW_REQUIRED rather than FAIL (see the module docstring).
    ok = (v.status == "REVIEW_REQUIRED"
          and "fix_incomplete_column_still_referenced" in v.reasons
          and bool(residual)
          and any(":" in str(x) and "referrer_code" in str(x) for x in residual))
    print(f"\nEXPECTED REVIEW_REQUIRED + fix_incomplete_column_still_referenced + a named "
          f"file:line -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
