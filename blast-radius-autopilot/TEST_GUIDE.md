# Blast Radius Autopilot — UI Test Guide

Everything below is loaded into your local DataHub and verified by GraphQL read-back
(2026-07-25). Browse and test it yourself. Public/synthetic sample data only.

## Log in
- Open **http://localhost:9002** → username **datahub**, password **datahub**.
- Catalog contents: **78 datasets**, 4 dashboards, 14 charts, 23 data flows/jobs
  (DataHub's official `showcase-ecommerce` datapack + 4 synthetic example scenarios).

Tip: the agent's marks are three tags — `pending-schema-change` (on the changed table),
`impacted-by-upstream-change` + `impact-breaks`/`impact-degrades` (on downstreams) — plus
7 `Blast Radius *` structured properties and a "Blast Radius Assessment" doc link.

---

## 1. FLAGSHIP — real datapack (the star of the demo)
**Search:** `orders` → open the **Dataset "orders"** (Snowflake, `order_entry_db › order_entry`,
has a "View in Snowflake" button, 15 columns).
- **Documentation** (right panel): "⚠️ drop order_entry.orders.promotion_id **breaks 3 and
  degrades 1** … Change risk: **CRITICAL (100/100)**" + a **Blast Radius Assessment** doc link.
- **Tags:** `pending-schema-change` (alongside the datapack's own Large Table / Most Queried).
- **Properties tab (19):** the 7 `Blast Radius *` rows — Status=pending-change, Risk=CRITICAL,
  Score=100, Breaks=3, Degrades=1, Teams=2, Assessed At.
- **Downstream to check — search `order_details`** (Snowflake analytics model, **55 columns**,
  full SQL view definition): Tags **`impacted-by-upstream-change` + `impact-breaks`**.
- Also `Essential_KPI_Measures` (PowerBI): Tags `impacted-by-upstream-change` + `impact-degrades`.

## 2. nyc-taxi (operational time-series) — drop `trips.trip_distance`
**Search:** `trips` → Dataset "trips" (Snowflake, 8 columns).
- Tags: `pending-schema-change`; Properties: 7 `Blast Radius *` (Breaks=2, Degrades=1, CRITICAL);
  Documentation: Blast Radius Assessment.
- Downstream — search `rpt_trip_metrics` (dbt): Tags `impacted-by-upstream-change` + `impact-breaks`.

## 3. fiction-retail (clean canvas) — drop `customers.loyalty_tier`
**Search:** `customers` → open the **retail** one (Dataset "customers", Snowflake, 6 columns —
not the datapack's order_entry customers).
- Tags: `pending-schema-change`; Properties: 7 `Blast Radius *` (Breaks=2, Degrades=1, CRITICAL);
  Documentation: Blast Radius Assessment.
- Downstream — search `rpt_loyalty` (dbt): Tags `impacted-by-upstream-change` + `impact-breaks`.

## 4. healthcare (SYNTHETIC, REVIEW-GATED) — rename `encounters.diagnosis_code` → `icd10_code`
**Search:** `encounters` → Dataset "encounters" (Snowflake, 6 columns) — **browsable**.
- **Expected:** *no* `pending-schema-change` tag and *no* Blast Radius properties. This is correct:
  the catalog is `require_review` (regulated), so the agent **queued** the write-back for a human
  (6 mutations queued, 0 written) instead of auto-applying. To see the queue, re-run:
  `python scripts/emit_example.py examples/healthcare/catalog.json --change "rename clinical.encounters.diagnosis_code icd10_code" --write`
  → prints `written=0 queued=6`.

## 5. finance (SYNTHETIC, SOX REVIEW-GATED) — rename `fct_revenue.revenue_usd` → `net_revenue_usd`
**Search:** `fct_revenue` → Dataset "fct_revenue" (Snowflake, 5 columns) — **browsable**.
- **Expected:** review-gated, same as healthcare — write-back **queued** (7 queued, 0 written), no
  auto-applied tags. Re-run the emit script with `--write` to see `written=0 queued=7`.

---

## Search the agent's marks directly
- Tags page / search: **`pending-schema-change`** → the 3 changed tables (orders, trips, customers).
- **`impact-breaks`** → the breaking downstreams (order_details, rpt_trip_metrics, rpt_loyalty, …).
- **`impact-degrades`** → the degrading consumers (Essential_KPI_Measures, …).

## Who is allowed to write (B19 — read this before re-running with `--write`)

`--write` on its own no longer writes. Since B19.3 an automatic write requires a static
verification that returned **PASS** for that exact change; absence of evidence is not
permission. The four cases:

| What you ran | What happens |
|---|---|
| `--write` with no `--verify` | **nothing is written.** Every mutation queues, `queued because: not_verified` |
| `--verify --write`, verdict **PASS** | written automatically, reported as `written (auto)` |
| `--verify --write`, verdict **REVIEW_REQUIRED** | queued, and an **approval manifest** is written to `out/APPROVAL-<change>.json` (+ a `.md` you can read) |
| `--verify --write`, verdict **FAIL** | queued. **No manifest is written, and no approval can ever apply it.** |

So a re-run against a live instance is a two-step for anything that is not a PASS:

```bash
# 1. verify — this writes nothing and produces the manifest
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" --verify --write

# 2. read out/APPROVAL-drop-analytics-fct-orders-customer-zip.md, then approve it
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" --verify \
          --approve out/APPROVAL-drop-analytics-fct-orders-customer-zip.json \
          --approver you@example.com --write
```

Three things to know before you try it:

- **The manifest is single-use.** A successful approval burns it (`consumed_at` + `approver`
  are written back into the file). Re-approving is refused with `already_consumed`; generate a
  fresh one by re-running step 1.
- **The manifest is bound.** If the change, the verdict, or the queued mutation set has moved
  since it was written, approval is refused with `manifest_stale`. Editing the file by hand
  also fails this check.
- **The approver is never inferred.** Pass `--approver`, or set `BRA_APPROVER`. Without one:
  `no_approver`, and nothing is applied.

### What you see in DataHub afterwards (B20.3)

Open the changed dataset → **Properties**. A human-approved write adds six properties that
an automatic write does not have at all — that absence is how the two paths stay
distinguishable in the catalog:

| Property (DataHub shows the display name) | Example |
|---|---|
| Blast Radius Approved By | `reviewer@example.com` |
| Blast Radius Approved At | `2026-07-31T22:49:11+00:00` |
| Blast Radius Manifest Id | `bfb4e6b0be235a6f` |
| Blast Radius Verification Status At Approval | `REVIEW_REQUIRED` |
| Blast Radius Approved Writes | `8` |
| Blast Radius Approved Failures | `0` |

Reproduce the whole loop against a live instance. Two ways, both verified 2026-08-04:

```bash
# 1. self-contained: emits the datasets, verifies, approves, reads back (15 assertions)
set -a && . ./.env && set +a && python scripts/b20_3_live_readback.py

# 2. via the CLI, the way the demo does it — then read back EVERYTHING (26 assertions:
#    properties + the six audit fields + tags + the institutional-memory link + the
#    description footer + every impacted downstream's tags)
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" --verify --write
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" --verify \
          --approve out/APPROVAL-drop-analytics-fct-orders-customer-zip.json \
          --approver you@example.com --write
python scripts/b20_live_full_readback.py --approver you@example.com \
       --manifest-id <the id printed above> --expect-writes 8
```

Both end in `ALL ASSERTIONS PASS`. `python scripts/b20_3_capture_audit_ui.py` screenshots the
Properties tab and **fails** if the audit is not actually on the rendered page.

Two other guards worth running before you trust the docs:

```bash
python scripts/check_referenced_paths.py   # every artifact the docs cite must exist
python scripts/test_E_incomplete_fix.py    # the incomplete-fix path names its file:line
```

> **Correction to an earlier claim.** This guide previously said the catalog carried
> `Blast Radius Writeback Applied By` / `Writeback Approver` / `Approval Manifest Id`. It did
> not. Those `blast_radius_writeback_*` keys exist only in the assessment returned to the CLI
> and the reports — the copy *emitted* to the catalog is deliberately built without write-back
> context (a document cannot report the outcome of the write that saves it). B20.3 is what
> actually puts the approval trail in the graph, under the six names above; a test asserts the
> write-back family stays report-only so the claim cannot drift back.

## Re-run / reset
- **Note:** the read-back items documented above were written on 2026-07-25, before the B19
  gate landed. Re-applying them now takes the two-step route above (or `--verify` to a PASS).
- Re-apply the flagship:
  `autopilot --catalog examples/showcase-ecommerce-live/catalog.json --change "drop order_entry.orders.promotion_id" --verify --write`
  → then approve the manifest it prints, if the verdict is REVIEW_REQUIRED.
- The four examples via `scripts/emit_example.py <catalog> --change "…" --write`.
- Full read-back proof of all items: see `LIVE_DATAHUB_EVIDENCE.md`.
- UI screenshots of the flagship: `out/live_ui/`; verdict screenshots: `out/live_ui/13_*`, `14_*`.
