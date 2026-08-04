"""Impact core — classify every consumer as BREAKS / DEGRADES / SAFE / UNKNOWN for a
proposed schema change, then roll up the blast radius.

Verdict mapping (dataset-agnostic; depends only on *how* the column is used):

    any op  select      -> BREAKS     a reference resolves to the column
    any op  filter      -> BREAKS     ditto — WHERE/JOIN/GROUP/HAVING/ORDER all error
    any op  star        -> DEGRADES   query runs; output silently changes shape
    any op  none        -> SAFE       parsed, provably no reference
    any op  parse_error -> UNKNOWN    could not be read — no evidence either way
    any op  no_definition -> UNKNOWN  consumer exposes no SQL at all

BREAKS covers filter clauses on a DROP as well as a RENAME: dropping a column that a
WHERE names makes the query *error*, it does not silently drift. DEGRADES is reserved
for the case where the statement still executes and only its output changes — a
`SELECT *` losing a column.

Low-confidence attributions (ambiguous unqualified columns across joined tables) are
gated out of the definite counts and surfaced separately — DESIGN's confidence gate.

UNKNOWN is load-bearing: it never counts as safe, never counts as a break, never moves
the risk score, and forces the whole run to REVIEW_REQUIRED. Missing evidence must
never read as proof of safety.
"""

from __future__ import annotations

from .lineage import analyze_query
from .schema import Catalog, ChangeSpec, ImpactReport, ImpactVerdict, Op, Verdict

# Usage states that mean "we could not assess this consumer".
_UNASSESSABLE = {"parse_error", "no_definition"}


def _verdict_for(op: Op, usage: str) -> Verdict:
    if usage in _UNASSESSABLE:
        return Verdict.UNKNOWN
    if usage == "none":
        return Verdict.SAFE
    if usage == "star":
        # Still executes; the output loses a field (drop) or a field is renamed
        # underneath the consumer (rename). Behaviour changes, nothing errors.
        return Verdict.DEGRADES
    # usage in {"select", "filter"} — a reference resolves to the column, so removing
    # or renaming it breaks the statement regardless of which clause it sits in.
    return Verdict.BREAKS


def _reason(change: ChangeSpec, usage: str, clauses: list[str], note: str = "") -> str:
    col = change.column
    where = ", ".join(clauses) if clauses else "—"
    if usage == "parse_error":
        return (f"SQL could not be parsed ({note or 'parse_error'}) — impact on `{col}` "
                f"is UNKNOWN, not safe; needs manual review")
    if usage == "no_definition":
        return (f"consumer exposes no SQL definition — impact on `{col}` is UNKNOWN, "
                f"not safe; needs manual review")
    if usage == "select":
        base = f"projects/derives `{col}` (in {where})"
    elif usage == "filter":
        base = f"references `{col}` in {where}"
    elif usage == "star":
        base = f"selects `*` over a scope that provides `{col}` (in {where})"
        return (f"{base} → still runs, output silently loses `{col}`"
                if change.op is Op.DROP
                else f"{base} → still runs, output field becomes `{change.new_name}`")
    else:
        return f"does not reference `{col}`"
    if change.op is Op.RENAME:
        return f"{base} → must be rewritten to `{change.new_name}`"
    return f"{base} → column removed"


def compute_impact(catalog: Catalog, change: ChangeSpec, dialect: str | None = None) -> ImpactReport:
    """Assess `change` across all of the catalog's real query history."""
    target = catalog.dataset_by_name_or_urn(change.dataset)
    notes: list[str] = []
    if target is None:
        return ImpactReport(
            change=change,
            catalog=catalog.name,
            target_urn=None,
            verdicts=[],
            notes=[f"target dataset '{change.dataset}' not found in catalog"],
        )
    if not target.has_column(change.column):
        notes.append(
            f"column '{change.column}' is not in {target.name}'s current schema "
            f"({', '.join(target.schema) or 'schema unknown'}) — assessing references anyway"
        )

    verdicts: list[ImpactVerdict] = []
    for q in catalog.queries:
        usage = analyze_query(q.sql, target, change.column, catalog, dialect)
        if usage.usage == "parse_error":
            notes.append(
                f"could not parse query {q.query_id} ({usage.note}) — reported UNKNOWN "
                f"(not safe) and routed to manual review"
            )
        verdict = _verdict_for(change.op, usage.usage)
        asset = catalog.asset_for_query(q.query_id)
        verdicts.append(
            ImpactVerdict(
                query_id=q.query_id,
                verdict=verdict,
                usage=usage.usage,
                clauses=usage.clauses,
                # Only a *parsed, proven* non-reference is promoted to high confidence.
                # A parse failure keeps its low confidence — promoting it was the second
                # half of the false-negative defect (see PROGRESS.md 2026-07-29).
                confidence="high" if usage.usage == "none" else usage.confidence,
                team=q.team,
                runs=q.runs,
                asset_urn=asset.urn if asset else None,
                asset_name=asset.name if asset else None,
                asset_type=asset.type if asset else None,
                reason=_reason(change, usage.usage, usage.clauses, usage.note),
            )
        )

    # Consumers discovered in lineage that carry NO SQL definition (PowerBI measures,
    # Looker views, dashboards). The parser can say nothing about them, so they are
    # UNKNOWN — counting them safe would be the same false-negative in a new place.
    assessed_query_ids = {q.query_id for q in catalog.queries}
    for a in catalog.assets:
        if a.defining_query_id and a.defining_query_id in assessed_query_ids:
            continue
        notes.append(
            f"consumer '{a.name}' ({a.type}) exposes no SQL definition — reported "
            f"UNKNOWN (not safe) and routed to manual review"
        )
        verdicts.append(
            ImpactVerdict(
                query_id=a.defining_query_id or f"no_definition:{a.urn}",
                verdict=Verdict.UNKNOWN,
                usage="no_definition",
                clauses=[],
                confidence="low",
                team=None,
                runs=0,
                asset_urn=a.urn,
                asset_name=a.name,
                asset_type=a.type,
                reason=_reason(change, "no_definition", []),
            )
        )

    report = ImpactReport(
        change=change,
        catalog=catalog.name,
        target_urn=target.urn,
        verdicts=verdicts,
        notes=notes,
    )
    cov = report.coverage()
    if report.review_required():
        # Name the actual gap. Unassessed and ambiguous are different failures of
        # knowledge and must not be reported as each other.
        gaps: list[str] = []
        if cov["unassessed"]:
            gaps.append(f"{cov['unassessed']} consumer(s) could not be assessed")
        if report.ambiguous:
            gaps.append(f"{len(report.ambiguous)} column reference(s) could not be confidently "
                        f"attributed to a source table")
        notes.append(
            f"COVERAGE {cov['line']} — " + "; ".join(gaps) + f"; verdict is "
            f"'{report.risk()['level_qualifier']}' and the change REQUIRES REVIEW before "
            f"any write-back."
        )
    return report
