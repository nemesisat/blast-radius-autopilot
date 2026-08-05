# Catalog Sweep — showcase-ecommerce

_Every candidate column change, assessed with the same impact → fix → verify chain as a single run._

**2 dataset(s) · 13 column(s) assessed of 13 · 13 of 13 candidate(s) fully assessed · 9 landmine(s) · 0 unassessed · 0 need review · 4 verified safe · 0 error(s) · duration 0.2s**

| Datasets | Columns assessed | Coverage | Duration | Started |
|---:|---:|---|---:|---|
| 2 | 13 of 13 | 13 of 13 candidate(s) fully assessed | 0.2s | 2026-08-05T17:35:29+00:00 |

| Bucket | Count |
|---|---:|
| 🔴 Landmines | 9 |
| ❓ Unassessed | 0 |
| ⚠️ Needs review | 0 |
| ✅ Verified safe | 4 |
| ⚠️ Errors | 0 |

> Static analysis only. Patches were applied in isolated copies and re-parsed; **no query was executed, no warehouse was contacted, no data was read**, and **nothing was written to DataHub** — a sweep is read-only by construction.

---

## 🔴 Landmines (9)

_Proven breakage that no mechanical fix reaches, or a failed verification. Changing these needs a migration plan and owners in the room._

| Column | Change | Risk | Breaks | Degr | Safe | Unknown | Coverage | Patch | Detail |
|---|---|---|---:|---:|---:|---:|---|---|---|
| `fct_orders.amount` | drop analytics.fct_orders.amount | CRITICAL (100) | 7 | 0 | 3 | 0 | 10 of 10 analysed | [`patch`](out/sweep/showcase-ecommerce/patches/drop-analytics-fct-orders-amount.patch) | verification **REVIEW_REQUIRED** · breaks 7→6 · unreachable by any mechanical fix: Sales by ZIP, Revenue by State, Daily Orders +3 more · `breaks_remaining`, `manual_work_remaining`, `6 breaking consumer(s) no mechanical fix reaches` |
| `fct_orders.customer_zip` | drop analytics.fct_orders.customer_zip | CRITICAL (100) | 6 | 0 | 3 | 0 | 10 of 10 analysed | [`patch`](out/sweep/showcase-ecommerce/patches/drop-analytics-fct-orders-customer-zip.patch) | verification **REVIEW_REQUIRED** · breaks 6→5 · unreachable by any mechanical fix: Sales by ZIP, ZIP Heatmap, Revenue by State +2 more · `breaks_remaining`, `ambiguous_consumers_present`, `manual_work_remaining`, `5 breaking consumer(s) no mechanical fix reaches` |
| `fct_orders.customer_id` | drop analytics.fct_orders.customer_id | CRITICAL (72) | 3 | 0 | 7 | 0 | 10 of 10 analysed | — | unreachable by any mechanical fix: query q_adhoc_zip_export, query q_adhoc_customer_orders, query q_adhoc_ambiguous_zip · `3 breaking consumer(s) no mechanical fix reaches` |
| `fct_orders.order_date` | drop analytics.fct_orders.order_date | CRITICAL (60) | 2 | 0 | 8 | 0 | 10 of 10 analysed | — | unreachable by any mechanical fix: Daily Orders, query q_adhoc_zip_export · `2 breaking consumer(s) no mechanical fix reaches` |
| `fct_orders.status` | drop analytics.fct_orders.status | HIGH (56) | 2 | 0 | 8 | 0 | 10 of 10 analysed | [`patch`](out/sweep/showcase-ecommerce/patches/drop-analytics-fct-orders-status.patch) | verification **FAIL** · breaks 2→2 · unreachable by any mechanical fix: query q_adhoc_status_breakdown · `breaks_not_reduced`, `breaks_remaining`, `manual_work_remaining`, `fix_incomplete_column_still_referenced` |
| `fct_orders.ship_state` | drop analytics.fct_orders.ship_state | HIGH (30) | 1 | 0 | 9 | 0 | 10 of 10 analysed | — | unreachable by any mechanical fix: Revenue by State · `1 breaking consumer(s) no mechanical fix reaches` |
| `dim_customer.customer_zip` | drop analytics.dim_customer.customer_zip | MODERATE (28) | 1 | 0 | 8 | 0 | 10 of 10 analysed | — | unreachable by any mechanical fix: query q_adhoc_join_on_zip · `1 breaking consumer(s) no mechanical fix reaches` |
| `dim_customer.customer_segment` | drop analytics.dim_customer.customer_segment | MODERATE (28) | 1 | 0 | 9 | 0 | 10 of 10 analysed | — | unreachable by any mechanical fix: query q_adhoc_join_on_zip · `1 breaking consumer(s) no mechanical fix reaches` |
| `dim_customer.customer_id` | drop analytics.dim_customer.customer_id | MODERATE (26) | 1 | 0 | 9 | 0 | 10 of 10 analysed | — | unreachable by any mechanical fix: query q_adhoc_ambiguous_zip · `1 breaking consumer(s) no mechanical fix reaches` |

## ❓ Unassessed (0)

_At least one consumer could not be read (unparseable SQL, or no SQL definition at all). **Not safe** — nothing is known about them. Zero breaks over a partial corpus is not a clean bill of health._

None.

## ⚠️ Needs review (0)

_Improved, ambiguous, or incomplete. A human decides._

None.

## ✅ Verified safe (4)

_Safe to change. Read the `basis` column: `verified_patch` means a fix was generated, applied in isolation and re-checked; `no_references` means nothing that parses referenced the column, so no patch was needed and none was verified._

| Column | Change | Risk | Breaks | Degr | Safe | Unknown | Coverage | Patch | Detail |
|---|---|---|---:|---:|---:|---:|---|---|---|
| `fct_orders.order_id` | drop analytics.fct_orders.order_id | MODERATE (28) | 1 | 0 | 9 | 0 | 10 of 10 analysed | [`patch`](out/sweep/showcase-ecommerce/patches/drop-analytics-fct-orders-order-id.patch) | verification **PASS** · breaks 1→0 · basis `verified_patch` · `breaks_eliminated` |
| `dim_customer.customer_name` | drop analytics.dim_customer.customer_name | LOW (0) | 0 | 0 | 10 | 0 | 10 of 10 analysed | — | basis `no_references` · `no consumer that parses references this column; no patch was needed` |
| `dim_customer.customer_email` | drop analytics.dim_customer.customer_email | LOW (0) | 0 | 0 | 10 | 0 | 10 of 10 analysed | — | basis `no_references` · `no consumer that parses references this column; no patch was needed` |
| `dim_customer.signup_date` | drop analytics.dim_customer.signup_date | LOW (0) | 0 | 0 | 10 | 0 | 10 of 10 analysed | — | basis `no_references` · `no consumer that parses references this column; no patch was needed` |

## ⚠️ Errors (0)

_The sweep could not assess these. An error is not a verdict — nothing is claimed about them either way._

None.

---

_Generated by Blast Radius Autopilot · sweep of `showcase-ecommerce` · ops drop · public/synthetic data only._
