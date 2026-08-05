# Blast Radius Autopilot

> **DataHub's Impact Analysis shows you the blast radius of a schema change. Blast Radius Autopilot _defuses_ it** — it computes evidence-backed column-level impact from available query history and downstream SQL definitions, while explicitly reporting unparseable, ambiguous, and non-SQL consumers, writes the migration code to fix what it can prove, **statically verifies its own patch**, generates an applicable patch and a CI-ready PR comment, and records the impact assessment back in the catalog.

**On coverage and confidence — two separate axes.** Every consumer lands in one of four
states: `BREAKS` (a reference resolves to the column), `DEGRADES` (still runs, output
changes), `SAFE` (parsed and provably untouched), `UNKNOWN` (could not be assessed —
unparseable SQL, or no SQL definition at all). A fifth signal cuts across them:
**ambiguous** — the SQL parsed and the column was found, but it cannot be attributed to a
source table (an unqualified column that more than one joined table provides).

UNKNOWN and ambiguous are deliberately different states. UNKNOWN means we could not read
the consumer; ambiguous means we read it and could not attribute the reference. Neither
ever counts as safe, neither is inflated into a break, neither moves the risk score — and
**either one forces the run to REVIEW REQUIRED with every catalog write queued for a
human.** Coverage is reported as its own dimension — *"HIGH among assessed · 5 of 24
analysed"*, or *"CRITICAL with 1 unresolved reference(s)"* when nothing went unread but
something went unattributed — because a confident verdict over a thin slice of consumers
must never masquerade as a confident verdict over all of them.

Viewing downstream lineage is shipped. *Autonomously deriving column-level impact from real queries, generating the migration fix, and writing a durable impact assessment back to DataHub* is not. That's the gap this fills.

**Category:** Metadata-Aware Code Generation (primary) + Agents That Do Real Work — it reads DataHub for real schemas/lineage/queries, acts (generates the fix + PR), and contributes back (assessment + status).

---

## What it does

Given a proposed change — *"drop `customer_zip` from `fct_orders`"* — the agent:

1. **Gathers** (DataHub reads / MCP): schema + ownership, downstream lineage, and the **real SQL** that touches the table (`get_dataset_queries`, downstream `viewProperties.logic`, or a seeded query log). Consumers that expose no SQL are carried forward as `UNKNOWN`, not dropped from the count.
2. **Computes the blast radius** — the novel core. It runs a column-usage engine (sqlglot, the same engine behind DataHub's `parse_sql_lineage()`) over every SQL definition it can read and classifies each consumer:
   - 🔴 **BREAKS** — a reference resolves to the column, whether projected into the output *or* sitting in `WHERE`/`JOIN`/`GROUP BY`/`HAVING`/`ORDER BY`. DataHub's parser documents that it excludes the filter clauses — a raw column-reference scan closes that gap, so this view is *more* thorough than the native one.
   - 🟡 **DEGRADES** — the statement still executes but its output changes: a `SELECT *` that silently loses the column.
   - 🟢 **SAFE** — parsed cleanly and provably does not reference the column.
   - ⚪ **UNKNOWN** — could not be assessed: the SQL would not parse (an unrendered dbt Jinja model), or the consumer exposes no SQL at all (PowerBI measures, Looker views). Never filed as safe.
   - ◐ **Ambiguous** — an unqualified column that more than one joined table provides. Gated to low confidence and reported separately: never counted as a definite break, never counted as safe, and it **forces review** because the reference is real and only its attribution is open.
3. **Generates the fix** — mechanically rewrites the affected dbt model against the real schema (drop/rename), producing a clean, applicable git diff.
3b. **Verifies the fix** (`--verify`) — applies the patch in an **isolated copy** of the repo, re-parses the patched SQL, **re-runs the same impact analyzer** over the patched corpus, and compares before/after to issue **PASS / REVIEW_REQUIRED / FAIL** with machine-readable reasons. A non-PASS verdict routes every catalog write to human approval. **This is static verification** — see the PASS definition below. **No query is executed, no warehouse is contacted, and no data is read**; it is evidence about SQL, not about runtime behaviour or results.
4. **Writes back** (gated, approve-before-write): a structured-property status, `pending-schema-change` tags on impacted assets, a one-line pending-change footer, and an **institutional-memory link** to the Impact Assessment. See [What lands in DataHub](#what-lands-in-datahub-exactly) — the catalog stores the link and title; the assessment body is a file that link points at. Results are reported as **planned / written / queued / failed / skipped**, and a dry run reports **0 written** because it wrote nothing.
5. **Reports** — a self-contained visual HTML report (verdict banner above the fold), a CI-style PR comment, and a catalog-wide column-fragility leaderboard.

### What a PASS means — and what it does not

Static migration verification applies the generated patch in an isolated copy, re-parses the
patched SQL, and recomputes the known blast radius. **It does not execute queries, contact a
warehouse, validate row-level results, or replace human approval.**

A migration may PASS **only** when every one of these holds — the conjunction lives in one
place (`verify._decide`) so a gate cannot be bypassed:

| Gate | Requirement |
|---|---|
| `change_target_resolved` | the dataset **and** column named by the change exist in the catalog |
| `target_schema_known` | the catalog records the target's columns at all (an empty schema proves nothing either way) |
| `patch_applied` | the patch applied cleanly in the isolated copy |
| `patched_sql_parses` | every patched SQL file still parses |
| `diff_in_scope` | the diff touched only files the fix was allowed to touch |
| `diff_fully_recomputed` | every patched `.sql` file mapped to a catalog consumer whose impact was recomputed |
| `no_consumer_sql_deleted` | the diff did not DELETE a consumer's defining SQL file |
| `renames_recomputed` | any file the diff MOVED was re-analysed at its new path |
| `no_breaks_after` | breaks after = 0 |
| `no_degrades_after` | degrades after = 0 (new **or** pre-existing) |
| `no_unknown_after` | unassessed consumers after = 0 |
| `no_ambiguous_after` | unattributable references after = 0 |
| `coverage_complete` | no consumer went unanalysed |
| `nothing_regressed` | no consumer's verdict got worse |
| `no_manual_work_remaining` | nothing left that no mechanical fix can reach |
| `no_residual_references` | no patched file still names the dropped column |

Anything **broken, out of scope, regressive, or unresolvable** is `FAIL`. Anything **improved
but incomplete, ambiguous, degraded, unmapped, deleted, moved, or partially assessed** is
`REVIEW_REQUIRED`. Absence of evidence is never treated as proof of safety.

Two of these deserve spelling out, because both were live false-PASS paths:

- **`change_target_resolved`.** A typo'd table or column used to produce an impact report over
  *zero* consumers — and zero breaks over zero consumers satisfied every count-based gate. The
  verifier said PASS about a change it had never assessed. `target_not_found` and
  `column_not_found` are separate reasons, because a wrong table name is a naming/lineage
  problem and a wrong column name is a schema problem.
- **`no_consumer_sql_deleted` / `renames_recomputed`.** A diff that DELETES a consumer's `.sql`
  writes `+++ /dev/null`, and a pure RENAME emits no `---`/`+++` pair at all — so both were
  invisible to the recomputation *and* to the report, and a consumer whose definition had been
  removed came back **SAFE**. A vanished consumer is not an unaffected consumer. A rename is
  allowed to PASS only when the new path maps to a catalog consumer and was actually
  re-analysed there.

Every `.sql` path a diff touches lands in exactly **one** bucket —
`file_query_map` (recomputed) / `unmapped_files` / `deleted_files` / `renamed_files` — and a
test asserts that partition holds.

## Who may write, and who approves

`--write` is not permission. An **automatic** write requires a static verification that
returned **PASS** for that exact change — absence of evidence is never permission:

| Verdict | Automatic write | Human approval |
|---|---|---|
| no `--verify` run | **no** — `not_verified` | no: nothing was assessed, so there is no verdict to approve |
| **PASS** | **yes** | not needed |
| **REVIEW_REQUIRED** | no | **yes**, via an approval manifest |
| **FAIL** | no | **never**, by any route |

`gated` means *needs a human*, not *impossible*. A REVIEW_REQUIRED run writes an **approval
manifest** — `out/APPROVAL-<change>.json`, plus a readable `.md` — listing every queued
mutation with its target URN and what it would write. Approving it applies exactly those
mutations and nothing else:

```bash
autopilot --catalog … --change "…" --verify           --approve out/APPROVAL-<change>.json --approver you@example.com --write
```

The manifest is **bound** (fingerprinted over the change, the verdict and the exact queued
set — any drift is refused as `manifest_stale`), **single-use** (a successful approval is
burned; replaying it is `already_consumed`), and **attributed** (the approver is supplied,
never inferred — no approver, no approval).

**What the binding does not cover.** The fingerprint does not extend to each mutation's
complete canonical payload, mutation IDs are not globally unique, and a partial failure
consumes the manifest instead of producing a retry manifest for the remainder. The
reviewer's rendering is therefore not cryptographically guaranteed to be byte-identical to
what executes. These are documented, deliberate scope boundaries — see
[LIMITATIONS.md](LIMITATIONS.md) §5–§7.

A **FAIL** produces no manifest, and presenting an older one while the verdict is FAIL is
refused with `fail_not_approvable`. There is deliberately no flag, environment variable, or
parameter anywhere in the CLI, the `WriteBack` API, or `--loop` that applies a failed
migration — a test asserts that structurally, by reading the real signatures and flag list.

The record always distinguishes the two paths. `written_auto` and `written_human_approved`
are disjoint buckets that reconcile against the total.

### The approval trail is in the graph, not just in the run (B20.3)

A human-approved write records **six structured properties on the changed dataset**, so the
question "who signed off on dropping this column?" is answered by the catalog rather than by
whoever still has the terminal scrollback:

| Property | What it records |
|---|---|
| `blast_radius_approved_by` | the `--approver` that was supplied — never inferred, never defaulted |
| `blast_radius_approved_at` | when the approval was applied |
| `blast_radius_manifest_id` | which single-use manifest authorised it |
| `blast_radius_verification_status_at_approval` | the verdict the human actually consented to |
| `blast_radius_approved_writes` | how many mutations landed |
| `blast_radius_approved_failures` | how many were attempted and failed |

Four things worth being precise about:

- **An automatic write carries none of them.** No blank approver, no `"system"`, no
  `"auto"` — a machine decision has no approver, so the field is absent and the two paths
  stay distinguishable by inspection. Asserted against the emitted payload, not the local
  document.
- **The counts are outcomes, not intentions.** If three of eight mutations land, the catalog
  says `_approved_writes=3, _approved_failures=5`. Zero writes with non-zero failures is a
  legitimate record: a human approved and it did not land.
- **The audit is a named additional emit, not a quietly enlarged one.** The manifest is
  written before the approval exists, so it cannot list a record *of* that approval.
  Rather than expand an approved mutation's payload beyond the summary the human read, the
  audit is emitted separately — so `written_human_approved` still equals exactly the approved
  set — and the manifest tells the approver, before they consent, that approving records their
  identity in the catalog.
- **It fails loudly.** If the audit emit is rejected, the run reports `audit_status=failed`
  with the error. An approval trail that can vanish while the run still reports a clean
  approval would be the same class of untruth the write counters had removed in B17.4.

Verified live: `out/b20_3_live_readback.txt` (GraphQL read-back off a running DataHub —
15/15 assertions pass) and `out/live_ui/16_b20_3_approval_audit_viewport.png`.

> **`--loop` never writes.** The breadth runner does not verify each fix, so by the rule
> above it can only queue — reported per run as `queued because: not_verified`. Approving a
> migration is a per-change decision, made on a single verified run.

## What lands in DataHub, exactly

Checked against the shipped aspect schema rather than assumed:

```
InstitutionalMemoryMetadata fields = {url, description, createStamp, updateStamp, settings}
```

There is **no document-body field**, so on DataHub OSS the catalog cannot hold the Impact
Assessment text. The write-back is therefore split, and every surface says which is which:

| | What |
|---|---|
| **Stored in DataHub** | `blast_radius_*` structured properties (incl. the six-field approval audit on a human-approved write) · `pending-schema-change` + `impacted-by-upstream-change` tags · a one-line pending-change footer on `editableProperties.description` · an institutional-memory **link** (url + title) |
| **Stored outside, and linked** | the full Impact Assessment markdown, written to `out/ASSESSMENT-<change>.md` — which is exactly what that link points at |

The body is written *before* the link mutation is planned, so the link never dangles. DataHub
Cloud has a real `save_document`; this build does not use it, and does not claim to.

## Dataset-agnostic by construction

Every capability runs off universal metadata primitives — schema, lineage, real queries, ownership — never dataset-specific columns. Adding a dataset is *data, not code*: point discovery at it and run. See `examples/` for worked runs across e-commerce, time-series, healthcare (synthetic), a clean-canvas retail set, and a synthetic finance set.

## Quickstart (offline — no DataHub required)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" \
          --html out/report.html --pr-comment out/PR_COMMENT.md
```

Rename instead of drop:

```bash
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "rename analytics.fct_orders.customer_zip postal_code"
```

## Against a live DataHub

```bash
cp .env.example .env          # fill in DATAHUB_GMS_URL + DATAHUB_TOKEN (never committed)
autopilot --online --target-urn "urn:li:dataset:(...)" \
          --change "drop analytics.fct_orders.customer_zip" --write
```

`--write` applies the gated write-back; `--require-review` queues everything for a human (regulated data). Enable mutation tools on the MCP server (`TOOLS_IS_MUTATION_ENABLED=true`) to write back.

**On pull requests.** The CLI does not open a real GitHub PR — it **generates an applicable patch
and a CI-ready PR comment** (`--pr-comment`). A tested local-PR helper (`report_pr.open_local_pr()`)
can create a branch, apply the patch, commit it, and generate the review comment without requiring
GitHub credentials; pushing and opening the remote PR needs the human's own auth.

### Verified live-MCP run — stated plainly

Against DataHub's official `showcase-ecommerce` datapack, read entirely through
`mcp-server-datahub` v0.6.0 (`scripts/mcp_live_run.py`), target auto-selected as the
most-connected table:

**`order_entry_db.analytics.order_details` · `drop category_name`** — MCP `get_lineage`
**discovered 24 downstream consumers; 6 exposed analysable SQL definitions
(`viewProperties.logic`); the remaining 18 were reported as unassessed.** Of the 6, one
(a dbt model shipped as unrendered Jinja) failed to parse and was also reported
unassessed. Final: **2 BREAKS · 1 DEGRADES · 2 SAFE · 19 UNKNOWN — "HIGH among assessed",
5 of 24 analysed, REVIEW REQUIRED.** `get_dataset_queries` returned **0** — the datapack
ships no query history, so there is no real execution-count evidence in this run and none
is claimed.

The `addresses` table run tells the same story from the other side: **17 discovered,
7 exposed analysable SQL, 10 unassessed**; 5 analysed consumers are genuinely unaffected,
so the verdict is **"LOW among assessed", 5 of 17 analysed, REVIEW REQUIRED** — a LOW that
cannot be mistaken for a clean bill of health. Full call log, counts and timing:
[`MCP_EVIDENCE.md`](MCP_EVIDENCE.md).

## Tests

```bash
pytest        # 198 tests: impact classification, WHERE/JOIN supplement, fix gen (+ git apply),
              # write-back gate + truthful accounting, safety semantics (UNKNOWN / ambiguous /
              # coverage / fail-closed), proof-carrying verification, target + schema
              # resolution, destructive diffs (delete/rename, incl. git-quoted unicode paths),
              # what actually persists to DataHub, and the human-approval path
              # (bound + single-use manifests; FAIL never approvable)
```

Verify a generated migration statically:

```bash
autopilot --catalog examples/verified-migration/catalog.json \
          --change "drop analytics.fct_signups.referrer_code" --verify
# -> PASS — breaks 2->0, degrades 0->0, unassessed 0->0, ambiguous 0->0,
#    coverage 3 of 3 analysed, 2 of 2 patched files recomputed
#    out/VERIFICATION.md + out/verification.json
```

Only a **PASS** may auto-apply the write-back. Captured contrasts (2026-07-30):

| Target | Verdict | Why |
|---|---|---|
| `examples/verified-migration` | **PASS** | breaks 2→0; every gate above satisfied |
| offline flagship `showcase-ecommerce` | **REVIEW_REQUIRED** | breaks 6→5 (five breaking consumers are BI dashboards/ad-hoc queries no mechanical fix reaches) **and** 1 unattributable reference → write-back **0 written / 8 queued** |
| live MCP datapack target `order_details` | **FAIL** | breaks 2→2 unchanged — both Tableau consumers use the column in `WHERE`/`GROUP BY`, which the fix generator deliberately never auto-rewrites. **Re-run live against the current build on 2026-08-03** (`MCP_EVIDENCE.md`, `out/b20_mcp_live_run.txt`): still FAIL, now on **six** named reasons instead of one, over coverage **5 of 24 analysed**. Impact counts are byte-identical to the B15 capture. Earlier README wording said this had *not* been re-run and that its verdict was reasoning rather than a captured run — it is now a captured run. |
| live MCP datapack target `addresses` | **FAIL** | `no_patch_provided` — 0 breaks among the 5 analysable consumers, so no patch is generated and there is nothing to verify. Coverage **5 of 17 analysed**, 12 UNKNOWN. See the calibration note in `MCP_EVIDENCE.md`: FAIL is the one verdict a human can never approve, so a target needing no mechanical fix currently has no route to record its assessment. |

Runs are captured in `out/verification_*_run.txt`, `out/b17_pass*`, and `out/b17_review*`.

## Overnight Catalog Sweep (B21)

`--verify` answers "is *this* change safe?". `--sweep` answers the bigger question: across the
whole catalog, which columns can be changed, which need a human, and which are landmines.

```bash
autopilot --catalog examples/showcase-ecommerce/catalog.json --sweep
autopilot --catalog examples/showcase-ecommerce/catalog.json --sweep --sweep-limit 5   # fast
# -> out/SWEEP.md + out/SWEEP.html + out/sweep.json
```

It enumerates every candidate column change in fragility order, runs the **same** impact → fix →
verify chain on each, and files the result in one of five buckets, worst first: 🔴 Landmines ·
❓ Unassessed · ⚠️ Needs review · ✅ Verified safe · ⚠️ Errors. Across the six synthetic catalogs
(43 candidates, 7 datasets, 0.65 s): **25 landmines, 1 needs review, 17 verified safe, 0 errors**.

Two properties worth stating plainly:

- **A sweep is READ-ONLY by construction.** It cannot write to DataHub — the module does not
  import the write layer, never constructs a client, and the CLI branch returns before any
  write-back code is reachable. Three tests enforce it, including one that makes every
  `WriteBack` method and `DataHubGraph.__init__` raise and then runs two full sweeps.
- **"Verified safe" is split by `basis`.** `verified_patch` means a fix was generated, applied in
  isolation and re-checked. `no_references` means nothing that parses referenced the column, so
  no patch was needed and **none was verified**. Both are safe to change; only one involved
  verifying anything, and the ledger never lets the second borrow the first's credibility. (8 of
  the 17 above are `verified_patch`; 9 are `no_references`.)

`unassessed` is evaluated before every other bucket: if any consumer could not be read, zero
breaks is not a clean bill of health and the row cannot be called safe.

## Documentation

| File | What it is |
|---|---|
| [`LIMITATIONS.md`](LIMITATIONS.md) | **Known limitations** — the residual risks we identified, decided not to close, and state plainly: what static verification does *not* prove, coverage bounded by what the catalog exposes, the partial approval-manifest binding (§5–§7), and what actually lands in DataHub |
| [`DESIGN.md`](DESIGN.md) | The product spec and architecture |
| [`TEST_GUIDE.md`](TEST_GUIDE.md) | Browse the results in a live DataHub UI — per-scenario search terms, who may write, and the two-step approval route |
| [`MCP_EVIDENCE.md`](MCP_EVIDENCE.md) | Every DataHub MCP call, its exact return, counts and timings — including the 2026-08-03 live re-run of both targets |
| [`LIVE_DATAHUB_EVIDENCE.md`](LIVE_DATAHUB_EVIDENCE.md) | GraphQL read-back proof of the live write-backs |
| [`EXAMPLES.md`](../EXAMPLES.md) | The ≥5 dataset types the same code runs against |
| [`demo/demo_script.md`](demo/demo_script.md) | The <3-minute demo shot list |
| [`out/README.md`](out/README.md) | Index of every captured artifact — current vs superseded |

Read `LIMITATIONS.md` alongside the PASS-gate table above: the gates say what is checked, and
that file says what is deliberately *not*.

## License

Apache-2.0. Public/synthetic data only — never real or production company data.
