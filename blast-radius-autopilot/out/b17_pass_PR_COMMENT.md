## 🧨 Blast Radius Autopilot — risk **🟠 HIGH** (56/100)

Assessing **`drop analytics.fct_signups.referrer_code`** against available query history and downstream SQL definitions in `verified-migration (synthetic — demonstrates a PASS verification)`.

🔴 **2 break** · 🟡 **0 degrade** · 🟢 1 safe · ⚪ **0 unassessed** · ◐ **0 ambiguous** · 👥 1 team(s) · ▶️ 23 impacted runs in history

**Coverage:** 3 of 3 analysed consumer(s).

> drop analytics.fct_signups.referrer_code breaks 2 and degrades 0 downstream consumer(s) across 1 team(s) (growth-eng), spanning 23 query runs in history. Change risk: HIGH (56/100).

<details open><summary><b>Impacted consumers</b></summary>

| Impact | Consumer | Team | Uses column | Runs |
|---|---|---|---|---|
| 🔴 BREAKS | rpt_signups_by_plan _dbt model_ | growth-eng | `select` (select) | 14 |
| 🔴 BREAKS | rpt_referrals _dbt model_ | growth-eng | `select` (select) | 9 |

</details>

### 🛠 Proposed migration

**`dbt_project/models/rpt_signups_by_plan.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_signups_by_plan.sql
+++ b/dbt_project/models/rpt_signups_by_plan.sql
@@ -2,7 +2,6 @@
 -- Owned by team:growth-eng. Downstream of analytics.fct_signups.
 SELECT
     s.signup_id,
-    s.plan,
-    s.referrer_code
+    s.plan
 FROM analytics.fct_signups s
 WHERE s.plan IS NOT NULL
```

**`dbt_project/models/rpt_referrals.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_referrals.sql
+++ b/dbt_project/models/rpt_referrals.sql
@@ -3,6 +3,5 @@
 SELECT
     s.signup_id,
     s.account_id,
-    s.referrer_code,
     s.signed_up_at
 FROM analytics.fct_signups s
```

### 🔬 Migration verification (static) — ✅ **PASS**

The generated fix was applied in an isolated copy, the patched SQL re-parsed, and impact recomputed: **no breaking or unassessed consumers remain**.

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| 🔴 Breaks | 2 | 0 | -2 |
| 🟡 Degrades | 0 | 0 | +0 |
| 🟢 Safe | 1 | 3 | +2 |
| ⚪ Unassessed | 0 | 0 | +0 |
| ◐ Ambiguous | 0 | 0 | +0 |
| Coverage | 3 of 3 analysed | 3 of 3 analysed | — |

<details open><summary><b>Consumer transitions</b></summary>

- `rpt_referrals`: BREAKS → SAFE
- `rpt_signups_by_plan`: BREAKS → SAFE

</details>

<details><summary><b>Why this verdict</b></summary>

- `breaks_eliminated` — no breaking consumers remain among those analysed

</details>

**Patched files that WERE recomputed:** `dbt_project/models/rpt_referrals.sql` → `q_dbt_rpt_referrals`, `dbt_project/models/rpt_signups_by_plan.sql` → `q_dbt_rpt_signups_by_plan`

> **Scope.** Static verification: the patch was applied in an isolated copy, the patched SQL re-parsed, and column-level impact recomputed. **No queries were executed, no warehouse was contacted, and no data was read.** This is evidence about the SQL, not about runtime behaviour or results.

### 📤 Catalog write-back

**6 planned, 0 written, 0 queued, 0 failed, 0 skipped**  _(dry run — nothing was written)_

| Outcome | Count |
|---|---:|
| Planned (total) | 6 |
| Written | 0 |
| Queued for review | 0 |
| Failed | 0 |
| Not attempted (dry run) | 6 |
| Skipped | 0 |

### ✅ Reviewer checklist

- [ ] Confirm the 2 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: growth-eng

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
