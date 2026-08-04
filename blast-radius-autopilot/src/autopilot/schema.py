"""The data model — pure dataclasses so the impact core stays testable without a
live catalog.

Everything downstream (impact, fix generation, write-back, reports) is expressed
in terms of these universal primitives, never dataset-specific fields:

    Dataset  — a table/view: schema (columns+types), owners, platform, sql_name
    Query    — a real SQL statement from query history + who/when/how-often
    Asset    — a downstream consumer (dbt model, Looker/PowerBI/Tableau) whose
               behaviour is *defined* by one query
    ChangeSpec — the proposed schema change: drop/rename a column on a dataset

This is what makes "works on any dataset" true rather than aspirational — adding
a dataset is data, not code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Op(str, Enum):
    """The kind of schema change proposed."""

    DROP = "drop"
    RENAME = "rename"


class Verdict(str, Enum):
    """Per-consumer impact classification (DataHub's own colour language).

    UNKNOWN is deliberately its own state rather than a lean toward either side:
    missing evidence must never read as proof of safety, but it is not evidence of
    harm either. UNKNOWN never counts as safe, never counts as a break, and never
    moves the numeric risk score — it is reported as a coverage dimension and it
    forces the run to REVIEW_REQUIRED.
    """

    BREAKS = "BREAKS"      # red   — a reference resolves to the column; consumer errors / loses data
    DEGRADES = "DEGRADES"  # amber — still executes, but output/behaviour changes (SELECT * loses a column)
    SAFE = "SAFE"          # green — parsed cleanly and provably does not reference the column
    UNKNOWN = "UNKNOWN"    # grey  — could NOT be assessed (unparseable SQL, or no SQL definition at all)

    @property
    def color(self) -> str:
        return {"BREAKS": "red", "DEGRADES": "amber", "SAFE": "green", "UNKNOWN": "grey"}[self.value]


# Worst first — the ranking order for reports/leaderboards. UNKNOWN sorts above
# SAFE: an unassessed consumer deserves attention before a proven-safe one.
_SEVERITY = {Verdict.BREAKS: 0, Verdict.DEGRADES: 1, Verdict.UNKNOWN: 2, Verdict.SAFE: 3}


def severity_rank(v: Verdict) -> int:
    return _SEVERITY[v]


@dataclass
class Dataset:
    urn: str
    name: str
    sql_name: str                       # how the table is referenced in SQL (e.g. analytics.fct_orders)
    platform: str = "unknown"
    schema: dict[str, str] = field(default_factory=dict)   # {column: native_type}
    owners: list[str] = field(default_factory=list)

    def has_column(self, col: str) -> bool:
        return col.lower() in {c.lower() for c in self.schema}


@dataclass
class Query:
    query_id: str
    sql: str
    platform: str = "unknown"
    team: str | None = None
    actor: str | None = None
    runs: int = 1                        # execution count from history (weights the fan-out)
    last_run: str | None = None


@dataclass
class Asset:
    """A downstream consumer defined by a query (dbt model / dashboard / report)."""

    urn: str
    name: str
    type: str                            # dbt_model | looker_dashboard | powerbi_report | tableau_workbook | ...
    platform: str = "unknown"
    owners: list[str] = field(default_factory=list)
    defining_query_id: str | None = None
    dbt_path: str | None = None          # relative path to the SQL file, if a dbt model


@dataclass
class Catalog:
    name: str
    datasets: list[Dataset] = field(default_factory=list)
    queries: list[Query] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    sql_dialect: str = "snowflake"
    require_review: bool = False          # regulated catalog: queue all writes for a human
    compliance_note: str = ""

    def dataset_by_sql_name(self, sql_name: str) -> Dataset | None:
        target = sql_name.lower()
        bare = target.split(".")[-1]
        for d in self.datasets:
            if d.sql_name.lower() == target or d.sql_name.lower().split(".")[-1] == bare:
                return d
        return None

    def dataset_by_name_or_urn(self, key: str) -> Dataset | None:
        for d in self.datasets:
            if key in (d.urn, d.name, d.sql_name):
                return d
        return self.dataset_by_sql_name(key)

    def asset_for_query(self, query_id: str) -> Asset | None:
        for a in self.assets:
            if a.defining_query_id == query_id:
                return a
        return None


@dataclass
class ChangeSpec:
    """The proposed schema change to assess."""

    dataset: str                         # sql_name / name / urn of the target table
    column: str                          # target column
    op: Op = Op.DROP
    new_name: str | None = None          # required when op == RENAME

    @classmethod
    def parse(cls, dataset: str, column: str, op: str, new_name: str | None = None) -> "ChangeSpec":
        o = Op(op.lower())
        if o is Op.RENAME and not new_name:
            raise ValueError("rename requires --new-name")
        return cls(dataset=dataset, column=column, op=o, new_name=new_name)

    def describe(self) -> str:
        if self.op is Op.RENAME:
            return f"rename {self.dataset}.{self.column} -> {self.new_name}"
        return f"drop {self.dataset}.{self.column}"


@dataclass
class ImpactVerdict:
    """The assessed impact of the change on one query/consumer."""

    query_id: str
    verdict: Verdict
    usage: str                           # select | filter | star | none | parse_error | no_definition
    clauses: list[str] = field(default_factory=list)   # where the column was seen
    confidence: str = "high"             # high | medium | low
    team: str | None = None
    runs: int = 1
    asset_urn: str | None = None
    asset_name: str | None = None
    asset_type: str | None = None
    reason: str = ""

    @property
    def is_unknown(self) -> bool:
        """Could not be assessed — no evidence either way."""
        return self.verdict is Verdict.UNKNOWN

    @property
    def is_ambiguous(self) -> bool:
        """A *resolved* reference we could not attribute confidently.

        Distinct from `is_unknown`: here the SQL parsed and the column was found,
        we just cannot prove which table it belongs to. An unassessable consumer is
        not "ambiguous" — it is unassessed, and must not be double-counted as both.
        """
        return self.confidence == "low" and not self.is_unknown


@dataclass
class ImpactReport:
    change: ChangeSpec
    catalog: str
    target_urn: str | None
    verdicts: list[ImpactVerdict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # --- rollups -----------------------------------------------------------
    def _by(self, v: Verdict) -> list[ImpactVerdict]:
        return [x for x in self.verdicts if x.verdict is v and not x.is_ambiguous]

    @property
    def breaks(self) -> list[ImpactVerdict]:
        return self._by(Verdict.BREAKS)

    @property
    def degrades(self) -> list[ImpactVerdict]:
        return self._by(Verdict.DEGRADES)

    @property
    def safe(self) -> list[ImpactVerdict]:
        return self._by(Verdict.SAFE)

    @property
    def unknown(self) -> list[ImpactVerdict]:
        """Consumers we could NOT assess. Never safe, never a break."""
        return [x for x in self.verdicts if x.is_unknown]

    @property
    def ambiguous(self) -> list[ImpactVerdict]:
        return [x for x in self.verdicts if x.is_ambiguous]

    # --- coverage: a dimension of its own, never folded into the score ------
    def coverage(self) -> dict[str, object]:
        """How much of the fan-out we could actually analyse.

        Reported separately from severity so a confident verdict over a thin slice
        of consumers can never masquerade as a confident verdict over all of them.
        """
        total = len(self.verdicts)
        unassessed = len(self.unknown)
        analysed = total - unassessed
        return {
            "analysed": analysed,
            "total": total,
            "unassessed": unassessed,
            "line": f"{analysed} of {total} analysed",
        }

    def review_required(self) -> bool:
        """Fail closed: any UNRESOLVED consumer forces human review.

        Two distinct kinds of unresolved, both blocking (B15 + B17.1):
          - `unknown`   — we could not read the consumer at all.
          - `ambiguous` — we read it, found the column, but cannot prove which table
            it came from. The reference is real; only its attribution is open.

        Ambiguity is uncertainty, not absence of risk. It is deliberately NOT folded
        into `unknown` (the SQL parsed, so coverage is complete) and never inflated
        into a break (we have not proven a reference to *our* column) — but it must
        not be auto-approved either.
        """
        return bool(self.unknown) or bool(self.ambiguous)

    def auto_applicable(self) -> bool:
        """Whether the assessment is complete enough to act on without a human."""
        return not self.review_required()

    def impacted(self) -> list[ImpactVerdict]:
        """Breaks + degrades (confident), worst first, then by run-weight."""
        hit = self.breaks + self.degrades
        return sorted(hit, key=lambda x: (severity_rank(x.verdict), -x.runs))

    def teams_impacted(self) -> list[str]:
        return sorted({x.team for x in self.breaks + self.degrades if x.team})

    def assets_impacted(self) -> list[ImpactVerdict]:
        return [x for x in self.breaks + self.degrades if x.asset_urn]

    def counts(self) -> dict[str, int]:
        cov = self.coverage()
        return {
            "breaks": len(self.breaks),
            "degrades": len(self.degrades),
            "safe": len(self.safe),
            "unknown": len(self.unknown),
            "ambiguous": len(self.ambiguous),
            "queries_total": len(self.verdicts),
            "analysed": int(cov["analysed"]),
            "unassessed": int(cov["unassessed"]),
            "runs_impacted": sum(x.runs for x in self.breaks + self.degrades),
            "teams": len(self.teams_impacted()),
        }

    def risk(self) -> dict[str, object]:
        """A single change-risk scorecard (0-100) from the fan-out and severity.

        The score is computed over CONFIDENTLY ASSESSED consumers only. Unassessed
        and ambiguous consumers do not raise it (that would invent breaks we never
        proved) and do not lower it (that would let missing evidence dilute real
        findings). They surface as `review_required` plus the coverage line and the
        ambiguous count instead.

        `level_qualifier` names the *reason* the number is partial, because the two
        reasons are different: incomplete coverage means some consumers were never
        read, while ambiguity means a reference was read but not attributed.
        """
        c = self.counts()
        # Break weight dominates; degrades add; run-weight and team-spread amplify.
        raw = (
            c["breaks"] * 20
            + c["degrades"] * 8
            + min(c["runs_impacted"], 60) * 0.5
            + c["teams"] * 5
        )
        score = int(min(100, round(raw)))
        level = "CRITICAL" if score >= 60 else "HIGH" if score >= 30 else "MODERATE" if score >= 10 else "LOW"
        cov = self.coverage()
        ambiguous = c["ambiguous"]
        if cov["unassessed"]:
            qualifier = f"{level} among assessed"
        elif ambiguous:
            qualifier = f"{level} with {ambiguous} unresolved reference(s)"
        else:
            qualifier = level
        return {
            "score": score,
            "level": level,
            "review_required": self.review_required(),
            "coverage": cov["line"],
            "unassessed": cov["unassessed"],
            "ambiguous": ambiguous,
            "level_qualifier": qualifier,
        }
