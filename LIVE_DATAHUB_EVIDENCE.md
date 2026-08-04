# Live DataHub evidence — verified on the REAL showcase-ecommerce datapack (2026-07-25)

The agent was run against DataHub's **official `showcase-ecommerce` datapack** (loaded via
`datahub datapack load showcase-ecommerce` — a verified pack, 1049 entities across Snowflake /
Looker / PowerBI / Tableau with real lineage + governance), not the earlier hand-seeded catalog.
Proven by an independent GraphQL read-back + UI screenshots. Official sample data only.

Reproduce:
```
cd blast-radius-autopilot; set -a; . ./.env; set +a
datahub datapack load showcase-ecommerce
autopilot --catalog examples/showcase-ecommerce-live/catalog.json \
          --change "drop order_entry.orders.promotion_id" --write
python scripts/capture_ui.py            # screenshots -> out/live_ui/
```

## Target + query history

- **Target asset (REAL datapack):** `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.orders,PROD)`
  — 15 real columns (order_id, customer_id, order_total, promotion_id, warehouse_id, …), real
  owners (Ian Chen, Data Platform Team), Domain, Data Product, and the datapack's own tags
  (Large Table, Most Queried).
- **Query history:** the datapack ships **none** — verified `QUERY` entities = 0 and
  `usageStats.topSqlQueries` = 0 (the `dataset.queries` GraphQL field also errors on this GMS
  build). Per the SETUP/BUILD_GUIDE fallback, a realistic query log was seeded against the REAL
  `orders` columns (`examples/showcase-ecommerce-live/query_log.json`). **Schemas and downstream
  assets are the datapack's real ones**, not stubs.

## Independent GraphQL read-back (the proof)

Change: `drop order_entry.orders.promotion_id` → `{breaks: 3, degrades: 1, safe: 3}`, risk CRITICAL.

`orders` (real datapack asset) after write-back:
```
real columns retained: 15   (proves it's the real asset; write-back is additive)
TAGS: ['b2fd91.__default_large_table', 'b2fd91.__default_high_queries', 'pending-schema-change']
DESCRIPTION FOOTER: "⚠️ drop order_entry.orders.promotion_id breaks 3 and degrades 1 downstream
  consumer(s) across 2 team(s) (analytics-eng, marketing-bi), spanning 48 query runs..."
STRUCTURED PROPERTIES (7): status=pending-change, risk=CRITICAL, score=100, breaks=3, degrades=1,
  teams=2, assessed_at=2026-07-24T21:32:56+00:00
INSTITUTIONAL MEMORY: ['Blast Radius Assessment — drop order_entry.orders.promotion_id']
```

Real downstreams (NOT stubs):
```
order_details (snowflake analytics model): 55 real columns  | tags: impacted-by-upstream-change, impact-breaks
Essential_KPI_Measures (powerbi):          12 real columns  | tags: impacted-by-upstream-change, impact-degrades
```

All 10 assertions PASS (orders retains 15 real cols; tag + footer + 7 props + assessment doc on the
real target; order_details 55 cols + impact tags; KPI 12 cols + degrade tag).

## UI screenshots (for the demo video) — `out/live_ui/`
- `01_orders_overview.png` — real `orders` (15 cols w/ descriptions + PII terms, real owners) with
  our Documentation footer (CRITICAL), the Blast Radius Assessment link, and `pending-schema-change`.
- `02_orders_properties.png` — Properties tab with the 7 `Blast Radius *` structured properties.
- `03_orders_documentation.png` — Documentation tab.
- `04_downstream_order_details.png` — the real `order_details` model (55 cols, full SQL view
  definition, many owners, SOC2/GDPR terms) carrying `impacted-by-upstream-change` + `impact-breaks`.

## Notes / issues hit (and resolved)
- `datahub datapack --help` crashes (wheel ships an empty `resources/` dir, missing
  `DATAPACK_AGENT_CONTEXT.md`); `datapack load` itself works (resolves the registry from GitHub).
- UI capture initially grabbed loading skeletons on the heavy real pages; fixed by waiting on
  page-specific real content (`order_total`, `Blast Radius`, `impacted-by-upstream-change`) before
  screenshotting, then re-captured.
- The earlier hand-seeded `analytics.fct_orders` demo assets also remain in the catalog from prior
  runs; this run targets the datapack's real `b2fd91.*` assets.
