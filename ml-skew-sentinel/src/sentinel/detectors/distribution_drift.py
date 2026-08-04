"""Distribution drift: compare a feature's live values against the training
baseline. Pure-Python PSI + two-sample KS so it runs with no heavy deps;
swap in numpy/scipy for scale if you like.

PSI (Population Stability Index) rule of thumb:
    < 0.10  stable
    0.10-0.25 moderate shift — worth watching
    > 0.25  significant shift — likely skew
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _quantile_edges(values: list[float], buckets: int) -> list[float]:
    """Bucket edges from baseline quantiles (equal-frequency binning)."""
    xs = sorted(values)
    if not xs:
        raise ValueError("baseline values are empty")
    edges = [xs[0]]
    for i in range(1, buckets):
        pos = i / buckets * (len(xs) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(xs) - 1)
        frac = pos - lo
        edges.append(xs[lo] * (1 - frac) + xs[hi] * frac)
    edges.append(xs[-1])
    # De-duplicate collapsed edges (constant regions) while preserving order.
    dedup = [edges[0]]
    for e in edges[1:]:
        if e > dedup[-1]:
            dedup.append(e)
    if len(dedup) < 2:
        dedup = [xs[0], xs[0] + 1e-9]
    return dedup


def _bucket_proportions(values: list[float], edges: list[float]) -> list[float]:
    counts = [0] * (len(edges) - 1)
    for v in values:
        placed = False
        for i in range(len(edges) - 1):
            # last bucket is inclusive on the right edge
            upper_ok = v <= edges[i + 1] if i == len(edges) - 2 else v < edges[i + 1]
            if edges[i] <= v and upper_ok:
                counts[i] += 1
                placed = True
                break
        if not placed:  # values outside baseline range fall into nearest edge bucket
            counts[0 if v < edges[0] else -1] += 1
    total = sum(counts) or 1
    return [c / total for c in counts]


def compute_psi(baseline: list[float], current: list[float], buckets: int = 10) -> float:
    """Population Stability Index between a baseline and a current sample."""
    edges = _quantile_edges(baseline, buckets)
    exp = _bucket_proportions(baseline, edges)
    act = _bucket_proportions(current, edges)
    eps = 1e-6
    psi = 0.0
    for e, a in zip(exp, act):
        e = max(e, eps)
        a = max(a, eps)
        psi += (a - e) * math.log(a / e)
    return psi


def classify_psi(psi: float) -> str:
    if psi < 0.10:
        return "stable"
    if psi < 0.25:
        return "moderate"
    return "significant"


def ks_statistic(baseline: list[float], current: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov D statistic (max CDF gap). Pure Python."""
    if not baseline or not current:
        raise ValueError("both samples must be non-empty")
    a, b = sorted(baseline), sorted(current)
    all_vals = sorted(set(a) | set(b))
    n_a, n_b = len(a), len(b)

    def cdf(sorted_vals: list[float], n: int, x: float) -> float:
        # fraction of values <= x, via linear scan (fine for demo sizes)
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_vals[mid] <= x:
                lo = mid + 1
            else:
                hi = mid
        return lo / n

    return max(abs(cdf(a, n_a, x) - cdf(b, n_b, x)) for x in all_vals)


@dataclass
class DistributionDriftResult:
    feature: str
    psi: float
    ks: float
    verdict: str  # stable | moderate | significant

    @property
    def has_drift(self) -> bool:
        return self.verdict != "stable"

    def summary(self) -> str:
        return (
            f"{self.feature}: PSI {self.psi:.3f} ({self.verdict}), "
            f"KS {self.ks:.3f}"
        )


def detect_distribution_drift(
    feature: str,
    baseline: list[float],
    current: list[float],
    buckets: int = 10,
) -> DistributionDriftResult:
    psi = compute_psi(baseline, current, buckets=buckets)
    ks = ks_statistic(baseline, current)
    return DistributionDriftResult(feature=feature, psi=psi, ks=ks, verdict=classify_psi(psi))
