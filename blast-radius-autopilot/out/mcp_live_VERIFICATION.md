# Migration Verification — ❌ FAIL

**Change.** `drop order_entry_db.analytics.order_details.category_name`

**Verdict.** ❌ FAIL — breaks 2→2 (+0), degrades 1→1, ambiguous 0→0, unassessed 19→19, coverage 5 of 24 analysed

> Static evidence only. No queries were executed.

## Why

- `breaks_not_reduced` — the break count did not go down
- `breaks_remaining` — breaking consumers still remain
- `degrades_remaining` — one or more consumers still execute with changed output or behaviour
- `unknown_consumers_present` — at least one consumer could not be assessed (UNKNOWN)
- `coverage_incomplete` — coverage is incomplete — some consumers were never analysed
- `fix_incomplete_column_still_referenced` — a patched file still references the dropped column — the fix is incomplete

## Before → after

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| 🔴 Breaks | 2 | 2 | +0 |
| 🟡 Degrades | 1 | 1 | +0 |
| 🟢 Safe | 2 | 2 | +0 |
| ⚪ Unassessed | 19 | 19 | +0 |
| ◐ Ambiguous | 0 | 0 | +0 |
| Coverage | 5 of 24 analysed | 5 of 24 analysed | — |

## Fix incomplete — column still referenced after patching

- `models/mcp_custom_sql_query_2.sql:6: still references `category_name` — WHERE category_name IS NOT NULL`
- `models/mcp_custom_sql_query_2.sql:7: still references `category_name` — GROUP BY category_name`
- `models/mcp_custom_sql_query_4.sql:6: still references `category_name` — WHERE category_name IS NOT NULL`
- `models/mcp_custom_sql_query_4.sql:7: still references `category_name` — GROUP BY order_date, category_name`

## Unassessed consumers (not safe — manual review)

- Customer Analysis
- Customer Analytics Measures
- DAX Visual
- Essential KPI Measures
- Executive Summary
- Geographic Measures
- Geographics
- ORDER_DETAILS
- ORDER_HISTORY
- Order Details
- Order Mode
- Orders By Day
- Product Perfromance Measures
- Promotions
- Time Inteligence Measures
- Top Product Category
- datahub_order_entries
- order_details
- order_history

## Patched files that WERE recomputed

- `models/mcp_custom_sql_query_2.sql` → consumer query `mcp_custom_sql_query_2`
- `models/mcp_custom_sql_query_4.sql` → consumer query `mcp_custom_sql_query_4`
- `models/mcp_order_details_replica_5.sql` → consumer query `mcp_order_details_replica_5`

## Files patched (in isolation)

- `models/mcp_custom_sql_query_2.sql`
- `models/mcp_custom_sql_query_4.sql`
- `models/mcp_order_details_replica_5.sql`

## Scope of this verification

> STATIC verification only: the patch was applied in an isolated copy, the patched SQL was re-parsed, and column-level impact was recomputed. No queries were executed, no warehouse was contacted, and no data was read. This is not evidence about runtime behaviour or results.

_Verified at 2026-08-04T14:33:59+00:00 · method: static._