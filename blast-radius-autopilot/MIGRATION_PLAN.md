# Migration Plan — drop analytics.fct_signups.referrer_code

**Change risk (derived):** HIGH (56/100)

## Ordered steps (deepest upstream first → consumers → BI last)

1. **[BREAKS] rpt_referrals** _(dbt_model)_
    - owner: growth-eng
    - action: apply generated fix: dbt_project/models/rpt_referrals.sql
    - column-analysis (parser) confidence: high
    - static verification: verified-clean after fix (BREAKS -> SAFE)
2. **[BREAKS] rpt_signups_by_plan** _(dbt_model)_
    - owner: growth-eng
    - action: apply generated fix: dbt_project/models/rpt_signups_by_plan.sql
    - column-analysis (parser) confidence: high
    - static verification: verified-clean after fix (BREAKS -> SAFE)

## Teams to involve

growth-eng

## Verify after the change (impacted downstreams)

- rpt_referrals (BREAKS)
- rpt_signups_by_plan (BREAKS)

## Rollback

- Revert the schema change: re-add column `referrer_code` to `analytics.fct_signups`.
- Close the generated migration PR and revert `dbt_project/models/rpt_signups_by_plan.sql` to its pre-change version.
- Close the generated migration PR and revert `dbt_project/models/rpt_referrals.sql` to its pre-change version.
- Re-run Blast Radius Autopilot to confirm the catalog assessment clears.

## Left for a human to decide (not computed)

- Effort: ⟨human to decide⟩
- Timeline: ⟨human to decide⟩
- Deployment window: ⟨human to decide⟩

---
_This plan lists only facts derived from the impact analysis._
_Effort, timeline, and deployment window are left for a human to decide — not computed._
_The only confidence shown is the per-step column-analysis (parser) confidence._
_Coverage: 3 of 3 analysed consumer(s)._
_Static verification: PASS — breaks 2 -> 0, coverage 3 of 3 analysed._
_Verification is STATIC: the patch was applied in an isolated copy, the patched SQL re-parsed, and impact recomputed. No queries were executed and no data was read._
