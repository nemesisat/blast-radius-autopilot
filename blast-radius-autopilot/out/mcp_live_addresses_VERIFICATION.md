# Migration Verification — ❌ FAIL

**Change.** `drop order_entry_db.order_entry.addresses.country_id`

**Verdict.** ❌ FAIL — breaks 0→0 (+0), degrades 0→0, ambiguous 0→0, unassessed 12→12, coverage 5 of 17 analysed

> Static evidence only. No queries were executed.

## Why

- `no_patch_provided` — no patch was supplied

## Before → after

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| 🔴 Breaks | 0 | 0 | +0 |
| 🟡 Degrades | 0 | 0 | +0 |
| 🟢 Safe | 5 | 5 | +0 |
| ⚪ Unassessed | 12 | 12 | +0 |
| ◐ Ambiguous | 0 | 0 | +0 |
| Coverage | 5 of 17 analysed | 5 of 17 analysed | — |

## Files patched (in isolation)

- `—`

## Scope of this verification

> STATIC verification only: the patch was applied in an isolated copy, the patched SQL was re-parsed, and column-level impact was recomputed. No queries were executed, no warehouse was contacted, and no data was read. This is not evidence about runtime behaviour or results.

_Verified at 2026-08-04T14:34:20+00:00 · method: static._