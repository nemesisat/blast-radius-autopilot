## 🧨 Blast Radius Autopilot — risk **🚨 CRITICAL** (87/100)

Assessing **`drop nyc.trips.trip_distance`** against available query history and downstream SQL definitions in `nyc-taxi`.

🔴 **3 break** · 🟡 **0 degrade** · 🟢 2 safe · ⚪ **0 unassessed** · ◐ **0 ambiguous** · 👥 2 team(s) · ▶️ 34 impacted runs in history

**Coverage:** 5 of 5 analysed consumer(s).

> drop nyc.trips.trip_distance breaks 3 and degrades 0 downstream consumer(s) across 2 team(s) (city-analytics, mobility-data), spanning 34 query runs in history. Change risk: CRITICAL (87/100).

<details open><summary><b>Impacted consumers</b></summary>

| Impact | Consumer | Team | Uses column | Runs |
|---|---|---|---|---|
| 🔴 BREAKS | Avg Distance by Zone _looker dashboard_ | city-analytics | `select` (select) | 18 |
| 🔴 BREAKS | rpt_trip_metrics _dbt model_ | mobility-data | `select` (select) | 9 |
| 🔴 BREAKS | Long Trips Monitor _powerbi report_ | city-analytics | `filter` (where) | 7 |

</details>

### 🛠 Proposed migration

**`dbt_project/models/rpt_trip_metrics.sql`** — auto-generated ✅ (minimal)

```diff
--- a/dbt_project/models/rpt_trip_metrics.sql
+++ b/dbt_project/models/rpt_trip_metrics.sql
@@ -2,7 +2,6 @@
 -- Owned by team:mobility-data. Downstream of nyc.trips.
 SELECT
     trip_id,
-    trip_distance,
     fare_amount
 FROM nyc.trips
 WHERE passenger_count > 0
```

### 📤 Catalog write-back

**7 planned, 0 written, 0 queued, 0 failed, 0 skipped**  _(dry run — nothing was written)_

| Outcome | Count |
|---|---:|
| Planned (total) | 7 |
| Written | 0 |
| Queued for review | 0 |
| Failed | 0 |
| Not attempted (dry run) | 7 |
| Skipped | 0 |

### ✅ Reviewer checklist

- [ ] Confirm the 3 breaking consumer(s) are migrated or signed off
- [ ] Notify impacted teams: city-analytics, mobility-data

_Auto-posted by Blast Radius Autopilot. Public/synthetic data only._
