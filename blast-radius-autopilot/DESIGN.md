# Blast Radius Autopilot — Build Design

*Grand-prize swing for Build with DataHub: The Agent Hackathon. Deadline Aug 10, 2026.*
*Consolidated after independent technical verification on both sides. Implementation pending the one query-history check (§7).*

## One-line pitch (own the overlap in the first breath)

> **DataHub's Impact Analysis shows you the blast radius of a schema change. Blast Radius Autopilot defuses it** — it computes evidence-backed column-level impact from available query history and downstream SQL definitions, while explicitly reporting unparseable, ambiguous, and non-SQL consumers, statically verifies its own patch, generates an applicable patch and a CI-ready PR comment, and records the assessment back in the catalog.

Naming and positioning: keep "Blast Radius" (it's DataHub's own term — owning it head-on is more disarming than a rename); product name **Blast Radius Autopilot** to signal the action. The README's first sentence names DataHub's Impact Analysis explicitly and states we're the agent layer that *acts* on it.

## Why it can win

- **Deepest authentic use of DataHub** — the agent derives column-level impact by running DataHub's own SQL parser (`parse_sql_lineage()`, stated 97-99% accuracy) over real queries from `get_dataset_queries`, then writes results back. That's read + reason + contribute, which criterion #1 rewards most.
- **Original beyond out-of-box** — viewing downstream lineage is shipped; *autonomously generating the migration fix + recording a durable impact assessment* is not.
- **Visceral, universal pain** — breaking schema changes are every data team's nightmare; the judges have all caused one.
- **Track fit** — leads on **Metadata-Aware Code Generation** (near word-for-word: reads DataHub for real schemas/lineage so generated code merges first try). Secondary listing under "Agents That Do Real Work" *only if* the rules permit one submission in multiple categories — confirm, don't assume.

## Architecture

```
 INPUT: "drop/rename column C on table T"  (CLI arg, or parsed from a dbt PR diff)

 1. GATHER (MCP / SDK reads)
    list_schema_fields / get_entities  → confirm T's schema, ownership
    get_lineage (DOWNSTREAM)           → candidate downstream assets
    get_dataset_queries (T + downstreams) → real SQL that touches T

 2. COMPUTE BLAST RADIUS  ★ the novel, agent-derived core
    parse_sql_lineage() on each query  → column-level: which queries/assets read T.C
    raw column-reference scan          → catch C used only in WHERE/JOIN/GROUP BY
                                         (documented parser gap — this closes it)
    classify each asset: BREAKS | DEGRADES | SAFE | UNKNOWN ; rank; map owners/teams
    (UNKNOWN = unreadable or no SQL at all; plus an `ambiguous` axis for
     references that parsed but cannot be attributed to a source table. Neither
     is ever counted as safe, and either forces human review.)

 3. GENERATE THE FIX  (scoped, mechanical, reliable)
    regenerate the target dbt model's SQL to the new/removed column,
    using the real schema read from DataHub → git diff → CI-ready PR comment
    (the CLI does not open a remote PR; open_local_pr() branches+commits locally)

 4. WRITE BACK  (contribute to the graph)
    update_description / structured property on T: "pending change, impact assessed"
    institutional-memory LINK to the Impact Assessment (url + title)
    NOTE (verified B18.3): the OSS institutionalMemory aspect stores url +
    description only — no document body. The assessment markdown is persisted
    to out/ASSESSMENT-<change>.md and that link points at it. Cloud has a real
    save_document; this build does not use it.
```

### Design decisions locked from the consult
- **Use `DataHubGraph.parse_sql_lineage()` directly. Avoid `SqlParsingAggregator`** — the aggregator is not an officially supported part of the SDK; too much undocumented surface for a 19-day build.
- **Gate parser output on `confidence_score`** — skip/flag low-confidence parses rather than assert them.
- **The raw column-reference scan is required, not optional** — DataHub's parser explicitly excludes columns used only in filtering/organizational clauses, so filter-only breakage would be missed without it. This also makes our impact view *more* thorough than the native one.

## Scope discipline (how the ambitious idea stays winnable)

A broken ambitious demo loses to a working simple one. So:
- **Fix generation is mechanical only** — column rename/drop propagated into one dbt model. No arbitrary logic rewrites. Everything else is "what's next," shown not built.
- **The on-camera PR must merge** — pre-stage the repo, rehearse, keep the change mechanical.
- **Public data only** — repo/code/video public; mutation tools write into a demo catalog. Use DataHub's demo instance or hackathon sample data. Never real/production company data.

## The one check — reframed (§7)

**Load showcase-ecommerce, pick a well-connected asset, call `get_dataset_queries`. Does real query history come back?**
- **Yes** → proceed; the agent derives impact from that history.
- **Thin/empty** → **fallback:** ingest a realistic query log against the pack's tables via DataHub's `sql-queries` connector. This yields both query history and column-level lineage, and doubles as a demo of that capability. Either way we are unblocked.

*(I can't run this from here — no DataHub instance — so it's the one thing for you to eyeball. The fallback means the answer changes the path, not whether we can build.)*

## Milestones (~19 days, weekends + evenings)

- **M0 — day 1-2:** DataHub Quickstart + showcase-ecommerce; run the query-history check (§7); confirm `parse_sql_lineage()` on one real query. Decide: existing history vs. seed a query log.
- **Week 1:** read layer (lineage + queries + ownership) + `parse_sql_lineage` integration → a correct blast-radius report for one column, with BREAKS/DEGRADES/SAFE. *Milestone: given T.C, list impacted queries/assets accurately.*
- **Week 2:** mechanical dbt fix generation + PR + write-back (assessment doc + structured property). *Milestone: end-to-end on one column → PR + assessment in DataHub.*
- **Week 3:** LLM-written assessment narrative, polish, <3-min demo video, README, OSS Skill PR, submit + feedback survey. Keep 1-2 days buffer.

## Demo (< 3 min)

1. "I want to drop `customer_zip`." — asset shown healthy in DataHub.
2. Run the Autopilot — live: it pulls queries, parses column lineage, and prints the blast radius: *breaks 3 dashboards, 1 model, 41 queries across 2 teams.*
3. It opens a PR fixing the affected dbt model against the real schema.
4. Refresh DataHub — the Impact Assessment doc + status are now on the asset.
5. Close: "One column change, assessed and fixed, in 30 seconds — instead of a Monday-morning incident." One "what's next" line (continuous mode, multi-repo fixes) — mentioned, not built.

## Risks → mitigations

| Risk | Mitigation |
|------|------------|
| Sample pack lacks query history | Bring-your-own query log via `sql-queries` connector (documented) |
| On-camera PR must actually merge | Pre-staged repo, mechanical rename/drop only, rehearsed |
| `parse_sql_lineage` edge cases | Gate on `confidence_score`; raw-scan supplement; skip low-confidence |
| Aggregator instability | Use `parse_sql_lineage()` directly; avoid `SqlParsingAggregator` |
| "Isn't this just Impact Analysis?" | Own it in line 1; novelty = agent-derived impact + auto-fix + written-back memory |
| Multi-category entry assumed | Confirm on the rules page; otherwise lead single-category (Code Gen) |

## OSS bonus

Package "column-level impact from query history" as a reusable DataHub **Skill** and PR it to `datahub-skills`. Converts the overlap conversation into the meaningful-contribution criterion.

## Reusable from prior scaffolds

Repo structure, Apache-2.0 setup, README pattern, the MCP read/write tool mappings, and the write-back patterns (structured properties, `save_document`) all carry over from the earlier work.
