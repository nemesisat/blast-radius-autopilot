## 🧨 Blast Radius Autopilot — risk **🚨 CRITICAL** (93/100)

Assessing **`rename finance.fct_revenue.revenue_usd -> net_revenue_usd`** against available query history and downstream SQL definitions in `finance`.

🔴 **3 break** · 🟡 **0 degrade** · 🟢 1 safe · ⚪ **0 unassessed** · ◐ **0 ambiguous** · 👥 3 team(s) · ▶️ 36 impacted runs in history

**Coverage:** 4 of 4 analysed consumer(s).

> rename finance.fct_revenue.revenue_usd -> net_revenue_usd breaks 3 and degrades 0 downstream consumer(s) across 3 team(s) (finance-reporting, fp-and-a, internal-audit), spanning 36 query runs in history. Change risk: CRITICAL (93/100).

<details open><summary><b>Impacted consumers</b></summary>

| Impact | Consumer | Team | Uses column | Runs |
|---|---|---|---|---|
| 🔴 BREAKS | Revenue by Region (Board) _looker dashboard_ | finance-reporting | `select` (select) | 20 |
| 🔴 BREAKS | rpt_pnl _dbt model_ | fp-and-a | `select` (select) | 10 |
| 🔴 BREAKS | Positive Revenue Audit _powerbi report_ | internal-audit | `filter` (where) | 6 |

</details>

### 🛠 Proposed migration

**`dbt_project/models/rpt_pnl.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_pnl.sql
+++ b/dbt_project/models/rpt_pnl.sql
@@ -2,6 +2,6 @@
 -- Owned by team:fp-and-a. Downstream of finance.fct_revenue. SOX-scoped.
 SELECT
     period,
-    revenue_usd,
+    net_revenue_usd,
     cost_usd
 FROM finance.fct_revenue
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

**Queued because:** `not_verified+require_review` — a migration is written automatically only when static verification returned PASS.

### ✅ Reviewer checklist

- [ ] Confirm the 3 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: finance-reporting, fp-and-a, internal-audit

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
