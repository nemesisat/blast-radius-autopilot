# EXAMPLES.md — Powerful Examples Across Dataset Types

The requirement: the agent must work on **all kinds of datasets**, proven by worked examples on
≥5 very different ones. Same loop (`AGENTS.md`), same primitives (`BUILD_GUIDE.md`) — only the data
changes. **All five are produced and captured** (`autopilot --loop loop.config.yaml`), output in
`blast-radius-autopilot/examples/CAPTURED_RUNS.md` and `out/examples/`.

> **Flagship (verified live on the real DataHub `showcase-ecommerce` datapack, 2026-07-25):** `drop order_entry.orders.promotion_id` → **3 breaks / 1 degrade · CRITICAL · 2 teams**; downstreams `order_details` + PowerBI reports tagged, Impact Assessment written back (GraphQL read-back in `LIVE_DATAHUB_EVIDENCE.md`).

The table below is the **offline breadth run** on *synthetic* example catalogs (one `loop.config.yaml`) — it proves the same code runs on any dataset shape, separate from the live datapack flagship above.

Status: ☑ produced & captured. Numbers below are from the captured run of **2026-07-30 (post-B17)**;
`autopilot --loop loop.config.yaml` reproduces them. Write-back is a **dry run**, so every row
reports **0 written** — the buckets are `planned` (would be applied) or `queued` (needs a human).

| # | Dataset (type) | Change assessed | Result | Write-back (dry run) |
|---|---|---|---|---|
| 1 | **showcase-ecommerce (synthetic catalog)** | drop `fct_orders.customer_zip` | 6 breaks / 0 degrades / 3 safe / 0 unassessed / **1 ambiguous** · CRITICAL · 3 teams · 41 runs · 10 of 10 analysed | **0 written / 8 queued** — the unattributable reference forces review |
| 2 | **nyc-taxi** (operational time-series) | drop `trips.trip_distance` | 3 breaks / 0 / 2 safe · CRITICAL · 2 teams · 34 runs · 5 of 5 analysed | 7 planned / 0 written / 0 queued |
| 3 | **healthcare** (synthetic, regulated) | rename `encounters.diagnosis_code`→`icd10_code` | 3 breaks / 0 / 1 safe · CRITICAL · 2 teams · 36 runs · 4 of 4 analysed | **0 written / 6 queued** (`require_review`) |
| 4 | **fiction-retail** (clean canvas) | drop `customers.loyalty_tier` | 3 breaks / 0 / 1 safe · CRITICAL · 2 teams · 28 runs · 4 of 4 analysed | 7 planned / 0 written / 0 queued |
| 5 | **finance** (synthetic, SOX) | rename `fct_revenue.revenue_usd`→`net_revenue_usd` | 3 breaks / 0 / 1 safe · CRITICAL · 3 teams · 36 runs · 4 of 4 analysed | **0 written / 7 queued** (`require_review`) |

---

### 1. ☑ E-commerce, cross-platform lineage — *offline synthetic example* (the live flagship runs on the real datapack: `orders` / drop `promotion_id`)
**Scenario:** "Drop `customer_zip` from `fct_orders`." Discover downstreams → read available query
history and downstream SQL definitions → sqlglot column-usage + raw scan → classify. **Finding:**
*breaks* 6 consumers — a Looker dashboard, a dbt model, two PowerBI reports, an ad-hoc export, and
an ad-hoc `JOIN`. Filter-only and `JOIN`-only references count as **breaks**, not degrades: dropping
a column a `WHERE` or `ON` names makes the statement *error*, it does not silently drift. One further
reference is **ambiguous** — an unqualified `customer_zip` across two joined tables that both provide
it — so it is reported separately and never counted as a proven break. **Write-back:** an
auto-generated dbt fix plus a CI-ready PR comment and the Impact Assessment document — but because
of that one unattributable reference, **all 8 mutations are queued for a human, none written**.

### 2. ☑ Operational / time-series — *nyc-taxi*
**Scenario:** drop `trips.trip_distance`. Breaks a distance dashboard, a dbt metrics model, and a
"long trips" monitor that only *filters* on it — the filter-only case errors on a drop, so it is a
break. Coverage 5 of 5, nothing ambiguous → the write-back is eligible to auto-apply (7 planned).

### 3. ☑ Sensitive / regulated — *healthcare* (SYNTHETIC — no real PHI)
**Scenario:** rename `encounters.diagnosis_code`→`icd10_code`. Rename escalates every reference to
a break. **Write-back:** `require_review` → everything **queued for human review**; compliance note
flags HIPAA/BAA-style handling for a real dataset.

### 4. ☑ Clean canvas — *fiction-retail*
**Scenario:** drop `customers.loyalty_tier`. Breaks the loyalty dashboard, the dbt model, and a
"gold members" report that only filters on it. Coverage 4 of 4, nothing ambiguous → eligible to
auto-apply (7 planned).

### 5. ☑ Financial / regulated — *finance* (SYNTHETIC — no real company data)
**Scenario:** rename a regulated revenue column. Touches a board revenue dashboard + P&L model + an
audit report. **Write-back:** everything **queued for review**; note that SOX reporting changes need
Finance/Internal-Audit sign-off.

---

**Adding a 6th dataset** takes no code change — a config entry in `loop.config.yaml` pointed at a new
`catalog.json`. That's the test of dataset-agnosticism, and all five above pass it. All data is
public/synthetic; the two regulated sets carry compliance notes and route writes to review.

---

## How to read the write-back column

Write-back results are reported in five disjoint buckets, and they always add up to what was
planned:

| Bucket | Meaning |
|---|---|
| `written` | emitted to the catalog and the emit returned successfully |
| `queued` | deliberately not applied — a human must approve it |
| `failed` | attempted and raised; the catalog does **not** have it |
| `planned` | not attempted because this was a dry run |
| `skipped` | not attempted for any other reason |

Every run above is a **dry run**, so `written` is 0 everywhere. A dry run reports what it planned,
never what it wrote. In a live run, a mutation the server rejects is reported `failed` — with its
tool, target URN, and error message — never counted as written.
