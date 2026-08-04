# MCP evidence — reads via the DataHub MCP server

> **Current section: [2026-08-03 — B20 live re-run](#2026-08-03--b20-live-re-run-both-mcp-targets-re-verified-against-the-current-build)**
> — both MCP targets re-verified against the shipped build (post-B15→B20), plus the live
> approval read-back. Sections dated **2026-07-25 / 07-29 / 07-30** below are kept for the
> record and describe **older semantics**; do not quote their numbers as current.

## 2026-07-25 — first reads over MCP (historical)

The flagship report was built from data pulled **through DataHub's official MCP server**
(`mcp-server-datahub` v0.6.0), not GraphQL. An MCP client (Python `mcp` lib) launched the server
over **stdio** and called its tools; each call + response is logged below. Public/synthetic
(official `showcase-ecommerce` datapack) data only.

## STEP 0 — server + connection

- Server: `mcp-server-datahub` **0.6.0** (`pip install mcp-server-datahub`), transport **stdio**,
  authed via `DATAHUB_GMS_URL=http://localhost:8080` + `DATAHUB_GMS_TOKEN` (from `.env`, gitignored).
- Server log confirms it connected to the local instance: `is_cloud=False, version=(1,5,0,6)`.
- **MCP tools listed by the client (8):** `search`, `get_lineage`, `get_dataset_queries`,
  `get_entities`, `list_schema_fields`, `get_lineage_paths_between`, `search_documents`,
  `grep_documents`.

## STEP 1 — reads over MCP for `order_entry.orders`

Target: `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.orders,PROD)`

| MCP tool call | Result (from the server) |
|---|---|
| `search(query="orders")` | total **1182**; top hit = the real Snowflake `orders` URN (+ s3/dbt/postgres variants) |
| `list_schema_fields(urn=orders)` | **15 fields** (see below), `totalFields=15` |
| `get_entities(urns=[orders])` | name `ORDERS`, platform snowflake; `editableProperties.description` = our Blast Radius footer; tags incl. `pending-schema-change`; PII glossary terms |
| `get_lineage(urn=orders, upstream=false, max_hops=2)` | **17 downstreams** incl. `order_details` (dbt/snowflake/looker/powerbi), `Essential KPI Measures`, `Customer Analytics Measures`, `Geographic Measures`, `Time Inteligence Measures`, Tableau custom SQL, `order_details_replica` |
| `get_dataset_queries(urn=orders)` | `total: 0` — **empty** (the datapack ships no query history; noted) |

**MCP `list_schema_fields` returned these 15 columns:**
`order_id (NUMBER), order_date (VARCHAR), order_mode (VARCHAR), customer_id (NUMBER), order_status
(NUMBER), order_total (FLOAT), sales_rep_id (NUMBER), promotion_id (FLOAT), warehouse_id (NUMBER),
delivery_type (VARCHAR), cost_of_delivery (FLOAT), wait_till_complete_yn (VARCHAR),
billing_address_id (NUMBER), delivery_address_id (NUMBER), payment_method_code (VARCHAR)`.

## STEP 2 — report built from MCP data

`scripts/mcp_pull_report.py` makes the three MCP calls (`list_schema_fields`, `get_lineage`,
`get_dataset_queries`) and feeds the results into the unchanged `autopilot.impact` +
`autopilot.report_html`:
- **Schema** → the target dataset's columns come from MCP `list_schema_fields` (15).
- **Downstream lineage** → the impacted-consumer assets come from MCP `get_lineage` (5 of the 17
  downstreams matched the seeded queries: `order_details`, `Customer_Analytics_Measures`,
  `Essential_KPI_Measures`, `Geographic_Measures`, `Time_Inteligence_Measures`).
- **Queries** → MCP `get_dataset_queries` returned 0, so the impact math uses the seeded query log
  against those real `orders` columns (the documented fallback).

Result for `drop order_entry.orders.promotion_id`: **breaks 3, degrades 1, safe 3, CRITICAL** →
`out/mcp_report.html` (self-contained; 0 external refs). Screenshot: `out/live_ui/05_mcp_report.png`
— header reads "catalog **showcase-ecommerce (real datapack, via MCP)**"; the lineage graph shows the
MCP-discovered `order_details` (snowflake) + PowerBI measures colored by verdict.

Reproduce:
```
pip install mcp-server-datahub          # the official DataHub MCP server
cd blast-radius-autopilot; set -a; . ./.env; set +a
DATAHUB_GMS_TOKEN=$DATAHUB_TOKEN python scripts/mcp_pull_report.py   # pulls via MCP -> out/mcp_report.html
```

---

## 2026-07-29 — Full end-to-end run THROUGH MCP on an auto-selected datapack table

Second, stronger MCP run. Difference from the 2026-07-25 run above: the target is **discovered over
MCP** rather than hardcoded, and the impact corpus is **real SQL read over MCP** rather than the
seeded query log.

### Step 0 — preflight
The DataHub stack had exited 44h earlier (status 255, Docker daemon restart); MySQL survived.
Restarted `opensearch → kafka → gms → frontend → actions`; GMS `/health` 200; existing `.env` token
still authenticates; `search(DATASET)` total = **78** (datapack intact).
`mcp-server-datahub` was **not installed on this machine** (the 07-25 install is gone) — reinstalled
**v0.6.0** into `~/bra/venv`.

`mcp-server-datahub` reports **`datahub 3.4.5`, `is_oss=True`, Mutation Tools ENABLED**, and exposes
**20 tools** (the earlier note of "8 tools" understated it):

```
search, get_lineage, get_dataset_queries, get_entities, list_schema_fields,
get_lineage_paths_between, search_documents, grep_documents,
add_tags, remove_tags, add_terms, remove_terms, add_owners, remove_owners,
set_domains, remove_domains, update_description,
add_structured_properties, remove_structured_properties, save_document
```

### Step 1 — target discovered over MCP, not hardcoded
`scripts/mcp_rank_tables.py`: MCP `search(query="*", filter="entity_type = dataset")` paginated
(50/page) → **78 datasets**; then MCP `get_lineage(upstream=False, max_hops=2)` on **all 78**
(41.4s, concurrency 6). Ranking top:

| downstreams | table |
|---|---|
| **24** | **ORDER_DETAILS** (snowflake, `order_entry_db.analytics.order_details`) |
| 17 | ADDRESSES, COUNTRIES, CUSTOMERS, INVENTORIES, ORDER_ITEMS, ORDERS, PRODUCTS, … |
| 15 | order_details (dbt) |

Chosen: **ORDER_DETAILS** — most connected (24), and the fan-out spans 6 platforms
(tableau 8, powerbi 6, looker 2, snowflake 2, dbt 1, 5 unresolved-platform). Full ranking:
`out/mcp_ranking.json`.

### Step 2 — MCP pull + counts + timing (`scripts/mcp_live_run.py`)

```
get_entities(urns=[target])                              -> 1 entity
list_schema_fields(urn=target)                           -> 55 fields
get_lineage(urn=target, upstream=False, max_hops=2)      -> total=24
get_dataset_queries(urn=target)                          -> total=0
get_entities(urns=[24 downstreams])                      -> 24 entities
```

**columns=55 · downstreams=24 · query history=0**

`TIMING  mcp_pull=11.46s  sqlglot_parse+impact=0.014s  total=11.48s`

Metadata-bound: the parse+impact step is **14 ms** over 55 columns and 6 SQL definitions, and does
not touch table data — so it is independent of how large `order_details` actually is.

### PROVENANCE — what was real, what was not
- MCP `get_dataset_queries` returned **total = 0**. The datapack ships **no query history**. Stated
  plainly: there is no real query-execution history behind this run, and none is implied.
- The impact corpus is instead **6 real SQL definitions** read over MCP from the downstreams'
  `viewProperties.logic` (source label `mcp:view_logic`):

  | platform | consumer | chars |
  |---|---|---|
  | dbt | order_history | 484 |
  | tableau | Custom SQL Query (Order Mode) | 243 |
  | tableau | Custom SQL Query (Top Product Category) | 280 |
  | tableau | Custom SQL Query (Promotions) | 349 |
  | tableau | Custom SQL Query (Orders By Day) | 276 |
  | snowflake | ORDER_DETAILS_REPLICA | 127 |

- **Seeded/synthetic SQL used: 0.** This run does not use `examples/showcase-ecommerce-live/`.
- **Only 6 of the 24 downstreams carry any SQL definition.** The other 18 (PowerBI measures, Looker
  views, unresolved-platform dashboards) expose no parseable SQL over MCP, so the parser cannot
  assess them. They are counted in lineage, absent from the impact corpus.
- `runs` is **1 per consumer** and `teams` is **0** — no execution counts or ownership came over MCP
  for these view definitions. The "3 impacted runs" tile is therefore a consumer count, not real
  execution volume.

### Step 3 — impact on a real column
Column also **discovered, not hardcoded**: most-referenced target column across the MCP-sourced SQL —
`category_name` (6 refs; then order_id 5, order_total 5, line_total 3, order_date 3).

`drop order_entry_db.analytics.order_details.category_name`
→ **breaks 3 · degrades 0 · safe 3 · ambiguous 0 · risk CRITICAL (62/100)**

```
BREAKS   Custom SQL Query (tableau)     select   high    group,select,where
BREAKS   Custom SQL Query (tableau)     select   high    group,select,where
BREAKS   ORDER_DETAILS_REPLICA          select   medium  select(*)      <- star handling
SAFE     order_history (dbt)            none     high    [PARSE FAILED - see caveat]
SAFE     Custom SQL Query (tableau)     none     high
SAFE     Custom SQL Query (tableau)     none     high
```

Artifacts: `out/mcp_live_report.html`, `out/mcp_live_report.json` (carries the full `provenance`
block), screenshot `out/live_ui/07_mcp_live_report.png`.

### Step 4 — second table, same code path (dataset-agnostic)
`ADDRESSES` (`order_entry_db.order_entry.addresses`), 9 columns, 17 downstreams, query history 0,
7 SQL defs over MCP. Auto-picked column `country_id` (4 refs).
→ **breaks 0 · degrades 0 · safe 7 · risk LOW**, `mcp_pull=8.91s  parse=0.009s`.
Artifacts: `out/mcp_live_addresses_report.{html,json}`.

**This LOW result is not trustworthy — see the caveat below.**

### CAVEAT (found by this run) — a SQL parse failure is reported as SAFE / high confidence
`lineage.py:177` returns `usage="none", confidence="low"` when sqlglot cannot parse a query.
`impact.py:78` then overwrites confidence back to `"high"` because `usage == "none"`, and
`_verdict_for("none")` returns **SAFE**. The failure survives only as a line in `report.notes`.

Consequence, concretely, on the ADDRESSES run: the dbt `order_details` model (5000 chars) is Jinja-
templated (`{{ source('order_entry','addresses') }}`, `{{ ref(...) }}`, `{% if %}`) so sqlglot raises
`ParseError`. That model **joins the addresses table and references `country_id` 4 times**. It was
nonetheless scored **SAFE, confidence high**, and it is the single most relevant consumer of
`addresses` — which is why that run reports risk **LOW**. That is a false negative.

The same defect is present but harmless in the ORDER_DETAILS run: dbt `order_history` also failed to
parse and was scored SAFE; it genuinely does not reference `category_name`, so the verdict is right
by luck rather than by analysis.

Not fixed here — `src/autopilot/` was off-limits for this run. Two candidate fixes: (a) map
`parse_error` to a distinct `UNKNOWN` verdict instead of SAFE and keep `confidence="low"`; and/or
(b) pre-render dbt Jinja in the adapter before handing SQL to the core.

### Reproduce
```
pip install mcp-server-datahub
cd blast-radius-autopilot; set -a; . ./.env; set +a
export DATAHUB_GMS_URL=http://localhost:8080 DATAHUB_GMS_TOKEN=$DATAHUB_TOKEN
python scripts/mcp_rank_tables.py                       # -> out/mcp_ranking.json (target discovery)
python scripts/mcp_live_run.py --slug mcp_live          # -> out/mcp_live_report.{html,json}
python scripts/mcp_live_run.py --slug mcp_live_addresses \
  --target-urn "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.addresses,PROD)"
```
Helper probes used while building: `scripts/mcp_probe.py` (tool list),
`scripts/mcp_shape.py` (raw response shapes), `scripts/mcp_sql_probe.py` (SQL discovery).
No core-logic files were modified. `.env` remains gitignored/local-only.

---

## 2026-07-30 — B15 re-run: the caveat above is now FIXED, and coverage is honest

The `CAVEAT` recorded on 2026-07-29 (a parse failure scored SAFE/high) has been fixed in the core.
Both live-MCP runs were repeated against the same datapack, same MCP server, same targets.

Two changes matter for reading these numbers:

1. **A parse failure is now `UNKNOWN`, not `SAFE`.** New fourth verdict; confidence stays `low`.
2. **The adapter no longer hides the no-SQL downstreams.** Previously `mcp_live_run.py` only built
   Catalog entries for downstreams that carried `viewProperties.logic`, so coverage read a flattering
   *"5 of 6 analysed"* when 18 of the 24 discovered consumers were absent from the report entirely.
   They are now registered as definition-less consumers → reported `UNKNOWN` → the honest
   **"5 of 24 analysed"**.

### ORDER_DETAILS — `drop order_entry_db.analytics.order_details.category_name`

MCP calls and counts unchanged: 55 columns · 24 downstreams · `get_dataset_queries` **total 0** ·
6 downstreams expose `viewProperties.logic` · 18 expose none.

| | before B15 | after B15 |
|---|---|---|
| BREAKS | 3 | **2** |
| DEGRADES | 0 | **1** |
| SAFE | 3 | **2** |
| UNKNOWN | *(state did not exist)* | **19** |
| risk | `CRITICAL (62/100)` | **`HIGH among assessed (50/100)`** |
| coverage | *(not reported)* | **`5 of 24 analysed`** |
| review_required | *(not reported)* | **`True`** |

Two reclassifications, both intended:
- `ORDER_DETAILS_REPLICA` — `CREATE OR REPLACE VIEW ... AS SELECT * FROM order_details` —
  BREAKS → **DEGRADES** (`usage=star`). A `SELECT *` view genuinely still executes after a column
  drop; its output silently loses a field. That is behaviour change, not failure.
- dbt `order_history` (unrendered Jinja) — SAFE → **UNKNOWN** (`usage=parse_error`).

**The CRITICAL → HIGH move is a de-escalation, and it is deliberate.** It comes entirely from the
star reclassification (3 breaks → 2 breaks + 1 degrades), *not* from unknowns diluting the score —
unknowns are excluded from the score by construction. The run is nonetheless now gated
(`REVIEW REQUIRED`) where before it was not, and its denominator is visible where before it was not.

### ADDRESSES — `drop order_entry_db.order_entry.addresses.country_id`

9 columns · 17 downstreams · `get_dataset_queries` **total 0** · 7 expose SQL · 10 expose none.

| | before B15 | after B15 |
|---|---|---|
| dbt `order_details` (references `country_id` 4×) | **`SAFE` / confidence `high`** | **`UNKNOWN` / `low` / `usage=parse_error`** |
| SAFE count | 7 | **5** |
| UNKNOWN | *(state did not exist)* | **12** |
| risk | `LOW` (unqualified) | **`LOW among assessed`** |
| coverage | *(not reported)* | **`5 of 17 analysed`** |
| review_required | *(not reported)* | **`True`** |
| write-back | would auto-apply | **0 auto / 4 queued** |

**Stated honestly: the level string is still "LOW", and that is correct.** The 5 consumers that can
be analysed genuinely do not reference `country_id`; promoting them to a break would be inventing
evidence, the mirror-image of the original defect. What changed is that the LOW is now *qualified*
("among assessed"), *gated* (review required, writes queued), and *bounded* (5 of 17) — so it can no
longer be mistaken for a clean bill of health, which is exactly what it was on 2026-07-29.

Artifacts: `out/mcp_live_report.{html,json}`, `out/mcp_live_addresses_report.{html,json}`,
screenshots `out/live_ui/08_b15_mcp_live_report.png`, `out/live_ui/09_b15_addresses_review_required.png`.
Both JSON reports carry `coverage`, `review_required`, and a `provenance` block recording
`downstreams_discovered` / `downstreams_with_analysable_sql` / `downstreams_without_sql_definition`.

Offline suite at the time of this run: **73 passed** (was 45). `.env` remains gitignored/local-only;
public/synthetic data only.

---

## 2026-08-03 — B20 live re-run: both MCP targets re-verified against the CURRENT build

**Why this run exists.** Every MCP capture before today predates the verification gates
(B16–B19) and the approval audit (B20.3). The `--verify` verdict on the live MCP target had
been carried in the docs as *reasoning* — "the B17 gates can only tighten a verdict, so the
captured FAIL cannot have become a PASS" — and never as a captured run, because the Docker
daemon was down for the B17/B18/B19 sessions. It is up now, so the artifacts are captured
rather than argued.

### STEP 0 — preflight, as measured

| Check | Result |
|---|---|
| GMS `localhost:8080/health` | **200** |
| Frontend `localhost:9002` | **200** |
| Containers | 5 up, healthy (gms, frontend, kafka, mysql, opensearch) |
| `datahub-actions` | **NOT running** — not required for the reads/writes here, recorded rather than hidden |
| `.env` token | **200** against `/openapi/v3/entity/dataset` |
| Datapack | **78 datasets**, 6 dashboards, 16 charts — still loaded |
| `QUERY` entities in the instance | **0** |
| `mcp-server-datahub` | **0.6.0**, already installed (no reinstall needed) |
| MCP server self-report | `datahub 3.4.5`, `is_oss=True`, **20 tools** |
| GMS version | `v1.5.0.6` (quickstart) |

The 20 tools, verbatim from `list_tools()`: `search`, `get_lineage`, `get_dataset_queries`,
`get_entities`, `list_schema_fields`, `get_lineage_paths_between`, `search_documents`,
`grep_documents`, `add_tags`, `remove_tags`, `add_terms`, `remove_terms`, `add_owners`,
`remove_owners`, `set_domains`, `remove_domains`, `update_description`,
`add_structured_properties`, `remove_structured_properties`, `save_document`.
(The 2026-07-25 note saying "8 tools" undercounted: it listed only the read tools.)

### STEP 1 — both targets, exact MCP returns

**ORDER_DETAILS** — `drop order_entry_db.analytics.order_details.category_name`
(target auto-selected from the MCP ranking, 24 downstreams)

```
get_entities(urns=[target])                            -> 1 entity
list_schema_fields(urn=target)                         -> 55 fields
get_lineage(urn=target, upstream=False, max_hops=2)    -> total=24
get_dataset_queries(urn=target)                        -> total=0
get_entities(urns=[24 downstreams])                    -> 24 entities
```

**ADDRESSES** — `drop order_entry_db.order_entry.addresses.country_id`

```
get_entities(urns=[target])                            -> 1 entity
list_schema_fields(urn=target)                         -> 9 fields
get_lineage(urn=target, upstream=False, max_hops=2)    -> total=17
get_dataset_queries(urn=target)                        -> total=0
get_entities(urns=[17 downstreams])                    -> 17 entities
```

**`get_dataset_queries` returned 0 on both targets.** The datapack ships **no query history**,
and none is implied. The corpus actually analysed is **real SQL read over MCP** from each
downstream's `viewProperties.logic`. **Seeded/synthetic SQL used: 0.**

| | ORDER_DETAILS | ADDRESSES |
|---|---:|---:|
| columns (`list_schema_fields`) | 55 | 9 |
| downstreams (`get_lineage`) | 24 | 17 |
| **query history (`get_dataset_queries`)** | **0** | **0** |
| real SQL definitions used (`mcp:view_logic`) | **6** | **7** |
| downstreams exposing no SQL at all | 18 | 10 |
| coverage | **5 of 24 analysed** | **5 of 17 analysed** |
| breaks / degrades / safe / UNKNOWN | 2 / 1 / 2 / **19** | 0 / 0 / 5 / **12** |
| risk | **HIGH among assessed (50/100)** | **LOW among assessed (0/100)** |
| `review_required` | **True** | **True** |
| **`--verify` verdict** | **FAIL** | **FAIL** |
| MCP pull | **10.47 s** | **9.05 s** |
| sqlglot parse + impact | **0.010 s** | **0.009 s** |

Parse is ~10 ms and touches no table data, so the run is metadata-bound regardless of how
large the underlying tables are.

**The impact numbers are byte-identical to the B15 capture** (ORDER_DETAILS 2/1/2/19,
`HIGH among assessed (50)`, 5 of 24; ADDRESSES 0/0/5/12, `LOW among assessed`, 5 of 17). The
B15 semantics fix has held across four subsequent rounds. `order_history` (dbt, Jinja) still
fails to parse and is still reported **UNKNOWN / low / `usage=parse_error`**, never SAFE — the
defect B15 fixed has not regressed.

**What is new is the verdict detail.** The pre-B17 capture recorded `FAIL` with a single
reason. Today, with the full sixteen-clause conjunction, ORDER_DETAILS fails on **six** named
reasons:

```
B16  VERDICT FAIL
     breaks 2 -> 2 (+0)  degrades 1 -> 1  unassessed 19 -> 19  ambiguous 0 -> 0
     coverage 5 of 24 analysed      patched files recomputed: 3 of 3
     - breaks_not_reduced
     - breaks_remaining
     - degrades_remaining
     - unknown_consumers_present
     - coverage_incomplete
     - fix_incomplete_column_still_referenced
```

Both Tableau consumers use `category_name` in `WHERE` + `GROUP BY`, which the fix generator
deliberately never auto-rewrites, so the 3 generated fixes cannot reduce the break count. The
previously-*reasoned* claim ("cannot have become a PASS") is now a **captured run**.

**ADDRESSES fails for a different reason, and it is worth being precise about:**
`no_patch_provided`. There are 0 breaks among the 5 analysable consumers, so `fixgen` produces
no patch, so there is nothing to verify. See *Limitation* below.

Artifacts: `out/mcp_live_report.{html,json}`, `out/mcp_live_addresses_report.{html,json}`,
`out/mcp_live_VERIFICATION.md`, `out/mcp_live_addresses_VERIFICATION.md`, full run logs
`out/b20_mcp_live_run.txt` + `out/b20_mcp_live_addresses_run.txt`, screenshots
`out/live_ui/17_b20_mcp_live_order_details_*.png` + `18_b20_mcp_live_addresses_*.png`
(the capture script fails unless the coverage denominator and REVIEW-REQUIRED state are
actually on the rendered page). Both JSON reports carry the `provenance` block:
`read_path="mcp-server-datahub 0.6.0 over stdio"`, `mcp_query_history_total=0`,
`seeded_queries_used=0`.

### STEP 2 — the live write path, end to end

The B19 rule was confirmed against the live instance rather than in a fixture. With `--write`
**given** and the verdict REVIEW_REQUIRED, **nothing was written**:

```
gate: verification REVIEW_REQUIRED — every mutation queued for a human.
Approval manifest -> out/APPROVAL-drop-analytics-fct-orders-customer-zip.json
Summary: 0 planned, 0 written (auto), 0 written (human-approved), 8 queued, 0 failed, 0 skipped.
  queued because: verification_review_required+unresolved_impact
```

Then the human-approval route:

```
APPROVED by reviewer@example.com — manifest f374130bcb5ce6f1 (8 mutation(s), verification REVIEW_REQUIRED)
Summary: 0 planned, 0 written (auto), 8 written (human-approved by reviewer@example.com), 0 queued, 0 failed, 0 skipped.
  Approval audit recorded in the catalog: approved_by=reviewer@example.com,
  at=2026-08-03T10:12:33+00:00, manifest=f374130bcb5ce6f1,
  verification_at_approval=REVIEW_REQUIRED, writes=8, failures=0
  manifest f374130bcb5ce6f1 consumed — approvals are single-use
```

**Independent GraphQL read-back — 26 assertions, ALL PASS**
(`scripts/b20_live_full_readback.py`, captured in `out/b20_live_full_readback.txt`). 24
structured properties on the asset; the six B20.3 audit fields:

| Property | Read back from DataHub |
|---|---|
| `blast_radius_approved_by` | `reviewer@example.com` |
| `blast_radius_approved_at` | `2026-08-03T10:12:33+00:00` |
| `blast_radius_manifest_id` | `f374130bcb5ce6f1` |
| `blast_radius_verification_status_at_approval` | `REVIEW_REQUIRED` |
| `blast_radius_approved_writes` | `8` |
| `blast_radius_approved_failures` | `0` |

plus the assessment (`status=pending-change`, `risk=CRITICAL`, `breaks=6`,
`coverage=10 of 10 analysed`, `verification_status=REVIEW_REQUIRED`), the
`pending-schema-change` tag, an institutional-memory **link whose target file exists**, the
`⚠️` description footer, and all four impacted downstreams carrying
`impacted-by-upstream-change` + `impact-breaks`. UI: `out/live_ui/16_b20_3_approval_audit_viewport.png`.

### Findings from this run — reported, not fixed (no feature work this session)

1. **The real-datapack flagship cannot reach the approval path at all.**
   `examples/showcase-ecommerce-live` / `drop order_entry.orders.promotion_id` verifies
   **FAIL / `no_patch_provided`**, because **all four** of its breaking consumers are a
   Snowflake view, two PowerBI reports and an ad-hoc query — **zero dbt models**, so `fixgen`
   generates nothing. FAIL means no manifest and no approval by any route, so on the real
   datapack target there is *no* way to record the assessment today. The synthetic
   `examples/showcase-ecommerce` flagship reaches REVIEW_REQUIRED only because it has one dbt
   consumer (`rpt_orders_by_region`). Captured: `out/b20_live_flagship_verify.txt`.
2. **`no_patch_provided` → FAIL is arguably mis-calibrated**, and it is the same finding on
   ADDRESSES. "There was no fix to check" is not the same as "the fix is broken", and FAIL is
   the one verdict a human can never approve — so a target needing no mechanical fix can never
   have its assessment recorded. REVIEW_REQUIRED would fit the meaning better. Fail-closed, so
   not dangerous, and **left alone** because this session is run-and-record.
3. **The real datapack `orders` asset still carries stale marks from the 2026-07-25 pre-B19
   auto-write**: `blast_radius_assessed_at = 2026-07-25T12:47:07`, `breaks=3`, `degrades=1`
   (pre-B15 semantics — current analysis says breaks 4 / degrades 0), 7 properties only. That
   write could not happen today. The demo script has been corrected accordingly.
4. **Write-back is additive, so verdict tags accumulate across semantics changes.**
   `Revenue by State` now carries **both** `impact-degrades` (from a pre-B15 run, when
   filter-only references were DEGRADES) **and** `impact-breaks` (current). `_add_tags` never
   removes, by design. On camera this reads as a contradiction.
5. **Institutional-memory links accumulate when the URL changes.** `_save_document` is
   idempotent *by url*, so the pre-B18 placeholder
   `https://blast-radius-autopilot.local/assessment` still sits beside the current
   `file://…/out/ASSESSMENT-….md`. Two links, same title, on the same asset.

Findings 3–5 are all the same shape: **an additive write-back against a catalog that holds
older writes.** None is a false PASS, and none was introduced by B20.3.

Offline suite at the time of this run: **181 passed**. `.env` remains gitignored/local-only;
public/synthetic (official `showcase-ecommerce` datapack) data only.
