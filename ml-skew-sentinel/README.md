# ML Skew Sentinel

**An agent that walks DataHub's ML lineage to catch silent training/serving skew — then writes its diagnosis back onto the model so the next person or agent inherits it.**

Built for [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/) — Track: Production ML Agents.

Silent feature drift and training/serving skew are among the most expensive ML failure modes: nothing errors, the model just quietly gets worse. Traditional monitoring misses it because the pipeline stays green. The Sentinel reads the path from **training data → features → model** in DataHub, compares live inputs against the model's training baseline, and when it finds skew it tags the model, records a machine-readable drift score, and files a root-cause note back into the catalog.

> Judges reward projects that go *beyond reading metadata and contribute back to the graph.* Writing the diagnosis back is the core of this project, not an afterthought.

## How it works

```
        READ (MCP / SDK)              DETECT                    WRITE BACK (MCP / SDK)
  ┌───────────────────────┐   ┌────────────────────┐   ┌────────────────────────────┐
  │ model → upstream       │   │ schema drift        │   │ tag: at-risk / skew-detected│
  │ features → source data │ → │ distribution (PSI/KS)│ → │ props: drift_score, upstream│
  │ schema + freshness     │   │ freshness vs SLA     │   │ knowledge doc: root cause   │
  └───────────────────────┘   └────────────────────┘   └────────────────────────────┘
                                      │
                          baseline.json (captured at seed time)
```

The training baseline is snapshotted when you seed the model, so distribution-drift detection does **not** depend on DataHub retaining historical profiles.

### DataHub tools used

| Step | MCP tool (agent mode) | SDK (library mode) |
|------|-----------------------|--------------------|
| Traverse model → features → source | `get_lineage`, `get_lineage_paths_between` | `searchAcrossLineage` GraphQL |
| Read current schema / columns | `get_entities`, `list_schema_fields` | `schemaMetadata` GraphQL |
| Read freshness | `get_entities` (operation aspect) | `operations` GraphQL |
| Tag the model | `add_tags` | `GlobalTags` aspect |
| Record drift score / offender | `add_structured_properties` | `MLModelProperties.customProperties` |
| File root-cause note | `save_document` | local copy under `runs/` |

Enable the MCP write path on the server with `TOOLS_IS_MUTATION_ENABLED=true`.

## Quickstart

```bash
# 0. Python 3.10+; install
pip install -e .

# 1. Stand up DataHub locally (see https://docs.datahub.com/docs/quickstart)
#    then create a token in the UI and copy .env
cp .env.example .env      # fill in DATAHUB_TOKEN

# 2. Seed an ML model + lineage and snapshot the training baseline
python scripts/seed_ml_metadata.py --training-data data/nyc_taxi_train.csv

# 3. Run the sentinel against live serving data (offline dry run)
python -m sentinel.run --baseline baseline.json --serving-data data/nyc_taxi_live.csv

# 4. Run against DataHub and write the diagnosis back
python -m sentinel.run --online --write --serving-data data/nyc_taxi_live.csv
```

Without `--write` the run is a dry run and prints the exact mutations it *would* make — good for your first pass and for the demo's "before" shot.

## Demo dataset

Uses the hackathon's [`nyc-taxi`](https://github.com/datahub-project/static-assets/tree/main/datasets/nyc-taxi) sample (planted freshness issues). Seed a "NYC Taxi Fare Predictor" over it, then point `--serving-data` at a shifted slice of trips to trigger distribution drift. See [`demo/demo_script.md`](demo/demo_script.md) for the <3 min shot list.

## What's tested vs. what to verify

- **Fully unit-tested (no DataHub needed):** the detectors — PSI/KS distribution drift, schema diff, freshness — and the agent's diagnosis assembly. Run `PYTHONPATH=src python -m pytest -q`.
- **Verify against your instance:** the DataHub read/write calls in `lineage.py` and `writeback.py` follow the documented GraphQL/SDK APIs; confirm aspect/field names against your DataHub version at `http://localhost:9002/api/graphiql`. The seed script mirrors the [official ML tutorial](https://docs.datahub.com/docs/api/tutorials/ml); vendor `dh_ai_client.py` from the DataHub repo's `metadata-ingestion/examples/ai/` into `scripts/`.

## Project structure

```
ml-skew-sentinel/
├── LICENSE                      # Apache 2.0
├── README.md
├── pyproject.toml
├── .env.example
├── scripts/
│   └── seed_ml_metadata.py      # seed ML lineage + snapshot baseline.json
├── src/sentinel/
│   ├── lineage.py               # READ: lineage, schema, freshness
│   ├── detectors/               # DETECT: schema / distribution / freshness
│   ├── agent.py                 # diagnose() + optional LLM narrative
│   ├── writeback.py             # WRITE BACK: tags, properties, doc
│   └── run.py                   # CLI: read → detect → diagnose → write back
├── tests/test_detectors.py
├── examples/
│   └── sample_at_risk_report.md # sample output for judges
└── demo/demo_script.md
```

## How this maps to the judging criteria

- **Use of DataHub** — reads the ML context graph *and* writes tags, structured properties, and a knowledge doc back through MCP.
- **Technical Execution** — deterministic detectors with unit tests; runs end-to-end on a seeded model.
- **Originality** — an autonomous cross-lineage skew agent, extending DataHub rather than rebuilding its features.
- **Real-World Usefulness** — training/serving skew is a top, universally-felt ML failure mode.
- **Submission Quality** — this README, a sample output, and a tight demo script.
- **Bonus (OSS)** — package the skew check as a reusable DataHub Skill and PR it to [`datahub-project/datahub-skills`](https://github.com/datahub-project/datahub-skills).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
