"""Unit tests for the pure-Python detectors. No DataHub or heavy deps needed:
    PYTHONPATH=src python -m pytest -q
"""

import random

from sentinel.detectors import (
    classify_psi,
    compute_psi,
    detect_freshness,
    detect_schema_drift,
    ks_statistic,
)


def _samples():
    random.seed(0)
    baseline = [random.gauss(0, 1) for _ in range(3000)]
    same = [random.gauss(0, 1) for _ in range(3000)]
    shifted = [random.gauss(1.5, 1) for _ in range(3000)]
    return baseline, same, shifted


# --- schema drift ---------------------------------------------------------- #
def test_schema_drift_detects_all_change_types():
    base = {"trip_distance": "double", "pickup_zone": "string", "passengers": "int"}
    cur = {"trip_distance": "double", "pickup_zone": "int", "surge": "double"}
    r = detect_schema_drift(base, cur)
    assert r.removed == ["passengers"]
    assert r.added == ["surge"]
    assert r.type_changed == [("pickup_zone", "string", "int")]
    assert r.has_drift and r.severity == "high"


def test_schema_no_drift():
    s = {"a": "int", "b": "string"}
    r = detect_schema_drift(s, dict(s))
    assert not r.has_drift and r.severity == "none"


# --- distribution drift ---------------------------------------------------- #
def test_psi_stable_for_same_distribution():
    baseline, same, _ = _samples()
    assert compute_psi(baseline, same) < 0.10
    assert classify_psi(compute_psi(baseline, same)) == "stable"


def test_psi_flags_mean_shift():
    baseline, _, shifted = _samples()
    psi = compute_psi(baseline, shifted)
    assert psi > 0.25
    assert classify_psi(psi) == "significant"


def test_ks_monotonic_and_bounded():
    baseline, same, shifted = _samples()
    ks_same = ks_statistic(baseline, same)
    ks_shift = ks_statistic(baseline, shifted)
    assert 0.0 <= ks_same <= 1.0
    assert ks_shift > ks_same


# --- freshness ------------------------------------------------------------- #
def test_freshness_fresh_vs_stale():
    import time

    now_ms = time.time() * 1000
    fresh = detect_freshness(now_ms, now=now_ms, max_age_hours=24)
    assert not fresh.is_stale

    three_days_ago = now_ms - 3 * 24 * 3600 * 1000
    stale = detect_freshness(three_days_ago, now=now_ms, max_age_hours=24)
    assert stale.is_stale and stale.severity == "high"
