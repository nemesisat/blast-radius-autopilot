## 🧨 Blast Radius Autopilot — risk **🚨 CRITICAL** (100/100)

Assessing **`drop analytics.fct_orders.customer_zip`** against available query history and downstream SQL definitions in `showcase-ecommerce`.

🔴 **6 break** · 🟡 **0 degrade** · 🟢 3 safe · ⚪ **0 unassessed** · 👥 3 team(s) · ▶️ 41 impacted runs in history

**Coverage:** 10 of 10 analysed consumer(s).

> drop analytics.fct_orders.customer_zip breaks 6 and degrades 0 downstream consumer(s) across 3 team(s) (analytics-eng, growth-analytics, marketing-bi), spanning 41 query runs in history. Change risk: CRITICAL (100/100).

<details open><summary><b>Impacted consumers</b></summary>

| Impact | Consumer | Team | Uses column | Runs |
|---|---|---|---|---|
| 🔴 BREAKS | Sales by ZIP _looker dashboard_ | growth-analytics | `select` (group, select) | 12 |
| 🔴 BREAKS | Revenue by State _powerbi report_ | marketing-bi | `filter` (where) | 9 |
| 🔴 BREAKS | rpt_orders_by_region _dbt model_ | analytics-eng | `select` (select) | 6 |
| 🔴 BREAKS | ZIP Heatmap _powerbi report_ | marketing-bi | `select` (group, select) | 5 |
| 🔴 BREAKS | q_adhoc_join_on_zip | analytics-eng | `filter` (join) | 5 |
| 🔴 BREAKS | q_adhoc_zip_export | growth-analytics | `select` (select) | 4 |

</details>

<details><summary>⚪ Low-confidence (surfaced, not counted)</summary>

- `q_adhoc_ambiguous_zip` — projects/derives `customer_zip` (in select) → column removed

</details>

### 🛠 Proposed migration

**`dbt_project/models/rpt_orders_by_region.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_orders_by_region.sql
+++ b/dbt_project/models/rpt_orders_by_region.sql
@@ -2,7 +2,6 @@
 -- Owned by team:analytics-eng. Downstream of analytics.fct_orders.
 SELECT
     o.order_id,
-    o.customer_zip,
     o.amount
 FROM analytics.fct_orders o
 WHERE o.status = 'complete'
```

### 🔬 Migration verification (static) — ⚠️ **REVIEW REQUIRED**

**Human review required.** The fix improved things but did not fully clear the blast radius, or some consumers could not be assessed.

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| 🔴 Breaks | 6 | 5 | -1 |
| 🟡 Degrades | 0 | 0 | +0 |
| 🟢 Safe | 3 | 4 | +1 |
| ⚪ Unassessed | 0 | 0 | +0 |
| Coverage | 10 of 10 analysed | 10 of 10 analysed | — |

<details open><summary><b>Consumer transitions</b></summary>

- `rpt_orders_by_region`: BREAKS → SAFE

</details>

<details><summary><b>Why this verdict</b></summary>

- `breaks_remaining` — breaking consumers still remain
- `manual_work_remaining` — consumers remain that no mechanical fix can reach

</details>

> **Scope.** Static verification: the patch was applied in an isolated copy, the patched SQL re-parsed, and column-level impact recomputed. **No queries were executed, no warehouse was contacted, and no data was read.** This is evidence about the SQL, not about runtime behaviour or results.

### ✅ Reviewer checklist

- [ ] Confirm the 6 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: analytics-eng, growth-analytics, marketing-bi
- [ ] **Verification returned REVIEW_REQUIRED** — do not merge on the strength of the generated fix alone
- [ ] Manually verify 1 low-confidence reference(s)

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
