# 🪦 The Data Necromancer

**An autonomous metadata investigation engine for DataHub. It resurrects the dead — undocumented assets — and exposes the *zombies*: metadata that has silently gone wrong.**

Built for [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/).

Every catalog is full of tables nobody documented and, worse, descriptions that are now *lies* — "sourced from Oracle ERP" when lineage quietly moved to Snowflake, "deprecated" stamped on a table 300 queries a day depend on. DataHub's `enrich` skill fills blank fields. **Nothing catches a description that has gone false.** The Necromancer does: it investigates the evidence (schema, lineage, real queries, downstream usage), reconstructs meaning only when the evidence corroborates it, and writes its conclusions — with their provenance — back into the catalog.

> This deliberately composes DataHub's shipped skills (`enrich`, `quality`, `lineage`) rather than rebuilding them — the hackathon's criteria reward exactly that. The new capability is **contradiction detection** and **evidence-bound reconstruction**, which those skills don't provide.

## Why this isn't "another documentation generator"

1. **Zombie detection.** Flags assets whose *existing* description contradicts current lineage/queries — `source_mismatch`, `false_deprecation`, `stale_column`. Structurally impossible for a blank-filling enricher.
2. **Evidence-bound, anti-hallucination.** Reconstructs only when ≥2 independent evidence types agree, and **refuses to write** when they don't (marks it for a human). It will decline on camera.
3. **Measurable impact.** A catalog knowledge leaderboard with a coverage metric you can watch move in one run.
4. **Ships as a DataHub Skill.** Packaged and PR'd to `datahub-skills` — turning the "overlap" question into the open-source bonus.

## Real output (from `examples/sample_catalog.json`, no DataHub required)

```
====================================================================
CATALOG KNOWLEDGE LEADERBOARD  (worst first)
====================================================================
  🔴 Critical       …analytics.fct_revenue
      └ load-bearing (340 queries, 2 downstream)
  🔴 Critical       …analytics.dim_customer_legacy
      └ load-bearing (120 queries, 3 downstream)
  🟡 Needs Review   …marketing.stg_marketing_spend
      └ zombie: [source_mismatch] description cites "salesforce" but current lineage is [s3.marketing_raw]
  🟠 Forgotten      …analytics.dim_product
      └ undocumented; reconstructable
  🟠 Forgotten      …raw.mystery_blob
      └ undocumented; evidence too thin to reconstruct
  🟢 Healthy        …analytics.dim_date
      └ documented and consistent with evidence
--------------------------------------------------------------------
  coverage: 16.7% healthy  |  🔴 2  🟡 1  🟠 2  🟢 1
====================================================================

INVESTIGATION — …analytics.fct_revenue
  • lineage: 2 upstream source(s)
  • queries: 340 real queries reference it
  • downstream: 2 dependent asset(s)
  ⚠️  ZOMBIE — documentation contradicts evidence:
       - [source_mismatch] description cites "oracle" but current lineage is [snowflake.raw_billing, dbt.stg_billing]
  → action: REVIEW  (confidence: strong)

Summary: 1 written, 3 queued for review, 2 skipped.
```

## How it works

```
   SCAN                 EVIDENCE                 INVESTIGATE              WRITE BACK (gated)
 search /        get_lineage, get_entities,   triangulate ≥2 sources,   update_description + footer,
 get_entities    get_dataset_queries,         detect contradictions,    add_structured_properties,
                 list_schema_fields           abstain if thin           save_document
```

| Step | MCP tool (agent) | Library mode (SDK) |
|------|------------------|--------------------|
| Find assets | `search` | GraphQL search |
| Collect evidence | `get_lineage`, `get_lineage_paths_between`, `get_dataset_queries`, `get_entities`, `list_schema_fields` | GraphQL |
| Write description + evidence footer | `update_description` | `EditableDatasetProperties` |
| Record health status | `add_structured_properties` | structured property |
| File data dictionary | `save_document` | knowledge doc |

Enable writes on the server with `TOOLS_IS_MUTATION_ENABLED=true`.

## Quickstart

```bash
pip install -e .

# offline — rehearse the whole flow, no DataHub needed
python -m necromancer.run --assets examples/sample_catalog.json

# against DataHub (dry run first; add --write to apply)
python -m necromancer.run --online --urns "urn:li:dataset:(...)"
python -m necromancer.run --online --write --urns "urn:li:dataset:(...)"
```

## Approve-before-write is built in

DataHub has no native "suggest, then a human approves" gate for descriptions/ownership (its governed proposals cover glossary terms and lifecycle only). So the gate lives in the Necromancer: **only `action == "write"` (strong evidence, no prior doc) is written.** Contradicted/zombie assets and thin-evidence assets are *queued for human review*, never silently overwritten.

## Demo flow (< 3 min)

1. **Cold open on the leaderboard** — the worst assets in the catalog, ranked.
2. **Drill into a 🔴** — undocumented and load-bearing, or a zombie whose docs lie.
3. **Run the Necromancer** — the investigation trace prints live: schema → lineage → queries → conclusion.
4. **Show the write-back** — new description with its evidence footer; health status on the asset.
5. **Watch coverage jump** on a re-scan.
6. **One "what's next" line** (deferred, not built): continuous monitoring, ownership workflows.

## Constraints (important)

- **Public data only.** Repo, code, and demo video are public, and the mutation tools write into whatever catalog is connected — use DataHub's demo instance or the hackathon sample datasets, **never real/production company data**.
- DataHub read/write calls follow the documented APIs; verify field/aspect names against your instance at `http://localhost:9002/api/graphiql`. Structured properties must be defined once before values can be set.

## What's tested vs. what to verify

- **Unit-tested, no DataHub needed:** contradiction detection, evidence-bound abstention, and health/leaderboard logic — `PYTHONPATH=src python -m pytest -q`.
- **Verify on your instance:** the DataHub read (`evidence.py`) and write (`writeback.py`) calls.

## How this maps to the judging criteria

- **Use of DataHub** — reads lineage/queries/schema *and* writes descriptions, structured properties, and knowledge docs back; contributes to the graph.
- **Originality** — contradiction detection + evidence-bound abstention go beyond DataHub's out-of-box enrichment.
- **Technical Execution** — deterministic core with unit tests; runs end-to-end offline and against DataHub.
- **Real-World Usefulness** — stale/false metadata erodes trust in every catalog.
- **Submission Quality** — this README, real sample output, a tight demo script.
- **Bonus (OSS)** — package the investigator as a DataHub Skill and PR it to [`datahub-skills`](https://github.com/datahub-project/datahub-skills).

## Structure

```
data-necromancer/
├── LICENSE  ·  README.md  ·  pyproject.toml
├── examples/sample_catalog.json      # 6 assets: zombies, forgotten, critical, healthy
├── src/necromancer/
│   ├── evidence.py          # SCAN + COLLECT
│   ├── investigator.py      # triangulation, abstention, zombie detection ★
│   ├── health.py            # buckets + leaderboard + coverage
│   ├── writeback.py         # gated write-back
│   └── run.py               # CLI
└── tests/test_investigation.py
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
