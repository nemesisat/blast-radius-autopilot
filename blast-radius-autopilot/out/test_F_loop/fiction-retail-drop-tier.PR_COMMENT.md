## 🧨 Blast Radius Autopilot — risk **🚨 CRITICAL** (84/100)

Assessing **`drop retail.customers.loyalty_tier`** against available query history and downstream SQL definitions in `fiction-retail`.

🔴 **3 break** · 🟡 **0 degrade** · 🟢 1 safe · ⚪ **0 unassessed** · ◐ **0 ambiguous** · 👥 2 team(s) · ▶️ 28 impacted runs in history

**Coverage:** 4 of 4 analysed consumer(s).

> drop retail.customers.loyalty_tier breaks 3 and degrades 0 downstream consumer(s) across 2 team(s) (crm-analytics, retail-data), spanning 28 query runs in history. Change risk: CRITICAL (84/100).

<details open><summary><b>Impacted consumers</b></summary>

| Impact | Consumer | Team | Uses column | Runs |
|---|---|---|---|---|
| 🔴 BREAKS | Loyalty Mix _looker dashboard_ | crm-analytics | `select` (group, select) | 16 |
| 🔴 BREAKS | rpt_loyalty _dbt model_ | retail-data | `select` (select) | 7 |
| 🔴 BREAKS | Gold Members _powerbi report_ | crm-analytics | `filter` (where) | 5 |

</details>

### 🛠 Proposed migration

**`dbt_project/models/rpt_loyalty.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_loyalty.sql
+++ b/dbt_project/models/rpt_loyalty.sql
@@ -2,6 +2,5 @@
 -- Owned by team:retail-data. Downstream of retail.customers.
 SELECT
     customer_id,
-    loyalty_tier,
     region
 FROM retail.customers
```

### 📤 Catalog write-back

**0 planned, 0 written (auto), 0 written (human-approved), 7 queued, 0 failed, 0 skipped**  _(dry run — nothing was written)_

| Outcome | Count |
|---|---:|
| Planned (total) | 7 |
| Written — automatic (verification PASSed) | 0 |
| Written — human-approved | 0 |
| Queued for review | 7 |
| Failed | 0 |
| Not attempted (dry run) | 0 |
| Skipped | 0 |

**Applied by:** none

**Queued because:** `not_verified` — a migration is written automatically only when static verification returned PASS.

### ✅ Reviewer checklist

- [ ] Confirm the 3 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: crm-analytics, retail-data

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
