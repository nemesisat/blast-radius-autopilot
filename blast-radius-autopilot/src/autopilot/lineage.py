"""Column-usage engine — the novel, agent-derived core.

Given one SQL query and a target `Dataset.column`, decide *how* the query uses
that column:

    "select"      — the column is projected or derived into the query's output
                    (this is the column-level lineage DataHub's `parse_sql_lineage()`
                    surfaces; sqlglot — the same engine — computes it here so results
                    match online and offline).
    "filter"      — the column appears ONLY in WHERE / JOIN / GROUP BY / HAVING /
                    ORDER BY / QUALIFY. DataHub's parser explicitly *excludes* these
                    (documented gap); this raw column-reference scan closes it, which
                    makes the impact view MORE thorough than the native one.
    "star"        — no explicit reference, but a `SELECT *` / `t.*` projection carries
                    the column into the output. The query survives a drop; its result
                    shape changes silently.
    "none"        — the query parsed and provably does not reference the column.
    "parse_error" — the SQL could not be parsed, so NOTHING is known about it. This is
                    deliberately distinct from "none": one is evidence of safety, the
                    other is absence of evidence. Conflating them produced a verified
                    false negative (see PROGRESS.md 2026-07-29).

Attribution is schema-aware: an unqualified `customer_zip` is attributed to the
target table only when the schema says the target provides it. When more than one
joined table provides the column, the reference is marked low-confidence (gated
out of the definite counts and surfaced separately) — mirroring DESIGN's
`confidence_score` gate.

Pure and deterministic → unit-testable without a live catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from .schema import Catalog, Dataset

# Clauses that count as "filter" usage (the parser gap the raw scan closes).
_FILTER_CLAUSES = {"where", "join", "group", "having", "order", "qualify"}


@dataclass
class ColumnUsage:
    usage: str = "none"                    # select | filter | star | none | parse_error
    clauses: list[str] = field(default_factory=list)
    confidence: str = "high"               # high | medium | low
    note: str = ""

    @property
    def references(self) -> bool:
        """The query provably touches the column. False for `parse_error` — we do
        not know either way there, and this must not read as "no reference"."""
        return self.usage in {"select", "filter", "star"}

    @property
    def assessable(self) -> bool:
        """Whether the query could be analysed at all."""
        return self.usage != "parse_error"


@dataclass
class _Source:
    keys: set[str]                         # alias + name forms this source answers to
    dataset: Dataset | None
    provided: set[str]                     # lowercased columns it provides (empty if schema unknown)
    is_target: bool


def _sources(expr: exp.Expression, catalog: Catalog, target: Dataset) -> list[_Source]:
    """Resolve every FROM/JOIN table to a catalog dataset + the columns it provides."""
    out: list[_Source] = []
    for t in expr.find_all(exp.Table):
        name, db, cat = t.name, t.db, t.catalog
        candidates = [name]
        if db:
            candidates.insert(0, f"{db}.{name}")
        if cat and db:
            candidates.insert(0, f"{cat}.{db}.{name}")
        ds = None
        for cand in candidates:
            ds = catalog.dataset_by_sql_name(cand)
            if ds:
                break
        keys = {name.lower()}
        if t.alias:
            keys.add(t.alias.lower())
        if db:
            keys.add(f"{db}.{name}".lower())
        out.append(
            _Source(
                keys=keys,
                dataset=ds,
                provided={c.lower() for c in ds.schema} if ds else set(),
                is_target=bool(ds and ds.urn == target.urn),
            )
        )
    return out


def _clause_of(node: exp.Expression) -> str:
    """Nearest governing clause of a node: 'select' (projection) or a filter clause."""
    child = node
    cur = node.parent
    while cur is not None:
        if isinstance(cur, exp.Where):
            return "where"
        if isinstance(cur, exp.Join):
            return "join"
        if isinstance(cur, exp.Group):
            return "group"
        if isinstance(cur, exp.Having):
            return "having"
        if isinstance(cur, exp.Order):
            return "order"
        if isinstance(cur, exp.Qualify):
            return "qualify"
        if isinstance(cur, exp.Select):
            exprs = cur.args.get("expressions") or []
            if any(child is e for e in exprs):
                return "select"
            # column lives elsewhere in this SELECT (already handled above) — keep climbing
        child = cur
        cur = cur.parent
    return "select"  # top-level projection with no wrapping clause


def _resolve_ref(col: exp.Column, column: str, sources: list[_Source]) -> tuple[bool, str]:
    """(is_target_ref, confidence) for one Column node named `column`.

    Qualified refs resolve via the alias map (high confidence). Unqualified refs
    are attributed by schema; ambiguity across joined tables → low confidence.
    """
    tgt = [s for s in sources if s.is_target]
    if not tgt:
        return False, "high"

    qualifier = (col.table or "").lower()
    if qualifier:
        for s in sources:
            if qualifier in s.keys:
                return (s.is_target, "high")
        return False, "high"  # qualifier is a CTE / unknown alias — not our table

    # Unqualified: attribute by which sources provide the column.
    providers = [s for s in sources if column.lower() in s.provided]
    unknown = [s for s in sources if not s.provided and not s.is_target]
    if any(s.is_target for s in providers):
        if len(providers) > 1:
            return True, "low"        # >1 known table provides it — ambiguous
        if unknown:
            return True, "medium"     # some table's schema unknown — can't be certain
        return True, "high"
    if providers:
        return False, "high"          # another table clearly provides it — not ours
    if unknown:
        return True, "medium"         # no schema anywhere; best guess it's the target
    return False, "high"              # target present but schema says it lacks the column


def _star_usage(expr: exp.Expression, column: str, sources: list[_Source]) -> tuple[bool, str]:
    """Detect `SELECT *` / `t.*` projections that carry the target column."""
    tgt = [s for s in sources if s.is_target]
    if not tgt:
        return False, "high"
    target_provides = any(column.lower() in s.provided for s in tgt) or any(not s.provided for s in tgt)
    for sel in expr.find_all(exp.Select):
        for proj in sel.args.get("expressions") or []:
            e = proj.this if isinstance(proj, exp.Alias) else proj
            if isinstance(e, exp.Star):
                if target_provides:
                    return True, "medium"        # bare * over a scope incl. the target
            elif isinstance(e, exp.Column) and isinstance(e.this, exp.Star):
                qualifier = (e.table or "").lower()
                for s in sources:
                    if qualifier in s.keys and s.is_target and target_provides:
                        return True, "high"       # target-alias.*
    return False, "high"


def analyze_query(
    sql: str, target: Dataset, column: str, catalog: Catalog, dialect: str | None = None
) -> ColumnUsage:
    """How does `sql` use `target`.`column`? Returns a ColumnUsage."""
    dialect = dialect or catalog.sql_dialect
    try:
        expr = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:  # noqa: BLE001 — unparseable SQL must not hide impact
        # A distinct state, NOT "none". "none" means we read the query and proved it
        # does not touch the column; this means we could not read it at all. Collapsing
        # the two is what let a Jinja-templated dbt model that references the column
        # 4x be reported SAFE (see PROGRESS.md 2026-07-29).
        return ColumnUsage(usage="parse_error", confidence="low",
                           note=f"parse_error: {type(e).__name__}")

    sources = _sources(expr, catalog, target)
    if not any(s.is_target for s in sources):
        return ColumnUsage(usage="none", confidence="high", note="target table not in query")

    select_conf: list[str] = []
    filter_conf: list[str] = []
    clauses: set[str] = set()

    # Explicit column references.
    for col in expr.find_all(exp.Column):
        if (col.name or "").lower() != column.lower():
            continue
        is_target, conf = _resolve_ref(col, column, sources)
        if not is_target:
            continue
        clause = _clause_of(col)
        clauses.add(clause)
        if clause == "select":
            select_conf.append(conf)
        elif clause in _FILTER_CLAUSES:
            filter_conf.append(conf)

    # Star projections (SELECT * / t.*) that carry the column. Kept OUT of
    # `select_conf`: a star does not name the column, so the query still executes
    # after a drop — its output just silently loses a field. That is DEGRADES, not
    # BREAKS, and only applies when nothing explicit was found.
    star_hit, star_conf = _star_usage(expr, column, sources)
    if star_hit:
        clauses.add("select(*)")

    def best(confs: list[str]) -> str:
        if "high" in confs:
            return "high"
        if "medium" in confs:
            return "medium"
        return "low"

    # Severity order: an explicit projection outranks an explicit filter reference,
    # which outranks a star that merely carries the column.
    if select_conf:
        return ColumnUsage("select", sorted(clauses), best(select_conf))
    if filter_conf:
        return ColumnUsage("filter", sorted(clauses), best(filter_conf))
    if star_hit:
        return ColumnUsage("star", sorted(clauses), star_conf)
    return ColumnUsage("none", confidence="high", note="no target-column reference")


def raw_reference_scan(sql: str, target: Dataset, column: str, catalog: Catalog, dialect: str | None = None) -> set[str]:
    """The raw column-reference scan on its own — every clause `target.column` is
    seen in (SELECT/WHERE/JOIN/GROUP/HAVING/ORDER/QUALIFY). Exposed for tests and
    to demonstrate the parser-gap closure independently of the verdict logic."""
    dialect = dialect or catalog.sql_dialect
    try:
        expr = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        return set()
    sources = _sources(expr, catalog, target)
    if not any(s.is_target for s in sources):
        return set()
    found: set[str] = set()
    for col in expr.find_all(exp.Column):
        if (col.name or "").lower() != column.lower():
            continue
        is_target, _ = _resolve_ref(col, column, sources)
        if is_target:
            found.add(_clause_of(col))
    return found
