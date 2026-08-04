"""Fix generation — the mechanical, reliable migration edit.

Scope discipline (DESIGN): mechanical only. For a dbt model downstream of the
changed table we regenerate the model's SQL against the *real* schema:

    DROP    → remove the column from the model's SELECT projection.
              If the model also uses the column in WHERE/JOIN/GROUP, that logic is
              flagged for human review — we never silently rewrite filter semantics.
    RENAME  → rename every reference to the column (projection + filter) to the new
              name. This is always safe and mechanical.

Output is a unified git diff that applies on the sample repo, plus the rewritten
SQL (re-parsed to prove it's valid). No arbitrary logic rewrites — everything else
is "what's next," shown not built.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp

from .lineage import _resolve_ref, _sources, raw_reference_scan
from .schema import Asset, Catalog, ChangeSpec, Op


@dataclass
class FixResult:
    asset_urn: str
    asset_name: str
    path: str
    original_sql: str
    new_sql: str
    diff: str
    applicable: bool = True
    needs_review: list[str] = field(default_factory=list)
    note: str = ""
    method: str = "minimal"          # minimal (formatting-preserving) | regenerated (sqlglot)

    @property
    def changed(self) -> bool:
        return self.original_sql.strip() != self.new_sql.strip()


def _norm(s: str) -> str:
    return " ".join(s.strip().rstrip(",").split()).lower()


def _minimal_drop(original: str, proj_texts: list[str], dialect: str) -> str | None:
    """Formatting-preserving drop: remove the projection line(s) that render to one
    of `proj_texts` (one-column-per-line dbt style), fixing any dangling comma.
    Returns None if it can't do it confidently (caller falls back to regen)."""
    wanted = {_norm(t) for t in proj_texts}
    lines = original.split("\n")
    kept, removed = [], 0
    for line in lines:
        if _norm(line) in wanted:
            removed += 1
            continue
        kept.append(line)
    if removed != len(proj_texts):
        return None  # projections weren't on their own lines — let regen handle it

    # Fix a dangling trailing comma on the last projection before FROM.
    for i, line in enumerate(kept):
        nxt = next((kept[j].strip().lower() for j in range(i + 1, len(kept)) if kept[j].strip()), "")
        if line.rstrip().endswith(",") and nxt.startswith("from"):
            kept[i] = line.rstrip()[:-1]
    new_sql = "\n".join(kept)
    try:
        if sqlglot.parse_one(new_sql, read=dialect) is None:
            return None
    except Exception:  # noqa: BLE001
        return None
    return new_sql


def _minimal_rename(original: str, col: str, new_name: str, single_table: bool, dialect: str) -> str | None:
    """Formatting-preserving rename via whole-word substitution — only safe when the
    model references a single table (no same-named column on a joined table)."""
    if not single_table:
        return None
    new_sql = re.sub(rf"\b{re.escape(col)}\b", new_name, original)
    try:
        if sqlglot.parse_one(new_sql, read=dialect) is None:
            return None
    except Exception:  # noqa: BLE001
        return None
    return new_sql


def _rewrite(original: str, change: ChangeSpec, catalog: Catalog, dialect: str) -> tuple[str, bool, list[str], str]:
    target = catalog.dataset_by_name_or_urn(change.dataset)
    expr = sqlglot.parse_one(original, read=dialect)
    sources = _sources(expr, catalog, target)
    col = change.column
    needs_review: list[str] = []
    applicable = True
    trailing = "\n" if original.endswith("\n") else ""

    if change.op is Op.RENAME:
        # Collect target references, then try a formatting-preserving rename first.
        single_table = len([s for s in sources if s.provided]) <= 1 or all(
            col.lower() not in s.provided for s in sources if not s.is_target
        )
        minimal = _minimal_rename(original, col, change.new_name, single_table, dialect)
        if minimal is not None:
            return minimal, applicable, needs_review, "minimal"

        def rename(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Column) and (node.name or "").lower() == col.lower():
                is_t, conf = _resolve_ref(node, col, sources)
                if is_t and conf != "low":
                    node.set("this", exp.to_identifier(change.new_name, quoted=node.this.quoted))
            return node

        new_expr = expr.transform(rename)
    else:  # DROP
        filter_clauses = raw_reference_scan(original, target, col, catalog, dialect) - {"select", "select(*)"}
        if filter_clauses:
            needs_review.append(
                f"`{col}` is used in {', '.join(sorted(filter_clauses))} of this model — "
                "filter/join logic needs manual review (not auto-rewritten)"
            )
        proj_texts: list[str] = []
        for sel in expr.find_all(exp.Select):
            kept = []
            for proj in sel.expressions:
                e = proj.this if isinstance(proj, exp.Alias) else proj
                is_target_proj = (
                    isinstance(e, exp.Column)
                    and (e.name or "").lower() == col.lower()
                    and _resolve_ref(e, col, sources)[0]
                )
                if is_target_proj:
                    proj_texts.append(proj.sql(dialect=dialect))
                    continue
                kept.append(proj)
            if not kept and sel.expressions:
                needs_review.append("dropping the column would empty a SELECT list — needs manual review")
                applicable = False
            elif len(kept) != len(sel.expressions):
                sel.set("expressions", kept)

        # Try a formatting-preserving edit first (clean PR diff); fall back to regen.
        if applicable and proj_texts:
            minimal = _minimal_drop(original, proj_texts, dialect)
            if minimal is not None:
                return minimal, applicable, needs_review, "minimal"
        new_expr = expr

    new_sql = new_expr.sql(dialect=dialect, pretty=True) + trailing
    return new_sql, applicable, needs_review, "regenerated"


def generate_fix(
    catalog: Catalog, change: ChangeSpec, asset: Asset, repo_root: str | Path, dialect: str | None = None
) -> FixResult | None:
    """Generate a migration fix for one dbt-model asset. Returns None if the asset
    has no editable SQL file."""
    if not asset.dbt_path:
        return None
    dialect = dialect or catalog.sql_dialect
    path = Path(repo_root) / asset.dbt_path
    if not path.exists():
        return FixResult(
            asset.urn, asset.name, str(asset.dbt_path), "", "", "",
            applicable=False, note=f"dbt file not found: {path}",
        )

    original = path.read_text()
    new_sql, applicable, needs_review, method = _rewrite(original, change, catalog, dialect)

    # Prove the generated SQL is valid before offering it as a fix.
    try:
        sqlglot.parse_one(new_sql, read=dialect)
    except Exception as e:  # noqa: BLE001
        return FixResult(
            asset.urn, asset.name, str(asset.dbt_path), original, new_sql, "",
            applicable=False, note=f"generated SQL failed to parse: {e}",
        )

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            new_sql.splitlines(keepends=True),
            fromfile=f"a/{asset.dbt_path}",
            tofile=f"b/{asset.dbt_path}",
        )
    )
    return FixResult(
        asset_urn=asset.urn,
        asset_name=asset.name,
        path=str(asset.dbt_path),
        original_sql=original,
        new_sql=new_sql,
        diff=diff,
        applicable=applicable,
        needs_review=needs_review,
        method=method,
    )


def generate_fixes(
    catalog: Catalog, change: ChangeSpec, report, repo_root: str | Path, dialect: str | None = None
) -> list[FixResult]:
    """Generate fixes for every impacted dbt-model asset in the report."""
    impacted_assets = {v.asset_urn for v in report.breaks + report.degrades if v.asset_urn}
    fixes: list[FixResult] = []
    for asset in catalog.assets:
        if asset.urn in impacted_assets and asset.dbt_path:
            fx = generate_fix(catalog, change, asset, repo_root, dialect)
            if fx:
                fixes.append(fx)
    return fixes
