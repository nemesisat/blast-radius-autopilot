"""Schema drift: compare a model's training-time schema against the live
upstream schema. Deterministic and high-signal — the most reliable detector
to demo.

A "schema" here is a mapping of column name -> type string, e.g.
    {"trip_distance": "double", "pickup_zone": "string"}
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SchemaDriftResult:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    type_changed: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.added or self.removed or self.type_changed)

    @property
    def severity(self) -> str:
        # Removed columns or type changes break inference; added columns are softer.
        if self.removed or self.type_changed:
            return "high"
        if self.added:
            return "low"
        return "none"

    def summary(self) -> str:
        if not self.has_drift:
            return "No schema drift."
        parts = []
        if self.removed:
            parts.append(f"removed: {', '.join(self.removed)}")
        if self.type_changed:
            parts.append(
                "type changes: "
                + ", ".join(f"{c} ({a}->{b})" for c, a, b in self.type_changed)
            )
        if self.added:
            parts.append(f"added: {', '.join(self.added)}")
        return "Schema drift — " + "; ".join(parts)


def _normalize(type_str: str) -> str:
    return (type_str or "").strip().lower()


def detect_schema_drift(
    baseline_schema: dict[str, str],
    current_schema: dict[str, str],
) -> SchemaDriftResult:
    """Diff two {column: type} maps. Type comparison is case-insensitive."""
    base_cols = set(baseline_schema)
    cur_cols = set(current_schema)

    added = sorted(cur_cols - base_cols)
    removed = sorted(base_cols - cur_cols)

    type_changed: list[tuple[str, str, str]] = []
    for col in sorted(base_cols & cur_cols):
        b, c = _normalize(baseline_schema[col]), _normalize(current_schema[col])
        if b != c:
            type_changed.append((col, baseline_schema[col], current_schema[col]))

    return SchemaDriftResult(added=added, removed=removed, type_changed=type_changed)
