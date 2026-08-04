## 🧨 Blast Radius Autopilot — risk **🚨 CRITICAL** (100/100)

Assessing **`drop analytics.fct_orders.customer_zip`** against available query history and downstream SQL definitions in `showcase-ecommerce`.

🔴 **6 break** · 🟡 **0 degrade** · 🟢 3 safe · ⚪ **0 unassessed** · ◐ **1 ambiguous** · 👥 3 team(s) · ▶️ 41 impacted runs in history

**Coverage:** 10 of 10 analysed consumer(s).

> ⚠️ **REVIEW REQUIRED — do not auto-apply.** 1 column reference(s) could not be confidently attributed to a source table, so they are **not** safe and **not** counted as proven breaks.

> drop analytics.fct_orders.customer_zip breaks 6 and degrades 0 downstream consumer(s) across 3 team(s) (analytics-eng, growth-analytics, marketing-bi), spanning 41 query runs in history. Change risk: CRITICAL with 1 unresolved reference(s) (100/100). 1 column reference(s) could not be confidently attributed to a source table (unqualified column across joined tables) — not safe, and not counted as a proven break — REVIEW REQUIRED before applying.

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

### 📤 Catalog write-back

**0 planned, 0 written, 8 queued, 0 failed, 0 skipped**  _(dry run — nothing was written)_

| Outcome | Count |
|---|---:|
| Planned (total) | 8 |
| Written | 0 |
| Queued for review | 8 |
| Failed | 0 |
| Not attempted (dry run) | 0 |
| Skipped | 0 |

### ✅ Reviewer checklist

- [ ] Confirm the 6 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: analytics-eng, growth-analytics, marketing-bi
- [ ] Manually verify 1 low-confidence reference(s)

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
