# Approval required — `drop analytics.fct_orders.customer_zip`

**Manifest** `f374130bcb5ce6f1` · created 2026-08-03T10:12:26+00:00

**Static verification:** REVIEW_REQUIRED — `breaks_remaining`, `ambiguous_consumers_present`, `manual_work_remaining`

Approving this applies **exactly these 8 mutation(s)**, and nothing else:

| Tool | Target | Would write |
|---|---|---|
| `add_structured_properties` | `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.fct_orders,PROD)` | 18 structured properties: blast_radius_ambiguous=1, blast_radius_breaks=6, blast_radius_coverage=10 of 10 analysed, blast_radius_degrades=0, blast_radius_review_required=True, blast_radius_risk=CRITICAL … |
| `add_tags` | `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.fct_orders,PROD)` | tags: pending-schema-change |
| `save_document` | `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.fct_orders,PROD)` | institutional-memory link -> file:///Users/adeel.tahir/bra/blast-radius-autopilot/out/ASSESSMENT-drop-analytics-fct-orders-customer-zip.md |
| `update_description` | `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.fct_orders,PROD)` | append footer: ⚠️ drop analytics.fct_orders.customer_zip breaks 6 and degrades 0 downstream consumer(s) across 3 team(s) (analytics-eng, growth-analytics, marketing-bi), spann |
| `add_tags` | `urn:li:dashboard:(looker,sales_by_zip)` | tags: impacted-by-upstream-change, impact-breaks |
| `add_tags` | `urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.rpt_orders_by_region,PROD)` | tags: impacted-by-upstream-change, impact-breaks |
| `add_tags` | `urn:li:chart:(powerbi,zip_heatmap)` | tags: impacted-by-upstream-change, impact-breaks |
| `add_tags` | `urn:li:chart:(powerbi,revenue_by_state)` | tags: impacted-by-upstream-change, impact-breaks |

> Static verification returned REVIEW_REQUIRED. Approving this manifest applies exactly the mutations listed above and nothing else. It is single-use and is bound to this change, this verdict and this queue. No query was executed to produce it. Approving also RECORDS THE APPROVER — your identity, the approval time, this manifest id, the verdict you approved against, and how many writes succeeded or failed — as structured properties on the changed dataset in DataHub, where anyone with access to the catalog can read them.

**What approving records about you** (structured properties on the changed dataset):

| Property | Value |
|---|---|
| `blast_radius_approved_by` | the `--approver` you pass — never inferred |
| `blast_radius_approved_at` | when you approved |
| `blast_radius_manifest_id` | `f374130bcb5ce6f1` |
| `blast_radius_verification_status_at_approval` | `REVIEW_REQUIRED` |
| `blast_radius_approved_writes` | how many of the mutations above landed |
| `blast_radius_approved_failures` | how many were attempted and failed |

Apply with:

```bash
autopilot --catalog <same catalog> --change "<same change>" --verify \
          --approve <this file> --approver you@example.com --write
```
