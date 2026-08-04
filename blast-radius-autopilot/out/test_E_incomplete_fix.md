# Migration Verification — ⚠️ REVIEW REQUIRED

**Change.** `drop analytics.fct_signups.referrer_code`

**Verdict.** ⚠️ REVIEW REQUIRED — breaks 2→1 (-1), degrades 0→0, ambiguous 0→0, unassessed 0→0, coverage 3 of 3 analysed

> Static evidence only. No queries were executed.

## Why

- `breaks_remaining` — breaking consumers still remain
- `fix_incomplete_column_still_referenced` — a patched file still references the dropped column — the fix is incomplete

## Before → after

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| 🔴 Breaks | 2 | 1 | -1 |
| 🟡 Degrades | 0 | 0 | +0 |
| 🟢 Safe | 1 | 2 | +1 |
| ⚪ Unassessed | 0 | 0 | +0 |
| ◐ Ambiguous | 0 | 0 | +0 |
| Coverage | 3 of 3 analysed | 3 of 3 analysed | — |

## Consumer transitions

- rpt_signups_by_plan: BREAKS → SAFE (improved)

## Fix incomplete — column still referenced after patching

- `dbt_project/models/rpt_referrals.sql:8: still references `referrer_code` — WHERE s.referrer_code IS NOT NULL`

## Patched files that WERE recomputed

- `dbt_project/models/rpt_referrals.sql` → consumer query `q_dbt_rpt_referrals`
- `dbt_project/models/rpt_signups_by_plan.sql` → consumer query `q_dbt_rpt_signups_by_plan`

## Files patched (in isolation)

- `dbt_project/models/rpt_signups_by_plan.sql`
- `dbt_project/models/rpt_referrals.sql`

## Scope of this verification

> STATIC verification only: the patch was applied in an isolated copy, the patched SQL was re-parsed, and column-level impact was recomputed. No queries were executed, no warehouse was contacted, and no data was read. This is not evidence about runtime behaviour or results.

_Verified at 2026-08-04T14:32:28+00:00 · method: static._