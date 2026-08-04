"""B16 — Proof-Carrying Migrations: turn a *generated* fix into a *verified* fix.

A generated diff is a proposal, not a result. This module treats it as a hypothesis and
tries to falsify it:

    1. ISOLATE   copy the repo to a throwaway workspace; apply the patch THERE.
                 The real working tree is never touched, on any path, including errors.
    2. VALIDATE  re-parse every patched SQL file with sqlglot; confirm the diff stays
                 inside the files the fix was allowed to touch.
    3. RE-RUN    recompute impact over the PATCHED corpus with the SAME analyzer and
                 the SAME change.
    4. COMPARE   per-consumer verdict transitions + count/coverage deltas.
    5. VERDICT   PASS / REVIEW_REQUIRED / FAIL, each with machine-readable reasons.

WHAT A PASS PROVES
    The patch applies cleanly, the patched SQL parses, the diff stayed in scope, and the
    analyzer can no longer find a broken or unassessed consumer.

WHAT A PASS DOES NOT PROVE
    That anything ran. This is STATIC verification: no query is executed, no warehouse
    or database is contacted, no data is read, no dbt build is invoked. Nothing here is
    evidence about runtime behaviour, row counts, performance, or results. A reviewer
    still owns the decision.

FAIL-CLOSED
    The verifier re-runs the same analyzer whose blind spots B15 made visible, so a
    consumer it cannot read is a blind spot, not a clean result. Zero breaks over a
    partial corpus is never a PASS.

    A migration may PASS only when every known consumer is confidently assessed and
    no unresolved impact remains. Each of these caps the verdict at REVIEW_REQUIRED:

        UNKNOWN consumer / incomplete coverage  we could not read it            (B15)
        target dataset has NO known schema      we cannot check the column      (B19.1)
        AMBIGUOUS reference                     read it, cannot attribute it  (B17.1)
        remaining DEGRADES                      still runs, output changed    (B17.2)
        unmapped patched SQL file               its impact was not recomputed (B17.3)

    All of them live in ONE place — `_decide()`'s `_PASS_GATES` — so the conjunction
    has a single source of truth and a new gate cannot be bypassed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import sqlglot

from .impact import compute_impact
from .schema import Catalog, ChangeSpec, ImpactReport, Op, Query, Verdict

# Verdict values -----------------------------------------------------------------
PASS = "PASS"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
FAIL = "FAIL"

# Machine-readable reason codes. Stable strings — safe to assert on and to key
# dashboards off.
R_NO_PATCH = "no_patch_provided"
R_APPLY_FAILED = "patch_apply_failed"
R_UNPARSEABLE = "patched_sql_unparseable"
R_SCOPE = "scope_violation"
R_BREAKS_ELIMINATED = "breaks_eliminated"
R_BREAKS_REMAINING = "breaks_remaining"
R_BREAKS_NOT_REDUCED = "breaks_not_reduced"
R_BREAKS_INCREASED = "breaks_increased"
R_NEW_DEGRADES = "new_degrades"
R_DEGRADES_REMAINING = "degrades_remaining"
R_UNKNOWN_PRESENT = "unknown_consumers_present"
R_AMBIGUOUS_PRESENT = "ambiguous_consumers_present"
R_PATCHED_FILE_UNMAPPED = "patched_file_unmapped"
R_COVERAGE_INCOMPLETE = "coverage_incomplete"
R_SAFE_REGRESSED = "safe_consumer_regressed"
R_MANUAL_WORK = "manual_work_remaining"
R_FIX_INCOMPLETE = "fix_incomplete_column_still_referenced"
# B18.1 — the change itself did not resolve, so no count below it means anything.
R_TARGET_NOT_FOUND = "target_not_found"
R_COLUMN_NOT_FOUND = "column_not_found"
# B19.1 — the dataset resolved but we cannot see its columns at all.
R_SCHEMA_UNKNOWN = "schema_unknown"
# B18.2 — the diff removed or moved a consumer's definition instead of editing it.
R_FILE_DELETED = "patched_file_deleted"
R_FILE_RENAMED = "patched_file_renamed"

_STATIC_NOTE = (
    "STATIC verification only: the patch was applied in an isolated copy, the patched "
    "SQL was re-parsed, and column-level impact was recomputed. No queries were "
    "executed, no warehouse was contacted, and no data was read. This is not evidence "
    "about runtime behaviour or results."
)

# Verdicts ordered worst-first, for detecting regressions.
_RANK = {Verdict.BREAKS: 0, Verdict.DEGRADES: 1, Verdict.UNKNOWN: 2, Verdict.SAFE: 3}


@dataclass
class VerdictTransition:
    """How one consumer's verdict moved between before and after."""

    consumer: str
    query_id: str
    before: str
    after: str
    regressed: bool = False
    improved: bool = False
    asset_type: str | None = None

    def describe(self) -> str:
        arrow = "→"
        tag = " (REGRESSED)" if self.regressed else " (improved)" if self.improved else ""
        return f"{self.consumer}: {self.before} {arrow} {self.after}{tag}"


@dataclass
class VerificationResult:
    status: str = REVIEW_REQUIRED
    reasons: list[str] = field(default_factory=list)
    patch_applied: bool = False
    files_patched: list[str] = field(default_factory=list)
    parse_ok: bool = True
    parse_errors: list[str] = field(default_factory=list)
    scope_ok: bool = True
    scope_violations: list[str] = field(default_factory=list)
    residual_references: list[str] = field(default_factory=list)
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    coverage_before: dict = field(default_factory=dict)
    coverage_after: dict = field(default_factory=dict)
    transitions: list[VerdictTransition] = field(default_factory=list)
    diff: str = ""
    manual_work_remaining: list[str] = field(default_factory=list)
    unknown_consumers: list[str] = field(default_factory=list)
    ambiguous_consumers: list[str] = field(default_factory=list)
    # B17.3 — coverage of the DIFF, tracked explicitly rather than inferred. Every
    # patched .sql file is either mapped to the query whose impact was recomputed
    # from it, or listed as a gap that blocks PASS.
    file_query_map: dict[str, str] = field(default_factory=dict)
    unmapped_files: list[str] = field(default_factory=list)
    # B18.2 — destructive edits, tracked as first-class outcomes next to the two
    # above. Every .sql path the diff accounts for lands in exactly one of
    # file_query_map / unmapped_files / deleted_files / renamed_files.
    deleted_files: list[str] = field(default_factory=list)
    renamed_files: list[tuple[str, str]] = field(default_factory=list)
    unresolved_renames: list[tuple[str, str]] = field(default_factory=list)
    diff_sql_paths: list[str] = field(default_factory=list)
    # B18.1 — did the change resolve against the catalog at all?
    target_resolved: bool = True
    target_problem: str = ""
    # B19.1 — did we actually know the target's columns? An empty schema is not proof
    # the column is absent (that would be a FAIL), nor proof the migration is complete
    # (that would be a PASS). It is a gap, and it caps the verdict at REVIEW_REQUIRED.
    schema_known: bool = True
    # Which resolution failed: R_TARGET_NOT_FOUND or R_COLUMN_NOT_FOUND. Set by
    # verify_migration, turned into a verdict by _decide() — the only place that may.
    _target_reason: str = ""
    isolation_dir: str | None = None
    verified_at: str = ""
    method: str = "static"
    change: str = ""
    notes: list[str] = field(default_factory=list)
    apply_stderr: str = ""

    @property
    def passed(self) -> bool:
        return self.status == PASS

    @property
    def auto_applicable(self) -> bool:
        """Only a PASS may be written back without a human. REVIEW_REQUIRED and FAIL
        both route to approval — an unproven migration is not a proven one."""
        return self.status == PASS

    def deltas(self) -> dict[str, int]:
        keys = set(self.before) | set(self.after)
        return {k: int(self.after.get(k, 0)) - int(self.before.get(k, 0)) for k in keys}

    def regressions(self) -> list[VerdictTransition]:
        return [t for t in self.transitions if t.regressed]

    def improvements(self) -> list[VerdictTransition]:
        return [t for t in self.transitions if t.improved]

    def summary_line(self) -> str:
        d = self.deltas()
        return (
            f"{self.status} — breaks {self.before.get('breaks', 0)}→{self.after.get('breaks', 0)} "
            f"({d.get('breaks', 0):+d}), degrades {self.before.get('degrades', 0)}"
            f"→{self.after.get('degrades', 0)}, ambiguous {self.before.get('ambiguous', 0)}"
            f"→{self.after.get('ambiguous', 0)}, unassessed "
            f"{self.coverage_before.get('unassessed', 0)}"
            f"→{self.coverage_after.get('unassessed', 0)}, "
            f"coverage {self.coverage_after.get('line', 'n/a')}"
        )


# --- patch plumbing -------------------------------------------------------------

_PLUS_FILE = re.compile(r"^\+\+\+ (?:b/)?(.+?)\s*$", re.M)


_C_ESCAPES = {"\\": 0x5C, '"': 0x22, "a": 0x07, "b": 0x08, "f": 0x0C,
              "n": 0x0A, "r": 0x0D, "t": 0x09, "v": 0x0B}


def unquote_git_path(path: str) -> str:
    """Decode a path as `git diff` writes it (B19.2).

    With `core.quotepath=true` — the DEFAULT — git renders any path containing
    non-ASCII bytes in C-quoted form, and the quotes wrap the `a/`/`b/` prefix too::

        --- "a/models/r\303\251sum\303\251.sql"        # models/résumé.sql
        rename to "models/renamed caf\303\251.sql"     # models/renamed café.sql

    Read literally, `models/r\303\251sum\303\251.sql` matches no `Asset.dbt_path` on
    earth, so a deletion or rename of any non-ASCII-named model was silently dropped:
    detected by nothing, reported by nothing. Paths containing only spaces are *not*
    quoted by git, so both forms have to work.

    The octal escapes are UTF-8 BYTES, so they are accumulated as bytes and decoded
    once at the end — decoding each escape separately would mangle every multi-byte
    character.
    """
    p = (path or "").strip()
    if len(p) < 2 or p[0] != '"' or p[-1] != '"':
        return p                      # already literal (core.quotepath=false, or ASCII)
    inner, out, i = p[1:-1], bytearray(), 0
    while i < len(inner):
        ch = inner[i]
        if ch != "\\" or i + 1 >= len(inner):
            out.extend(ch.encode("utf-8"))
            i += 1
            continue
        nxt = inner[i + 1]
        if nxt in _C_ESCAPES:
            out.append(_C_ESCAPES[nxt])
            i += 2
        elif inner[i + 1:i + 4].isdigit() and len(inner[i + 1:i + 4]) == 3 \
                and all(c in "01234567" for c in inner[i + 1:i + 4]):
            out.append(int(inner[i + 1:i + 4], 8))
            i += 4
        else:                         # unknown escape: keep the escaped char verbatim
            out.extend(nxt.encode("utf-8"))
            i += 2
    return out.decode("utf-8", errors="replace")


def _strip_ab(path: str) -> str:
    """Decode git's quoting, then drop its `a/` / `b/` diff prefix.

    Order matters: git quotes the WHOLE token including the prefix, so stripping
    before decoding would leave a stray quote on the front of the path.
    """
    p = unquote_git_path(path)
    return p[2:] if p.startswith(("a/", "b/")) else p


@dataclass
class DiffPaths:
    """Every path a diff touches, split by WHAT IT DID to that path (B18.2).

    `patched_files()` only ever looked at `+++ b/<path>`, which made two whole classes
    of edit invisible:

      * a DELETION writes `+++ /dev/null`, so the vanished file appeared nowhere; and
      * a pure RENAME carries no `---`/`+++` pair at all, only `rename from`/`rename to`.

    Both were then absent from the recomputation *and* absent from the report, so a
    consumer whose defining SQL had been removed or moved read as one that had become
    safe. A vanished consumer is not an unaffected consumer.
    """

    written: list[str] = field(default_factory=list)          # exists after the patch
    deleted: list[str] = field(default_factory=list)          # `+++ /dev/null`
    renamed: list[tuple[str, str]] = field(default_factory=list)   # (old, new)

    def sql_only(self) -> "DiffPaths":
        def is_sql(p: str) -> bool:
            return p.lower().endswith(".sql")
        return DiffPaths(
            written=[p for p in self.written if is_sql(p)],
            deleted=[p for p in self.deleted if is_sql(p)],
            renamed=[(o, n) for o, n in self.renamed if is_sql(o) or is_sql(n)],
        )

    def accounted_paths(self) -> list[str]:
        """The paths that must each land in exactly one outcome bucket.

        A rename is ONE logical file, so it is accounted for by its OLD path; the new
        path shows up in `written`/`file_query_map` when the diff also carried content
        for it, and is otherwise represented by the rename pair itself.
        """
        out: list[str] = []
        for p in [*self.written, *self.deleted, *(o for o, _n in self.renamed)]:
            if p not in out:
                out.append(p)
        return out


def parse_diff(patch: str) -> DiffPaths:
    """Split a unified/git diff into written / deleted / renamed paths.

    Handles both `git diff` output (with `diff --git` + `rename from/to` headers) and
    bare `difflib.unified_diff` output (which has only the `---`/`+++` pair).
    """
    dp = DiffPaths()
    minus: str | None = None
    rename_from: str | None = None
    for line in (patch or "").splitlines():
        if line.startswith("diff --git "):
            minus, rename_from = None, None
        elif line.startswith("rename from "):
            # `rename from`/`rename to` carry no a/ b/ prefix, but ARE quoted.
            rename_from = _strip_ab(line[len("rename from "):])
        elif line.startswith("rename to "):
            new = _strip_ab(line[len("rename to "):])
            if rename_from and (rename_from, new) not in dp.renamed:
                dp.renamed.append((rename_from, new))
            rename_from = None
        elif line.startswith("--- "):
            raw = line[4:].strip()
            minus = None if raw == "/dev/null" else _strip_ab(raw)
        elif line.startswith("+++ "):
            raw = line[4:].strip()
            if raw == "/dev/null":
                if minus and minus not in dp.deleted:
                    dp.deleted.append(minus)
            else:
                p = _strip_ab(raw)
                if p and p not in dp.written:
                    dp.written.append(p)
            minus = None
    return dp


def patched_files(patch: str) -> list[str]:
    """Files a unified diff writes to, in order, de-duplicated.

    Kept as the "what exists after the patch" list — deletions and renames are
    reported separately by `parse_diff()`, because they are different events.
    """
    return parse_diff(patch).written


def _apply_in_isolation(patch: str, repo: Path, workspace: Path) -> tuple[bool, str]:
    """Copy the repo (minus VCS metadata) into `workspace` and apply the patch there.

    `git apply` works outside a git repository, so .git is deliberately NOT copied:
    it keeps the copy cheap and makes it impossible to disturb the real repo's git
    state. Returns (applied, stderr).
    """
    shutil.copytree(repo, workspace, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "node_modules"))
    patch_file = workspace / "_b16_verify.patch"
    patch_file.write_text(patch)
    proc = subprocess.run(
        ["git", "apply", "--verbose", "_b16_verify.patch"],
        cwd=workspace, capture_output=True, text=True,
    )
    patch_file.unlink(missing_ok=True)
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def _reparse(workspace: Path, files: list[str], dialect: str) -> tuple[bool, list[str]]:
    """Every patched SQL file must still parse. Unverifiable SQL is not a PASS."""
    errors: list[str] = []
    for rel in files:
        if not rel.lower().endswith(".sql"):
            continue
        p = workspace / rel
        if not p.exists():
            errors.append(f"{rel}: patched file missing after apply")
            continue
        text = p.read_text()
        try:
            if sqlglot.parse_one(text, read=dialect) is None:
                errors.append(f"{rel}: sqlglot returned no expression")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{rel}: {type(e).__name__}: {str(e).splitlines()[0]}")
    return (not errors), errors


def _check_scope(patch: str, files: list[str], change: ChangeSpec,
                 allowed: list[str] | None) -> tuple[bool, list[str]]:
    """The diff must touch only files the fix was allowed to touch.

    Deliberately FILE-level only. An earlier version also failed any diff whose added
    lines mentioned the dropped column, which misfired: a *regenerated* rewrite re-emits
    surrounding lines (e.g. a GROUP BY it is not allowed to rewrite) with new
    indentation, so a legitimate partial fix looked like an out-of-scope edit. Whether
    the column is still referenced is a completeness question, not a scope question —
    `_residual_references` answers it, and the impact re-run measures the consequence.
    """
    violations: list[str] = []
    if allowed is not None:
        allowed_set = {a.replace("\\", "/") for a in allowed}
        for f in files:
            if f.replace("\\", "/") not in allowed_set:
                violations.append(f"{f}: outside the fix's declared scope")
    return (not violations), violations


def _residual_references(workspace: Path, files: list[str],
                         change: ChangeSpec) -> list[str]:
    """Patched files that STILL reference the column after the fix — i.e. the fix is
    incomplete. Not fatal on its own: the impact re-run decides the severity. Reported
    so a reviewer knows exactly which file to finish by hand."""
    if change.op is not Op.DROP:
        return []
    col = re.escape(change.column)
    out: list[str] = []
    for rel in files:
        if not rel.lower().endswith(".sql"):
            continue
        p = workspace / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if re.search(rf"\b{col}\b", line, re.I):
                out.append(f"{rel}:{i}: still references `{change.column}` — "
                           f"{line.strip()[:80]}")
    return out


def _resolve_target(catalog: Catalog, change: ChangeSpec) -> tuple[bool, bool, str, str]:
    """Does the change resolve against the catalog?

    Returns `(target_resolved, schema_known, reason_code, detail)`. Three outcomes, and
    they carry three different verdicts, because they are three different facts:

        dataset absent    -> resolved=False  FAIL      the change names nothing
        column absent     -> resolved=False  FAIL      the change is provably wrong
        schema EMPTY      -> known=False     REVIEW    we cannot tell either way

    B18.1 added the first two: a typo'd table or column produced an impact report over
    ZERO consumers, and zero breaks over zero consumers satisfied every count-based
    gate, so the verifier said PASS about a change it had never assessed. B19.1 adds
    the third, which is the subtler one — with no schema at all we cannot prove the
    column is absent (so FAIL would be a lie) and cannot prove the migration is
    complete (so PASS would be a lie). It is a gap, and gaps force review.
    """
    ds = catalog.dataset_by_name_or_urn(change.dataset)
    if ds is None:
        known = ", ".join(sorted(d.sql_name for d in catalog.datasets)[:8]) or "none"
        return False, True, R_TARGET_NOT_FOUND, (
            f"target dataset `{change.dataset}` was not found in catalog "
            f"`{catalog.name}` — nothing was assessed, so no count below describes "
            f"this change. Datasets the catalog does know: {known}"
        )
    if not ds.schema:
        return True, False, R_SCHEMA_UNKNOWN, (
            f"the catalog knows dataset `{ds.sql_name}` but records NO columns for it, "
            f"so we cannot confirm that `{change.column}` exists, that it was fully "
            f"removed, or that no other column shares its name. The reference-level "
            f"findings below stand on their own; the schema-level claim does not."
        )
    if not ds.has_column(change.column):
        cols = ", ".join(sorted(ds.schema)[:12])
        return False, True, R_COLUMN_NOT_FOUND, (
            f"column `{change.column}` is not in `{ds.sql_name}`'s schema — the "
            f"dataset resolved, the column did not. Columns it does have: {cols}"
        )
    return True, True, "", ""


def _patched_catalog(catalog: Catalog, workspace: Path, files: list[str],
                     rename_targets: tuple[str, ...] = (),
                     ) -> tuple[Catalog, dict[str, str], list[str]]:
    """Rebuild the catalog with each patched dbt model's SQL replaced by its patched
    content on disk. The link used is Asset.dbt_path -> Asset.defining_query_id.

    Returns (patched_catalog, file->query_id map, unmapped .sql files). The map is the
    audit trail for B17.3: it is the exact set of patched files whose effect on impact
    was actually recomputed. Anything not in it is a hole in the recomputation, and a
    hole in the recomputation is not a clean result.

    `rename_targets` are the NEW paths of renamed files (B18.2). They are considered
    for mapping — a file moved INTO a path the catalog maps is that consumer's new
    definition and must be re-analysed, not skipped — but they are never added to
    `unmapped`, because an unresolvable rename is reported by the rename gate instead
    of being double-counted as a coverage gap.
    """
    by_path = {}
    for a in catalog.assets:
        if a.dbt_path and a.defining_query_id:
            by_path[a.dbt_path.replace("\\", "/")] = a.defining_query_id
    known_queries = {q.query_id for q in catalog.queries}

    mapped: dict[str, str] = {}
    replaced: dict[str, str] = {}
    unmapped: list[str] = []
    written = set(files)
    for rel in [*files, *(r for r in rename_targets if r not in written)]:
        if not rel.lower().endswith(".sql"):
            continue          # non-SQL files carry no analysable impact
        key = rel.replace("\\", "/")
        qid = by_path.get(key)
        p = workspace / rel
        # A mapping only counts when it resolves all the way to a query we can
        # re-analyse AND the patched text is readable. A dangling defining_query_id
        # or a vanished file is a gap, not a mapping.
        if not qid or qid not in known_queries or not p.exists():
            if rel in written:
                unmapped.append(rel)
            continue
        mapped[rel] = qid
        replaced[qid] = p.read_text()

    new_queries = [
        Query(query_id=q.query_id, sql=replaced.get(q.query_id, q.sql), platform=q.platform,
              team=q.team, actor=q.actor, runs=q.runs, last_run=q.last_run)
        for q in catalog.queries
    ]
    patched = Catalog(
        name=catalog.name, datasets=catalog.datasets, queries=new_queries,
        assets=catalog.assets, sql_dialect=catalog.sql_dialect,
        require_review=catalog.require_review, compliance_note=catalog.compliance_note,
    )
    return patched, mapped, unmapped


def _transitions(before: ImpactReport, after: ImpactReport) -> list[VerdictTransition]:
    b = {v.query_id: v for v in before.verdicts}
    a = {v.query_id: v for v in after.verdicts}
    out: list[VerdictTransition] = []
    for qid in b.keys() | a.keys():
        bv, av = b.get(qid), a.get(qid)
        if bv is None or av is None:
            # A consumer that appeared or vanished between runs — surface it rather
            # than silently dropping it.
            present = av or bv
            out.append(VerdictTransition(
                consumer=(present.asset_name or qid), query_id=qid,
                before=(bv.verdict.value if bv else "ABSENT"),
                after=(av.verdict.value if av else "ABSENT"),
                asset_type=present.asset_type,
            ))
            continue
        if bv.verdict is av.verdict:
            continue
        worse = _RANK[av.verdict] < _RANK[bv.verdict]
        out.append(VerdictTransition(
            consumer=(av.asset_name or qid), query_id=qid,
            before=bv.verdict.value, after=av.verdict.value,
            regressed=worse, improved=not worse, asset_type=av.asset_type,
        ))
    out.sort(key=lambda t: (not t.regressed, t.consumer))
    return out


def _manual_work(after: ImpactReport, catalog: Catalog) -> list[str]:
    """Consumers still impacted that no mechanical fix can reach (no dbt file)."""
    fixable = {a.urn for a in catalog.assets if a.dbt_path}
    out: list[str] = []
    for v in after.impacted():
        if v.asset_urn and v.asset_urn in fixable:
            continue
        out.append(v.asset_name or v.query_id)
    return sorted(set(out))


# --- the verifier ---------------------------------------------------------------

def verify_migration(
    change: ChangeSpec,
    before_impact: ImpactReport,
    patch: str,
    repo: str | Path,
    *,
    catalog: Catalog,
    dialect: str | None = None,
    expected_files: list[str] | None = None,
    now: datetime | None = None,
) -> VerificationResult:
    """Verify a generated migration statically. Never mutates `repo`.

    `catalog` is keyword-only and required: recomputing impact needs the corpus, and
    `before_impact` carries only the catalog's *name*.
    """
    now = now or datetime.now(timezone.utc)
    dialect = dialect or catalog.sql_dialect
    repo = Path(repo)

    res = VerificationResult(
        before=before_impact.counts(),
        coverage_before=before_impact.coverage(),
        diff=patch or "",
        verified_at=now.isoformat(timespec="seconds"),
        change=change.describe(),
        notes=[_STATIC_NOTE],
    )

    # B18.1 — resolve the change FIRST. Every count below is meaningless if the thing
    # being changed was never found, and "meaningless" must not read as "clean".
    resolved, schema_known, target_code, target_detail = _resolve_target(catalog, change)
    res.target_resolved = resolved
    res.schema_known = schema_known
    res.target_problem = target_detail
    res._target_reason = target_code          # consumed by _decide()
    if target_detail:
        res.notes.append(target_detail)

    if not (patch or "").strip():
        res.status = FAIL
        res.reasons = _dedupe([R_NO_PATCH] + ([target_code] if target_code else []))
        res.after, res.coverage_after = res.before, res.coverage_before
        res.notes.append("No patch was supplied, so there is nothing to verify.")
        return res

    diff = parse_diff(patch).sql_only()
    res.files_patched = parse_diff(patch).written
    res.deleted_files = diff.deleted
    res.renamed_files = diff.renamed
    res.diff_sql_paths = diff.accounted_paths()
    for old, new in diff.renamed:
        res.notes.append(
            f"the diff MOVES `{old}` to `{new}` rather than editing it in place"
        )
    for rel in diff.deleted:
        res.notes.append(f"the diff DELETES `{rel}`")

    # Default the allowed set to the catalog's own dbt models, so a diff that wanders
    # into unrelated files is caught even when no explicit scope is passed.
    allowed = expected_files
    if allowed is None:
        allowed = [a.dbt_path for a in catalog.assets if a.dbt_path] or None

    workspace = Path(tempfile.mkdtemp(prefix="bra-verify-"))
    res.isolation_dir = str(workspace)
    try:
        applied, stderr = _apply_in_isolation(patch, repo, workspace)
        res.patch_applied = applied
        res.apply_stderr = stderr
        if not applied:
            res.status = FAIL
            res.reasons = _dedupe([R_APPLY_FAILED]
                                  + ([res._target_reason] if res._target_reason else []))
            res.after, res.coverage_after = res.before, res.coverage_before
            res.notes.append(
                "`git apply` refused the patch in the isolated copy; the real working "
                "tree was not touched."
            )
            return res

        res.parse_ok, res.parse_errors = _reparse(workspace, res.files_patched, dialect)
        # Scope covers every path the diff touched, not just the ones it wrote: a diff
        # that deletes or moves a file outside its declared scope is just as much an
        # out-of-scope edit as one that rewrites it.
        touched = _dedupe([*res.files_patched, *diff.deleted,
                           *(p for pair in diff.renamed for p in pair)])
        res.scope_ok, res.scope_violations = _check_scope(patch, touched, change, allowed)
        res.residual_references = _residual_references(workspace, res.files_patched, change)

        patched_cat, mapped, unmapped = _patched_catalog(
            catalog, workspace, res.files_patched,
            rename_targets=tuple(new for _old, new in diff.renamed),
        )
        res.file_query_map = mapped
        res.unmapped_files = unmapped
        # A rename is only resolved when the NEW path was actually re-analysed AND the
        # OLD path was not itself a consumer's recorded definition. Otherwise a
        # consumer just lost the file the catalog points at.
        catalog_paths = {a.dbt_path.replace("\\", "/")
                         for a in catalog.assets if a.dbt_path}
        res.unresolved_renames = [
            (old, new) for old, new in diff.renamed
            if new not in mapped or old.replace("\\", "/") in catalog_paths
        ]
        for rel in unmapped:
            res.notes.append(
                f"patched SQL file `{rel}` could not be mapped to any catalog consumer — "
                f"its effect on impact was NOT recomputed, so the recomputed blast radius "
                f"does not cover the whole diff"
            )
        after_impact = compute_impact(patched_cat, change, dialect)

        res.after = after_impact.counts()
        res.coverage_after = after_impact.coverage()
        res.transitions = _transitions(before_impact, after_impact)
        res.manual_work_remaining = _manual_work(after_impact, patched_cat)
        res.unknown_consumers = sorted(
            (v.asset_name or v.query_id) for v in after_impact.unknown
        )
        res.ambiguous_consumers = sorted(
            (v.asset_name or v.query_id) for v in after_impact.ambiguous
        )
        res.status, res.reasons = _decide(res, before_impact, after_impact)
        return res
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _decide(res: VerificationResult, before: ImpactReport,
            after: ImpactReport) -> tuple[str, list[str]]:
    """THE single place a verdict is computed. PASS / REVIEW_REQUIRED / FAIL, with
    every applicable machine-readable reason code.

    One source of truth, deliberately: `_PASS_GATES` below is the whole PASS
    conjunction, so a new gate is added in exactly one place and cannot be bypassed
    by a caller that forgot about it. Nothing else in the codebase may synthesise a
    verdict — `VerificationResult.auto_applicable` derives from `status`, and
    write-back derives from `auto_applicable`.

    Order: hard failures first (the patch itself is bad), then the PASS conjunction;
    anything that is neither is REVIEW_REQUIRED. Reasons ACCUMULATE, so the caller
    sees every finding rather than only the one that decided the verdict.

    GOVERNING RULE: a migration may PASS only when every known consumer is
    confidently assessed and no unresolved impact remains. Absence of evidence
    (unreadable SQL, unattributable reference, un-recomputed patched file) is never
    proof of safety.
    """
    reasons: list[str] = []
    b, a = res.before, res.after

    breaks_b, breaks_a = int(b.get("breaks", 0)), int(a.get("breaks", 0))
    degrades_a = int(a.get("degrades", 0))
    unknown_a = int(a.get("unknown", 0))
    ambiguous_a = int(a.get("ambiguous", 0))
    unassessed_a = int(res.coverage_after.get("unassessed", 0))
    regressions = res.regressions()
    new_degrades = [t for t in res.transitions if t.after == Verdict.DEGRADES.value
                    and t.before not in (Verdict.DEGRADES.value, Verdict.BREAKS.value)]

    # --- observations (collected regardless of verdict) ---
    # B18.1 / B19.1 — first, because they qualify everything after them: if the change
    # never resolved, the counts describe an empty evidence set; if the schema is
    # unknown, they describe references only, not the column's existence.
    if res._target_reason:
        reasons.append(res._target_reason)
    if not res.parse_ok:
        reasons.append(R_UNPARSEABLE)
    if not res.scope_ok:
        reasons.append(R_SCOPE)
    if regressions:
        reasons.append(R_SAFE_REGRESSED if any(t.before == "SAFE" for t in regressions)
                       else R_BREAKS_INCREASED)
    if breaks_a > breaks_b:
        if R_BREAKS_INCREASED not in reasons:
            reasons.append(R_BREAKS_INCREASED)
    elif breaks_a == breaks_b and breaks_b > 0:
        reasons.append(R_BREAKS_NOT_REDUCED)
    if new_degrades:
        reasons.append(R_NEW_DEGRADES)
    if breaks_a == 0:
        reasons.append(R_BREAKS_ELIMINATED)
    else:
        reasons.append(R_BREAKS_REMAINING)
    # B17.2 — a degradation the patch did not introduce is still unresolved impact:
    # the consumer keeps executing, but its output schema changed underneath a
    # downstream contract. Reported separately from R_NEW_DEGRADES because the two
    # carry different verdicts (review vs fail).
    if degrades_a and not new_degrades:
        reasons.append(R_DEGRADES_REMAINING)
    if unknown_a:
        reasons.append(R_UNKNOWN_PRESENT)
    # B17.1 — parsed, the column was found, but it cannot be attributed to a source
    # table. Distinct from UNKNOWN, and never counted as safe.
    if ambiguous_a:
        reasons.append(R_AMBIGUOUS_PRESENT)
    if unassessed_a:
        reasons.append(R_COVERAGE_INCOMPLETE)
    # B17.3 — part of the diff was excluded from the recomputation.
    if res.unmapped_files:
        reasons.append(R_PATCHED_FILE_UNMAPPED)
    # B18.2 — the diff removed or moved a definition instead of editing it. A consumer
    # whose SQL file is gone is unresolved impact, not a consumer that became safe.
    if res.deleted_files:
        reasons.append(R_FILE_DELETED)
    if res.unresolved_renames:
        reasons.append(R_FILE_RENAMED)
    if res.manual_work_remaining:
        reasons.append(R_MANUAL_WORK)
    if res.residual_references:
        reasons.append(R_FIX_INCOMPLETE)

    # --- FAIL: the change did not resolve, or the patch is broken / regressive ---
    hard_fail = (
        # B18.1 — an unresolved change was never assessed; that is not a migration
        # that "improved but is incomplete", it is a request we could not act on.
        not res.target_resolved
        or not res.parse_ok
        or not res.scope_ok
        or bool(regressions)
        or bool(new_degrades)
        or breaks_a > breaks_b
        or (breaks_a == breaks_b and breaks_b > 0)
    )
    if hard_fail:
        return FAIL, _dedupe(reasons)

    # --- PASS: the strict conjunction, in one place. Every clause must hold. ---
    _PASS_GATES = (
        # the change itself resolved against the catalog (B18.1)
        ("change_target_resolved", res.target_resolved),
        ("patch_applied", res.patch_applied),
        ("patched_sql_parses", res.parse_ok),
        ("diff_in_scope", res.scope_ok),
        # the target's columns were actually visible (B19.1)
        ("target_schema_known", res.schema_known),
        # every patched .sql file was actually re-analysed (B17.3)
        ("diff_fully_recomputed", not res.unmapped_files),
        # no consumer's definition was deleted or moved out from under the catalog (B18.2)
        ("no_consumer_sql_deleted", not res.deleted_files),
        ("renames_recomputed", not res.unresolved_renames),
        ("no_breaks_after", breaks_a == 0),
        # no residual degradation, new or pre-existing (B17.2)
        ("no_degrades_after", degrades_a == 0),
        ("no_unknown_after", unknown_a == 0),
        # no unattributable reference left (B17.1)
        ("no_ambiguous_after", ambiguous_a == 0),
        ("coverage_complete", unassessed_a == 0),
        ("nothing_regressed", not regressions),
        ("no_manual_work_remaining", not res.manual_work_remaining),
        ("no_residual_references", not res.residual_references),
    )
    if all(ok for _name, ok in _PASS_GATES):
        return PASS, _dedupe(reasons)

    return REVIEW_REQUIRED, _dedupe(reasons)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


# --- rendering ------------------------------------------------------------------

_BADGE = {PASS: "✅ PASS", REVIEW_REQUIRED: "⚠️ REVIEW REQUIRED", FAIL: "❌ FAIL"}

_REASON_TEXT = {
    R_NO_PATCH: "no patch was supplied",
    R_APPLY_FAILED: "the patch did not apply cleanly",
    R_UNPARSEABLE: "patched SQL no longer parses",
    R_SCOPE: "the diff touched files outside the fix's scope",
    R_BREAKS_ELIMINATED: "no breaking consumers remain among those analysed",
    R_BREAKS_REMAINING: "breaking consumers still remain",
    R_BREAKS_NOT_REDUCED: "the break count did not go down",
    R_BREAKS_INCREASED: "the patch increased the break count",
    R_NEW_DEGRADES: "the patch introduced new DEGRADES consumers",
    R_DEGRADES_REMAINING: "one or more consumers still execute with changed output or behaviour",
    R_UNKNOWN_PRESENT: "at least one consumer could not be assessed (UNKNOWN)",
    R_AMBIGUOUS_PRESENT: "at least one column reference could not be confidently attributed "
                         "to a source table",
    R_PATCHED_FILE_UNMAPPED: "at least one patched SQL file could not be connected to a "
                             "catalog consumer, so its impact was not recomputed",
    R_COVERAGE_INCOMPLETE: "coverage is incomplete — some consumers were never analysed",
    R_SAFE_REGRESSED: "a previously-SAFE consumer regressed",
    R_MANUAL_WORK: "consumers remain that no mechanical fix can reach",
    R_FIX_INCOMPLETE: "a patched file still references the dropped column — the fix is incomplete",
    R_TARGET_NOT_FOUND: "the target dataset was not found in the catalog, so nothing was assessed",
    R_SCHEMA_UNKNOWN: "the catalog records no columns for the target dataset, so the change "
                      "could not be checked against a schema",
    R_COLUMN_NOT_FOUND: "the target column is not in the resolved dataset's schema",
    R_FILE_DELETED: "the diff DELETES a consumer's defining SQL file — a vanished consumer "
                    "is not an unaffected one",
    R_FILE_RENAMED: "the diff MOVES a consumer's defining SQL file to a path that could not "
                    "be re-analysed",
}


def render_verification_md(res: VerificationResult) -> str:
    """The VERIFICATION.md artifact. Derived facts only."""
    d = res.deltas()
    L: list[str] = []
    L.append(f"# Migration Verification — {_BADGE.get(res.status, res.status)}")
    L.append("")
    L.append(f"**Change.** `{res.change}`")
    L.append("")
    # ONE badge: `summary_line()` already starts with the status, so print only its
    # detail half here rather than repeating the verdict ("REVIEW REQUIRED —
    # REVIEW_REQUIRED — ..." was the markdown twin of the HTML card's "PASS PASS").
    L.append(f"**Verdict.** {_BADGE.get(res.status, res.status)} — "
             f"{res.summary_line().split('—', 1)[-1].strip()}")
    L.append("")
    L.append("> Static evidence only. No queries were executed.")
    L.append("")
    if not res.target_resolved:
        L.append(f"> ❌ **The change did not resolve.** {res.target_problem}")
        L.append("")
    elif not res.schema_known:
        L.append(f"> ⚠️ **The target's schema is unknown.** {res.target_problem}")
        L.append("")
    L.append("## Why")
    L.append("")
    for r in res.reasons:
        L.append(f"- `{r}` — {_REASON_TEXT.get(r, r)}")
    L.append("")
    L.append("## Before → after")
    L.append("")
    L.append("| Metric | Before | After | Δ |")
    L.append("|---|---:|---:|---:|")
    for key, label in [("breaks", "🔴 Breaks"), ("degrades", "🟡 Degrades"),
                       ("safe", "🟢 Safe"), ("unknown", "⚪ Unassessed"),
                       ("ambiguous", "◐ Ambiguous")]:
        L.append(f"| {label} | {res.before.get(key, 0)} | {res.after.get(key, 0)} | "
                 f"{d.get(key, 0):+d} |")
    L.append(f"| Coverage | {res.coverage_before.get('line', 'n/a')} | "
             f"{res.coverage_after.get('line', 'n/a')} | — |")
    L.append("")
    if res.transitions:
        L.append("## Consumer transitions")
        L.append("")
        for t in res.transitions:
            L.append(f"- {t.describe()}")
        L.append("")
    if res.parse_errors:
        L.append("## Parse errors in patched SQL")
        L.append("")
        for e in res.parse_errors:
            L.append(f"- `{e}`")
        L.append("")
    if res.scope_violations:
        L.append("## Scope violations")
        L.append("")
        for v in res.scope_violations:
            L.append(f"- {v}")
        L.append("")
    if res.residual_references:
        L.append("## Fix incomplete — column still referenced after patching")
        L.append("")
        for r in res.residual_references:
            L.append(f"- `{r}`")
        L.append("")
    if res.unknown_consumers:
        L.append("## Unassessed consumers (not safe — manual review)")
        L.append("")
        for u in res.unknown_consumers:
            L.append(f"- {u}")
        L.append("")
    if res.ambiguous_consumers:
        L.append("## Ambiguous references (parsed, but not attributable — manual review)")
        L.append("")
        L.append("_The SQL parsed and the column was found, but it could not be confidently "
                 "attributed to a source table (an unqualified column that more than one "
                 "joined table provides). Not safe, and not a proven break._")
        L.append("")
        for x in res.ambiguous_consumers:
            L.append(f"- {x}")
        L.append("")
    if res.unmapped_files:
        L.append("## Patched files whose impact could not be recomputed")
        L.append("")
        L.append("_These patched SQL files **could not be mapped** to any catalog consumer "
                 "(`Asset.dbt_path` → `defining_query_id` → `Query`), so their effect on the "
                 "blast radius was NOT recomputed. The recomputed numbers below do not cover "
                 "the whole diff._")
        L.append("")
        for u in res.unmapped_files:
            L.append(f"- `{u}`")
        L.append("")
    if res.deleted_files:
        L.append("## SQL files DELETED by the diff")
        L.append("")
        L.append("_A consumer whose defining SQL was removed is **not** a consumer that "
                 "became safe — its impact simply can no longer be recomputed._")
        L.append("")
        for rel in res.deleted_files:
            L.append(f"- `{rel}`")
        L.append("")
    if res.renamed_files:
        L.append("## SQL files MOVED by the diff")
        L.append("")
        for old, new in res.renamed_files:
            tag = ("recomputed at the new path" if (old, new) not in res.unresolved_renames
                   else "**not re-analysable at the new path**")
            L.append(f"- `{old}` → `{new}` — {tag}")
        L.append("")
    if res.file_query_map:
        L.append("## Patched files that WERE recomputed")
        L.append("")
        for rel, qid in sorted(res.file_query_map.items()):
            L.append(f"- `{rel}` → consumer query `{qid}`")
        L.append("")
    if res.manual_work_remaining:
        L.append("## Still needs manual work (no mechanical fix possible)")
        L.append("")
        for m in res.manual_work_remaining:
            L.append(f"- {m}")
        L.append("")
    L.append("## Files patched (in isolation)")
    L.append("")
    for f in res.files_patched or ["—"]:
        L.append(f"- `{f}`")
    L.append("")
    L.append("## Scope of this verification")
    L.append("")
    L.append(f"> {_STATIC_NOTE}")
    L.append("")
    L.append(f"_Verified at {res.verified_at} · method: {res.method}._")
    return "\n".join(L)


def verification_json(res: VerificationResult) -> dict:
    return {
        "status": res.status,
        "reasons": res.reasons,
        "change": res.change,
        "method": res.method,
        "verified_at": res.verified_at,
        "patch_applied": res.patch_applied,
        "parse_ok": res.parse_ok,
        "parse_errors": res.parse_errors,
        "scope_ok": res.scope_ok,
        "scope_violations": res.scope_violations,
        "residual_references": res.residual_references,
        "files_patched": res.files_patched,
        # B17.3 + B18.2 — coverage of the diff, explicit in the machine-readable
        # artifact. Every accounted .sql path is in exactly one of these four.
        "file_query_map": res.file_query_map,
        "unmapped_files": res.unmapped_files,
        "deleted_files": res.deleted_files,
        "renamed_files": [[old, new] for old, new in res.renamed_files],
        "unresolved_renames": [[old, new] for old, new in res.unresolved_renames],
        "diff_sql_paths": res.diff_sql_paths,
        # B18.1 / B19.1 — did the change resolve at all, and could we see the schema?
        "target_resolved": res.target_resolved,
        "schema_known": res.schema_known,
        "target_problem": res.target_problem,
        "before": res.before,
        "after": res.after,
        "deltas": res.deltas(),
        "coverage_before": res.coverage_before,
        "coverage_after": res.coverage_after,
        "transitions": [
            {"consumer": t.consumer, "query_id": t.query_id, "before": t.before,
             "after": t.after, "regressed": t.regressed, "improved": t.improved,
             "asset_type": t.asset_type}
            for t in res.transitions
        ],
        "unknown_consumers": res.unknown_consumers,
        "ambiguous_consumers": res.ambiguous_consumers,
        "manual_work_remaining": res.manual_work_remaining,
        "auto_applicable": res.auto_applicable,
        "notes": res.notes,
    }
