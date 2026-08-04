# Migration Plan — drop analytics.fct_orders.customer_zip

**Change risk (derived):** CRITICAL with 1 unresolved reference(s) (100/100)

## Ordered steps (deepest upstream first → consumers → BI last)

1. **[BREAKS] q_adhoc_join_on_zip** _(query)_
    - owner: analytics-eng
    - action: manual review — no mechanical fix generated
    - column-analysis (parser) confidence: high
    - static verification: unchanged after fix — manual review
2. **[BREAKS] q_adhoc_zip_export** _(query)_
    - owner: growth-analytics
    - action: manual review — no mechanical fix generated
    - column-analysis (parser) confidence: high
    - static verification: unchanged after fix — manual review
3. **[BREAKS] rpt_orders_by_region** _(dbt_model)_
    - owner: analytics-eng
    - action: apply generated fix: dbt_project/models/rpt_orders_by_region.sql
    - column-analysis (parser) confidence: high
    - static verification: verified-clean after fix (BREAKS -> SAFE)
4. **[BREAKS] Revenue by State** _(powerbi_report)_
    - owner: marketing-bi
    - action: manual review — no mechanical fix generated
    - column-analysis (parser) confidence: high
    - static verification: still impacted after fix — manual review
5. **[BREAKS] Sales by ZIP** _(looker_dashboard)_
    - owner: growth-analytics
    - action: manual review — no mechanical fix generated
    - column-analysis (parser) confidence: high
    - static verification: still impacted after fix — manual review
6. **[BREAKS] ZIP Heatmap** _(powerbi_report)_
    - owner: marketing-bi
    - action: manual review — no mechanical fix generated
    - column-analysis (parser) confidence: high
    - static verification: still impacted after fix — manual review

## Teams to involve

analytics-eng, growth-analytics, marketing-bi

## Verify after the change (impacted downstreams)

- q_adhoc_join_on_zip (BREAKS)
- q_adhoc_zip_export (BREAKS)
- rpt_orders_by_region (BREAKS)
- Revenue by State (BREAKS)
- Sales by ZIP (BREAKS)
- ZIP Heatmap (BREAKS)

## Rollback

- Revert the schema change: re-add column `customer_zip` to `analytics.fct_orders`.
- Close the generated migration PR and revert `dbt_project/models/rpt_orders_by_region.sql` to its pre-change version.
- Re-run Blast Radius Autopilot to confirm the catalog assessment clears.

## Left for a human to decide (not computed)

- Effort: ⟨human to decide⟩
- Timeline: ⟨human to decide⟩
- Deployment window: ⟨human to decide⟩

---
_This plan lists only facts derived from the impact analysis._
_Effort, timeline, and deployment window are left for a human to decide — not computed._
_The only confidence shown is the per-step column-analysis (parser) confidence._
_Coverage: 10 of 10 analysed consumer(s)._
_REVIEW REQUIRED: 0 consumer(s) could not be assessed and are listed as manual-review steps. They are UNKNOWN, not safe; the risk level covers only the 10 analysed consumer(s)._
_1 low-confidence reference(s) were surfaced but not counted — verify manually._
_Static verification: REVIEW_REQUIRED — breaks 6 -> 5, coverage 10 of 10 analysed._
_Verification is STATIC: the patch was applied in an isolated copy, the patched SQL re-parsed, and impact recomputed. No queries were executed and no data was read._
_Verification did not PASS, so no step here may be applied without human approval._
