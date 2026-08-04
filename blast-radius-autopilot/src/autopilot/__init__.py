"""Blast Radius Autopilot.

DataHub's Impact Analysis shows you the blast radius of a schema change.
Blast Radius Autopilot *defuses* it: it computes evidence-backed column-level
impact from available query history and downstream SQL definitions — reporting
unparseable, ambiguous, and non-SQL consumers explicitly rather than assuming
they are unaffected — generates the migration fix, STATICALLY VERIFIES that fix
against the recomputed blast radius, produces an applicable patch plus a CI-ready
PR comment, and contributes the impact assessment back to the catalog.

Two honesty constraints hold throughout, and the tests enforce them:

  * Verification is STATIC. No query is executed, no warehouse is contacted, no
    data is read. A PASS means the analyzer can no longer find unresolved impact,
    never that anything ran.
  * What lands in DataHub is stated exactly. Structured properties, tags, a
    one-line description footer, and an institutional-memory LINK to the Impact
    Assessment. The assessment BODY is a file on disk that the link points at —
    the OSS `institutionalMemory` aspect stores a URL and a title, not a document.

The package is dataset-agnostic: every capability runs off universal metadata
primitives (schema, lineage, queries, ownership) — never dataset-specific
columns. Point it at any catalog and it works.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .schema import (
    Asset,
    Catalog,
    ChangeSpec,
    Dataset,
    ImpactReport,
    ImpactVerdict,
    Query,
    Verdict,
)

__all__ = [
    "Asset",
    "Catalog",
    "ChangeSpec",
    "Dataset",
    "ImpactReport",
    "ImpactVerdict",
    "Query",
    "Verdict",
]
