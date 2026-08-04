## 🧨 Blast Radius Autopilot — risk **🚨 CRITICAL** (88/100)

Assessing **`rename clinical.encounters.diagnosis_code -> icd10_code`** against available query history and downstream SQL definitions in `healthcare`.

🔴 **3 break** · 🟡 **0 degrade** · 🟢 1 safe · ⚪ **0 unassessed** · ◐ **0 ambiguous** · 👥 2 team(s) · ▶️ 36 impacted runs in history

**Coverage:** 4 of 4 analysed consumer(s).

> rename clinical.encounters.diagnosis_code -> icd10_code breaks 3 and degrades 0 downstream consumer(s) across 2 team(s) (clinical-data, population-health), spanning 36 query runs in history. Change risk: CRITICAL (88/100).

<details open><summary><b>Impacted consumers</b></summary>

| Impact | Consumer | Team | Uses column | Runs |
|---|---|---|---|---|
| 🔴 BREAKS | Diagnoses by Month _looker dashboard_ | population-health | `select` (group, select) | 22 |
| 🔴 BREAKS | rpt_diagnoses _dbt model_ | clinical-data | `select` (select) | 8 |
| 🔴 BREAKS | q_filter_dx | population-health | `filter` (where) | 6 |

</details>

### 🛠 Proposed migration

**`dbt_project/models/rpt_diagnoses.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_diagnoses.sql
+++ b/dbt_project/models/rpt_diagnoses.sql
@@ -2,7 +2,7 @@
 -- Owned by team:clinical-data. Downstream of clinical.encounters.
 SELECT
     encounter_id,
-    diagnosis_code,
+    icd10_code,
     cost
 FROM clinical.encounters
 WHERE encounter_date >= '2026-01-01'
```

### 📤 Catalog write-back

**0 planned, 0 written, 6 queued, 0 failed, 0 skipped**  _(dry run — nothing was written)_

| Outcome | Count |
|---|---:|
| Planned (total) | 6 |
| Written | 0 |
| Queued for review | 6 |
| Failed | 0 |
| Not attempted (dry run) | 0 |
| Skipped | 0 |

### ✅ Reviewer checklist

- [ ] Confirm the 3 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: clinical-data, population-health

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
