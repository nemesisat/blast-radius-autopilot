"""Drift detectors: schema, distribution (PSI/KS), and freshness.

All detectors are pure functions over plain Python data so they can be unit
tested without a running DataHub. The lineage layer feeds them; the write-back
layer consumes their results.
"""

from .schema_drift import SchemaDriftResult, detect_schema_drift
from .distribution_drift import (
    DistributionDriftResult,
    classify_psi,
    compute_psi,
    ks_statistic,
    detect_distribution_drift,
)
from .freshness import FreshnessResult, detect_freshness

__all__ = [
    "SchemaDriftResult",
    "detect_schema_drift",
    "DistributionDriftResult",
    "classify_psi",
    "compute_psi",
    "ks_statistic",
    "detect_distribution_drift",
    "FreshnessResult",
    "detect_freshness",
]
