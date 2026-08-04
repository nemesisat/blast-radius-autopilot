# Captured runs (B7 evidence)

Regenerate all of this with:

```bash
autopilot --loop loop.config.yaml --out out/examples          # per-dataset HTML + PR comments
autopilot --catalog examples/showcase-ecommerce/catalog.json --fragility   # leaderboard
```

## Dataset-agnostic loop — the SAME code across 5 very different datasets

```
  BLAST RADIUS AUTOPILOT — LOOP SUMMARY (same loop, many datasets)
==================================================================================
  RUN                       RISK       BREAKS  DEGR  SAFE FIXES  WRITE-BACK
----------------------------------------------------------------------------------
  ecommerce-drop-zip        CRITICAL        4     2     3     1  8 written
  nyc-taxi-drop-distance    CRITICAL        2     1     2     1  7 written
  healthcare-rename-dx      CRITICAL        3     0     1     1  6 queued (review)
  fiction-retail-drop-tier  CRITICAL        2     1     1     1  7 written
  finance-rename-revenue    CRITICAL        3     0     1     1  7 queued (review)
==================================================================================
```

Each row is a different domain (e-commerce, operational time-series, synthetic
healthcare, clean-canvas retail, synthetic finance) and platform mix, run through the
identical loop with only a config entry per dataset. The two **regulated** catalogs
(`healthcare`, `finance`, marked `require_review`) correctly **queue every write for a
human** instead of auto-applying — matching the compliance posture in EXAMPLES.md.

The five worked examples in `EXAMPLES.md` map to these five runs. Per-dataset visual
reports + PR comments are written to `out/examples/<name>.html` and
`out/examples/<name>.PR_COMMENT.md`.

## Catalog Fragility leaderboard (B13) — showcase-ecommerce

```
   #  DATASET.COLUMN                           RISK  BREAKS DEGR  RUNS TEAMS
------------------------------------------------------------------------------
   1  fct_orders.amount                         100       7    0    59     4   CRITICAL
   2  fct_orders.customer_zip                   100       4    2    41     3   CRITICAL
   3  fct_orders.customer_id                     60       2    1    14     1   CRITICAL
   4  fct_orders.order_date                      48       1    1    19     2   HIGH
   5  fct_orders.status                          44       1    1    13     2   HIGH
   6  fct_orders.ship_state                      30       1    0     9     1   HIGH
   7  fct_orders.order_id                        28       1    0     6     1   MODERATE
   8  dim_customer.customer_segment              28       1    0     5     1   MODERATE
   9  dim_customer.customer_zip                  16       0    1     5     1   MODERATE
  10  dim_customer.customer_id                   14       0    1     2     1   MODERATE
  11  dim_customer.customer_name                  0       0    0     0     0   LOW
  12  dim_customer.customer_email                 0       0    0     0     0   LOW
  13  dim_customer.signup_date                    0       0    0     0     0   LOW
```

Note the honest result: `amount` (aggregated in 7 queries) is the single most
load-bearing column — even ahead of the flagship `customer_zip`. Unused columns rank
at the bottom with zero fragility.
