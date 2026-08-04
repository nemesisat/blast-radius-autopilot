"""Freshness skew: an upstream feature table that stopped updating means the
model is serving on stale inputs. This is the planted issue in the nyc-taxi
sample dataset — the demo trigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _to_datetime(ts) -> datetime:
    """Accept a datetime, epoch seconds, or epoch milliseconds (DataHub uses ms)."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    ts = float(ts)
    if ts > 1e12:  # milliseconds
        ts /= 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc)


@dataclass
class FreshnessResult:
    last_modified: datetime
    age_hours: float
    max_age_hours: float

    @property
    def is_stale(self) -> bool:
        return self.age_hours > self.max_age_hours

    @property
    def severity(self) -> str:
        if not self.is_stale:
            return "none"
        return "high" if self.age_hours > 2 * self.max_age_hours else "moderate"

    def summary(self) -> str:
        if not self.is_stale:
            return f"Fresh — last updated {self.age_hours:.1f}h ago."
        return (
            f"Stale — last updated {self.age_hours:.1f}h ago "
            f"(SLA {self.max_age_hours:.0f}h)."
        )


def detect_freshness(last_modified, now=None, max_age_hours: float = 24.0) -> FreshnessResult:
    lm = _to_datetime(last_modified)
    now_dt = _to_datetime(now) if now is not None else datetime.now(timezone.utc)
    age_hours = (now_dt - lm).total_seconds() / 3600.0
    return FreshnessResult(last_modified=lm, age_hours=age_hours, max_age_hours=max_age_hours)
