"""B21 — Overnight Catalog Sweep: the per-change loop, generalised to a whole catalog.

`--verify` answers "is *this* change safe?". A platform team's actual question is bigger:
*"across everything we own, which columns can we change tomorrow, which need a human, and
which are landmines?"* This module answers that by enumerating every candidate column change
and running the **existing** impact -> fixgen -> verify chain over each one, then filing the
result in a ledger.

FIVE PROPERTIES, each of which is a test in `tests/test_sweep.py`:

READ-ONLY, STRUCTURALLY
    A sweep NEVER writes to DataHub — not automatically, not gated, not queued. This module
    does not import `writeback`, never constructs a DataHub client, and exposes no parameter
    whose name suggests writing; a test asserts all three. An assessment pass that can mutate
    the thing it is assessing is a different and far more dangerous tool, and the way to keep
    those apart is to make the read-only one incapable rather than merely well-behaved.

BORROWED SEMANTICS, NOT NEW ONES
    Every verdict here comes from `verify._decide()` and every count from `compute_impact()`.
    This module classifies what they returned; it never re-decides. PASS is the same
    sixteen-clause PASS. UNKNOWN is never counted as safe. Nothing is inflated into a break.

HONEST "SAFE"
    Two very different things could both be called safe, and conflating them would be the
    project's characteristic error in miniature:

        basis="verified_patch"  a fix was generated, applied in isolation, re-parsed, and the
                                impact re-run came back clean. A patch was checked.
        basis="no_references"   nothing that parses references the column, so no patch was
                                needed and none was checked.

    Both are genuinely safe-to-change. Only the first involved verifying anything, so the
    ledger records which is which and never lets the second borrow the first's credibility.
    And neither is reachable while coverage is incomplete: zero breaks over a corpus with an
    unreadable consumer in it is `unassessed`, never safe.

RESILIENT
    A catalog is big and heterogeneous; one pathological candidate must not cost the other
    N-1. Each candidate is assessed inside a try/except and a failure becomes an `error` row
    carrying the exception text, with **no verdict at all** — an error means we do not know,
    so it may not borrow a verdict from anywhere.

ISOLATED
    Isolation is inherited, not reimplemented: `verify_migration()` copies the repo to a temp
    workspace, applies the patch *there*, and removes it in a `finally`. The sweep adds no new
    filesystem writes except the patch files it saves for the ledger to link, which go to an
    explicit `patch_dir` under `out/`.

ORDERING
    Candidates come from `fragility.fragility_leaderboard()` — reused, not reimplemented — so
    the ledger reads worst-first, which is the order someone triaging it actually wants.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .fixgen import generate_fixes
from .fragility import fragility_leaderboard
from .impact import compute_impact
from .schema import Catalog, ChangeSpec, Op
from .verify import verify_migration

# Where generated patches are saved so the ledger can link to them.
DEFAULT_PATCH_DIR = Path("out") / "sweep_patches"

BUCKETS = ("verified_safe", "needs_review", "landmine", "unassessed", "error")

BUCKET_LABEL = {
    "landmine": "🔴 Landmines",
    "unassessed": "❓ Unassessed",
    "needs_review": "⚠️ Needs review",
    "verified_safe": "✅ Verified safe",
    "error": "⚠️ Errors",
}

# Worst first — a triage list is useless if the reader has to scroll past the good news.
BUCKET_ORDER = ("landmine", "unassessed", "needs_review", "verified_safe", "error")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "candidate"


@dataclass
class SweepEntry:
    """One candidate column change, assessed. Every field is derived from the impact report
    or the verification result — nothing here is estimated."""

    dataset: str
    dataset_urn: str
    column: str
    op: str
    change: str

    # From compute_impact()
    breaks: int = 0
    degrades: int = 0
    safe: int = 0
    unknown: int = 0
    ambiguous: int = 0
    coverage: str = ""
    coverage_complete: bool = False
    risk_level: str = ""
    risk_score: int = 0
    fragility_score: int = 0
    runs_impacted: int = 0
    teams: int = 0

    # From fixgen()
    patch_generated: bool = False
    patch_path: str | None = None
    fix_method: str = ""
    fixable_consumers: list[str] = field(default_factory=list)
    # Consumers that break and that no mechanical fix reaches — what makes a landmine.
    blocking_consumers: list[str] = field(default_factory=list)

    # From verify_migration()
    verdict: str | None = None
    reasons: list[str] = field(default_factory=list)
    breaks_before: int | None = None
    breaks_after: int | None = None

    # This module's own classification
    bucket: str = "error"
    basis: str = ""            # verified_patch | no_references | "" when not safe
    error: str = ""

    @property
    def ref(self) -> str:
        return f"{self.dataset}.{self.column}"


@dataclass
class SweepResult:
    catalog: str
    datasets_scanned: int = 0
    candidates_total: int = 0        # what exists in the catalog
    columns_assessed: int = 0        # what this run actually assessed (differs under `limit`)
    entries: list[SweepEntry] = field(default_factory=list)
    duration_seconds: float = 0.0
    started_at: str = ""
    ops: tuple[str, ...] = ("drop",)
    limit: int | None = None
    order: str = "fragility"

    def by_bucket(self) -> dict[str, list[SweepEntry]]:
        """Entries grouped into the five buckets. Always returns all five keys, so a caller
        can never mistake "no landmines found" for "landmines were not looked for"."""
        out: dict[str, list[SweepEntry]] = {b: [] for b in BUCKETS}
        for e in self.entries:
            out.setdefault(e.bucket, []).append(e)
        return out

    def totals(self) -> dict[str, int]:
        return {b: len(v) for b, v in self.by_bucket().items()}

    @property
    def errors(self) -> int:
        return self.totals()["error"]

    def coverage_line(self) -> str:
        """Aggregate coverage across the sweep, stated as a fraction of candidates whose
        impact analysis was complete — NOT averaged, because averaging a coverage ratio
        across candidates would produce a number that describes nothing."""
        complete = sum(1 for e in self.entries
                       if e.bucket != "error" and e.coverage_complete)
        return f"{complete} of {self.columns_assessed} candidate(s) fully assessed"

    def reconciles(self) -> bool:
        return sum(self.totals().values()) == len(self.entries) == self.columns_assessed

    def header_line(self) -> str:
        t = self.totals()
        return (f"{self.datasets_scanned} dataset(s) · {self.columns_assessed} column(s) "
                f"assessed of {self.candidates_total} · {self.coverage_line()} · "
                f"{t['landmine']} landmine(s) · {t['unassessed']} unassessed · "
                f"{t['needs_review']} need review · {t['verified_safe']} verified safe · "
                f"{t['error']} error(s) · duration {self.duration_seconds:.1f}s")


def _classify(report, verification, patch_generated: bool,
              blocking: list[str]) -> tuple[str, str, list[str]]:
    """Decide the bucket. Returns `(bucket, basis, notes)`.

    PRECEDENCE, and the reasoning for it:

      1. `unassessed` — any UNKNOWN consumer. Checked FIRST, because everything below is a
         statement about a corpus we could read, and if part of it was unreadable then no
         such statement is available. This is the rule that stops a thin slice of a catalog
         from reading as a clean bill of health.
      2. `landmine` — proven breaks (or degrades) that no mechanical fix reaches, or a
         verification that came back FAIL. Known damage, no automatic way out.
      3. `needs_review` — anything the impact report or the verifier says a human must look
         at: REVIEW_REQUIRED, or an ambiguous reference, or remaining manual work.
      4. `verified_safe` — nothing broken, nothing degraded, nothing unknown, nothing
         ambiguous, coverage complete. Split by `basis` into a checked patch versus a column
         nothing referenced.

    Note what is NOT here: this function never inspects SQL, never counts anything itself,
    and never overrides a verdict. It reads what impact and verify already concluded.
    """
    c = report.counts()
    cov = report.coverage()
    notes: list[str] = []
    status = getattr(verification, "status", None)

    if c["unknown"] or cov.get("unassessed"):
        notes.append(f"{c['unknown']} consumer(s) could not be assessed")
        return "unassessed", "", notes

    if status == "FAIL":
        notes.append("static verification returned FAIL")
        return "landmine", "", notes

    if c["breaks"] or c["degrades"]:
        if blocking:
            notes.append(f"{len(blocking)} breaking consumer(s) no mechanical fix reaches")
            return "landmine", "", notes
        if status == "PASS":
            return "verified_safe", "verified_patch", notes
        notes.append(f"verification {status or 'not run'} — a human must confirm")
        return "needs_review", "", notes

    # Nothing broken and nothing unknown. Still route ambiguity to a human (B17.1): the
    # reference is real, only its attribution is open.
    if c["ambiguous"] or report.review_required():
        notes.append("an unattributable column reference remains")
        return "needs_review", "", notes

    if patch_generated and status == "PASS":
        return "verified_safe", "verified_patch", notes
    if patch_generated:
        notes.append(f"a patch was generated but verification returned {status or 'nothing'}")
        return "needs_review", "", notes

    notes.append("no consumer that parses references this column; no patch was needed")
    return "verified_safe", "no_references", notes


def sweep(catalog: Catalog, *, ops: tuple[str, ...] = ("drop",), limit: int | None = None,
          order: str = "fragility", repo_root: Path | str | None = None,
          patch_dir: Path | str | None = None, now: datetime | None = None) -> SweepResult:
    """Assess every candidate column change in `catalog` and return a ranked ledger.

    READ-ONLY. Nothing here reaches DataHub.

    `repo_root` is where the dbt project lives; without it no patch can be generated or
    verified, and every candidate is classified from its impact analysis alone (which still
    distinguishes landmines from unreferenced columns — it just cannot say "verified patch").

    `ops` defaults to `("drop",)`. A rename is assessed as its own candidate when requested;
    the two are not interchangeable, since a rename can be mechanically fixed in places a
    drop cannot.
    """
    started = now or datetime.now(timezone.utc)
    t0 = time.perf_counter()

    # Reused, not reimplemented — this IS the fragility ranking.
    ranking = fragility_leaderboard(catalog)
    candidates: list[tuple] = []
    for row in ranking:
        for op in ops:
            candidates.append((row, op))
    if order != "fragility":
        # Only one order is implemented; say so rather than silently ignoring the argument.
        raise ValueError(f"unsupported order {order!r} (only 'fragility' is implemented)")

    total = len(candidates)
    selected = candidates[:limit] if limit is not None else candidates

    pdir = Path(patch_dir) if patch_dir is not None else DEFAULT_PATCH_DIR
    entries: list[SweepEntry] = []
    for row, op in selected:
        entries.append(_assess_one(catalog, row, op, repo_root, pdir))

    res = SweepResult(
        catalog=catalog.name,
        datasets_scanned=len({r.dataset_urn for r, _ in selected}) if selected else 0,
        candidates_total=total,
        columns_assessed=len(entries),
        entries=entries,
        duration_seconds=time.perf_counter() - t0,
        started_at=started.isoformat(timespec="seconds"),
        ops=tuple(ops),
        limit=limit,
        order=order,
    )
    return res


def _assess_one(catalog: Catalog, row, op: str, repo_root, patch_dir: Path) -> SweepEntry:
    """Assess one candidate. Never raises: a failure becomes an `error` row.

    The broad `except` is deliberate and is the point of the function. A sweep runs unattended
    over a whole catalog, and the alternative to catching everything is losing the entire run
    to one malformed consumer.
    """
    ds = catalog.dataset_by_name_or_urn(row.dataset_urn) or catalog.dataset_by_name_or_urn(row.dataset)
    sql_name = ds.sql_name if ds else row.dataset
    entry = SweepEntry(
        dataset=row.dataset, dataset_urn=row.dataset_urn, column=row.column, op=op,
        change="", fragility_score=row.score,
    )
    try:
        change = (ChangeSpec(dataset=sql_name, column=row.column, op=Op(op),
                             new_name=f"{row.column}_renamed") if op == "rename"
                  else ChangeSpec(dataset=sql_name, column=row.column, op=Op(op)))
        entry.change = change.describe()

        report = compute_impact(catalog, change)
        c, cov, risk = report.counts(), report.coverage(), report.risk()
        entry.breaks, entry.degrades = c["breaks"], c["degrades"]
        entry.safe, entry.unknown = c["safe"], c["unknown"]
        entry.ambiguous = c["ambiguous"]
        entry.coverage = cov["line"]
        entry.coverage_complete = not cov.get("unassessed")
        entry.risk_level, entry.risk_score = str(risk["level"]), int(risk["score"])
        entry.runs_impacted, entry.teams = c["runs_impacted"], c["teams"]

        fixes = generate_fixes(catalog, change, report, repo_root) if repo_root else []
        applicable = [f for f in fixes if f.applicable and f.changed and f.diff]
        entry.fixable_consumers = [f.asset_name for f in applicable]
        entry.fix_method = applicable[0].method if applicable else ""

        # Which breaking consumers no mechanical fix reaches. This is what separates a
        # landmine from a fixable break, and it is computed from the fix list rather than
        # guessed from the asset type.
        fixed_urns = {f.asset_urn for f in applicable}
        entry.blocking_consumers = [
            (v.asset_name or f"query {v.query_id}")
            for v in report.assets_impacted() if v.asset_urn not in fixed_urns
        ] + [
            f"query {v.query_id}" for v in report.breaks if not v.asset_urn
        ]

        patch = "".join(f.diff for f in applicable)
        if patch:
            patch_dir.mkdir(parents=True, exist_ok=True)
            p = patch_dir / f"{_slug(change.describe())}.patch"
            p.write_text(patch)
            entry.patch_generated, entry.patch_path = True, str(p)

        verification = None
        if patch and repo_root:
            verification = verify_migration(
                change, report, patch, repo_root, catalog=catalog,
                expected_files=[f.path for f in applicable if f.path] or None,
            )
            entry.verdict = verification.status
            entry.reasons = list(verification.reasons)
            entry.breaks_before = int(verification.before.get("breaks", 0))
            entry.breaks_after = int(verification.after.get("breaks", 0))

        bucket, basis, notes = _classify(report, verification, entry.patch_generated,
                                         entry.blocking_consumers)
        entry.bucket, entry.basis = bucket, basis
        entry.reasons = entry.reasons + notes
    except Exception as e:  # noqa: BLE001 — see the docstring
        entry.bucket = "error"
        entry.error = f"{type(e).__name__}: {e}"
        # An error means we do not know. It borrows no verdict and no basis.
        entry.verdict = None
        entry.basis = ""
    return entry
