# Known limitations

Deliberate, documented scope boundaries — not oversights. Each item below is a residual
risk we identified, decided not to close in this build, and are stating plainly rather
than leaving for a reader to discover. Where a production version would need more, we say
what it would need.

The project's guiding rule is that **missing evidence must never be presented as proof of
safety**. This file applies that rule to the tool itself.

---

## 1. What static verification does and does not prove

**Proves:** the generated patch applies cleanly in an isolated copy, every patched `.sql`
file re-parses, the diff stayed within its declared scope, and the impact analyzer can no
longer find a broken or unassessed consumer.

**Does not prove:** that anything ran. No query is executed, no warehouse or database is
contacted, no data is read, no dbt build is invoked. It is evidence about SQL *text*, not
about runtime behaviour, row counts, results, or performance. A verdict of `PASS` means
"no remaining evidence of breakage in the text we could read," never "tested."

## 2. Analysis coverage is bounded by what the catalog exposes

Impact is computed from query history and downstream SQL definitions. Consumers that
expose no parseable SQL — PowerBI measures, Looker views, dashboards — cannot be assessed
by a SQL parser and are carried as `UNKNOWN`, never as `SAFE`. On the live
`showcase-ecommerce` datapack run, only **6 of 24** downstream consumers exposed analysable
SQL; the other 18 were reported as unassessed. Coverage is always reported as its own
dimension (e.g. "CRITICAL among assessed · 6 of 24 analysed") and any `UNKNOWN` blocks
`PASS`.

The sample datapack also ships **no query history** (`get_dataset_queries` returns 0), so
the corpus for those runs is the real SQL definitions read over MCP. Where a supplied query
log is used instead, it is labelled as such.

## 3. Fix generation is mechanical and narrow

`fixgen` handles column **drop** and **rename** in dbt models only. It deliberately never
auto-rewrites `WHERE` / `JOIN` / `GROUP BY` logic, and it cannot fix non-dbt consumers
(BI tools, ad-hoc queries) — those are surfaced as manual-review steps. In practice this
means most real changes land as `REVIEW_REQUIRED` rather than `PASS`, which is the honest
outcome, not a failure of the tool.

## 4. Ambiguous column attribution is not resolved

An unqualified column present on more than one joined table cannot be attributed with
confidence. Such references are gated to low confidence, never counted as a definite break
and never counted as safe, and they block `PASS`. The tool does not perform full
scope/alias resolution to disambiguate them; a production version would need proper
name-resolution against each source schema.

## 5. Approval manifests: binding is partial

The approval manifest is fingerprint-bound to the change, the verdict and the queued set,
it is single-use, and a `FAIL` can never be approved. Two gaps remain:

- **The fingerprint does not cover the complete canonical payload.** It binds the change and
  the queued set, but a sufficiently determined edit to a mutation's payload body after the
  manifest is written is not guaranteed to be detected. Consequently **what a reviewer reads
  in the manifest is not cryptographically guaranteed to be byte-identical to what
  executes.**
- **Mutation IDs are not globally unique.** Two mutations that collide on identity (same
  tool and target, differing payload) can, in principle, resolve to the wrong payload at
  apply time.

A production version would hash the full canonical payload (tool + URN + every displayed
field + verification artifact + patch hash) into each mutation's ID, and re-hash and compare
immediately before each write.

## 6. Partial failure consumes the approval

If some mutations succeed and others fail mid-apply, the manifest is consumed as a whole.
There is no per-mutation receipt ledger and no automatically generated retry manifest
covering only the failed remainder, so retrying requires re-running the assessment and
re-approving. Write-back counters remain truthful about what was written versus failed —
the gap is in resumability, not in reporting.

## 7. Single-operator assumption: no locking, no atomicity, no idempotency

The approval path assumes one operator running one apply at a time. There is:

- **no file locking or atomic state transition** on the manifest, so two concurrent
  approvals of the same manifest could both proceed;
- **no crash-safe journalling**, so a process killed mid-apply may leave mutations applied
  without the manifest being marked consumed — a subsequent approval could replay them;
- **no idempotency keys** on the DataHub side, so a replayed mutation is a second write
  rather than a no-op.

A production version would need an atomic state machine over the manifest (e.g.
`PENDING → CLAIMED → APPLIED/PARTIAL`), an exclusive lock around claim-and-apply, and
idempotency keys carried into the catalog writes.

## 8. What lands in DataHub, exactly

`InstitutionalMemoryMetadata` on open-source DataHub is `{url, description, createStamp,
updateStamp, settings}` — it has no field that can hold a document body. So the catalog
stores: the `blast_radius_*` structured properties, the `pending-schema-change` /
`impacted-by-upstream-change` tags, a one-line pending-change footer on the editable
description, the human-approval audit properties, and an institutional-memory **link**
(url + title). The full Impact Assessment markdown is persisted to a file, and that link
points at it. DataHub Cloud has a real document API; this build does not use it and does
not claim to.

## 9. Scale characteristics are argued, not benchmarked

The tool reads metadata only — schemas, lineage, query text, ownership — and never reads
table data, so its cost is independent of the underlying dataset size (a 6 TB table and a
6 MB table look identical to it). Observed on the live run: MCP pull ~11.5 s, parse + impact
~14 ms. It has **not** been benchmarked against enterprise-scale query history or lineage
fan-out; at that scale, query pagination, parse caching, and deduplication would matter.

---

*All examples and demo data in this repository are public or synthetic. No real,
production, or company data is included.*
