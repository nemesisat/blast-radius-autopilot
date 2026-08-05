# Migration Verification — ⚠️ REVIEW REQUIRED

**Change.** `drop analytics.fct_orders.customer_zip`

**Verdict.** ⚠️ REVIEW REQUIRED — breaks 6→5 (-1), degrades 0→0, ambiguous 1→1, unassessed 0→0, coverage 10 of 10 analysed

> Static evidence only. No queries were executed.

## Why

- `breaks_remaining` — breaking consumers still remain
- `ambiguous_consumers_present` — at least one column reference could not be confidently attributed to a source table
- `manual_work_remaining` — consumers remain that no mechanical fix can reach

## Before → after

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| 🔴 Breaks | 6 | 5 | -1 |
| 🟡 Degrades | 0 | 0 | +0 |
| 🟢 Safe | 3 | 4 | +1 |
| ⚪ Unassessed | 0 | 0 | +0 |
| ◐ Ambiguous | 1 | 1 | +0 |
| Coverage | 10 of 10 analysed | 10 of 10 analysed | — |

## Consumer transitions

- rpt_orders_by_region: BREAKS → SAFE (improved)

## Ambiguous references (parsed, but not attributable — manual review)

_The SQL parsed and the column was found, but it could not be confidently attributed to a source table (an unqualified column that more than one joined table provides). Not safe, and not a proven break._

- q_adhoc_ambiguous_zip

## Patched files that WERE recomputed

- `dbt_project/models/rpt_orders_by_region.sql` → consumer query `q_dbt_rpt_orders_by_region`

## Still needs manual work (no mechanical fix possible)

- Revenue by State
- Sales by ZIP
- ZIP Heatmap
- q_adhoc_join_on_zip
- q_adhoc_zip_export

## Files patched (in isolation)

- `dbt_project/models/rpt_orders_by_region.sql`

## Scope of this verification

> STATIC verification only: the patch was applied in an isolated copy, the patched SQL was re-parsed, and column-level impact was recomputed. No queries were executed, no warehouse was contacted, and no data was read. This is not evidence about runtime behaviour or results.

_Verified at 2026-08-05T17:31:57+00:00 · method: static._