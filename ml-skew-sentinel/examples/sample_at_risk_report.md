# ML Skew Sentinel — sample output

This is a real report produced by `python -m sentinel.run` against a seeded
"NYC Taxi Fare Predictor" whose upstream feature table went stale and drifted.
It's included so judges can see the output quality without running the project.

---

**Verdict:** AT RISK
**Drift score:** 1.917
**Model:** `urn:li:mlModel:(urn:li:dataPlatform:mlflow,nyc_taxi_fare_predictor,PROD)`

## Findings
- **Schema:** Schema drift — removed: `pickup_zone`
- **Freshness:** Stale — last updated 72.0h ago (SLA 24h).
- **Distribution:**
    - `trip_distance`: PSI 1.317 (significant), KS 0.450 ⚠️

## Recommended action
- Investigate the offending upstream before trusting new predictions; consider
  retraining on refreshed data or rolling back to the last good snapshot.

---

## What the Sentinel wrote back to DataHub

| Target | Mutation | Value |
|--------|----------|-------|
| model | `add_tags` | `at-risk`, `skew-detected` |
| model | `add_structured_properties` | `skew_status=at-risk`, `skew_drift_score=1.917`, `skew_offending_upstream=…trips_features#trip_distance`, `skew_checked_at=<ts>` |
| model | `save_document` | this root-cause note, linked to the model |

The next engineer who opens the model in DataHub sees the tag, the drift score,
and the root cause — no tribal knowledge required.
