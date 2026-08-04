# ML Skew Sentinel — Build Plan

**Hackathon:** Build with DataHub: The Agent Hackathon
**Track:** Production ML Agents (Track 3)
**Deadline:** Aug 10, 2026, 5:00pm ET · Judging Aug 17–31 · Winners ~Sep 8
**Status:** Draft plan (API specifics flagged for verification — see §9)

---

## 1. The pitch (one sentence)

An autonomous agent that walks DataHub's end-to-end ML lineage — training data → features → model → deployment — and catches *silent* training/serving skew and feature drift *before* it degrades a production model, then writes its diagnosis back onto the model in DataHub so the next person (or agent) inherits it.

**Why it wins the room:** silent feature drift and training-serving skew are among the most common and most expensive causes of ML incidents, and they're invisible in normal monitoring because nothing errors — the model just quietly gets worse. Every ML/platform judge has been burned by this.

## 2. Why this track, this idea

- **Thinnest field.** Most hackathon entrants build chatbots and code-gen. Track 3 needs real ML-lineage understanding, so fewer credible entries — and there's a dedicated $3,000 Challenge Winner prize *per track*.
- **Hits criterion #1 hardest.** Judges repeatedly say the strongest submissions "go beyond reading metadata and contribute back to the graph." This design's whole point is the write-back loop.
- **Demo-able in 3 minutes** on a sample dataset with planted issues (see §5).

## 3. Architecture

Three stages — **Read → Detect → Write back** — orchestrated by an LLM agent.

```
                    ┌─────────────────────────────────────────┐
                    │              ML Skew Sentinel Agent       │
                    │  (LLM orchestration + root-cause writeup) │
                    └─────────────────────────────────────────┘
        READ (MCP Server / SDK)      DETECT              WRITE BACK (SDK)
   ┌──────────────────────────┐  ┌──────────────┐  ┌──────────────────────────┐
   │ For a target MLModel:     │  │ schema drift │  │ Tag model "at-risk"       │
   │  • traverse upstream      │→ │ dist. drift  │→ │ Structured property:      │
   │    lineage to feature     │  │  (PSI / KS)  │  │   drift_score, offender,  │
   │    tables + source data   │  │ freshness    │  │   checked_at              │
   │  • fetch schemas + stats  │  │ vs training  │  │ Incident / assertion      │
   │  • fetch training snapshot│  │  baseline    │  │ result on model + upstream│
   └──────────────────────────┘  └──────────────┘  │ Human-readable root cause │
                                                    └──────────────────────────┘
```

**The agent angle (matters for "Agents That Do Real Work" framing):** don't hard-code a script. Give an LLM (e.g., Claude) the DataHub MCP tools and let it decide which upstream entities to inspect, interpret the drift numbers, write the natural-language root cause, and choose the write-back action. That's what makes it an *agent*, not a cron job.

## 4. What it reads and writes in DataHub

**Reads (via MCP Server, or GraphQL through the Python SDK):**
- ML lineage: `MLModel` → `MLModelGroup`, `MLFeatureTable`, `MLFeature`, upstream `Dataset`(s), and `MLModelDeployment` downstream.
- Schemas of upstream feature tables / datasets (current vs. the model's training-time snapshot).
- Dataset profiles / column statistics (min/max/mean/nulls/distinct) if profiling is enabled — used as the distribution baseline. If not available, capture the baseline yourself at seed time (see §9).
- Freshness / last-updated (operation aspect) on upstream tables.

MCP read tools that cover this: `get_lineage` and `get_lineage_paths_between` (traverse model → features → sources), `get_entities` (full metadata/schema/ownership/docs), `list_schema_fields` (columns), `search` (find the model/tables), `get_dataset_queries` (usage).

**Writes back — all supported natively by the MCP Server's mutation tools (set `TOOLS_IS_MUTATION_ENABLED=true`), so the agent writes through the same MCP interface it reads with:**
- `add_tags` — flag the model `skew-detected` / `at-risk`.
- `add_structured_properties` — attach `drift_score`, `offending_upstream`, `check_type`, `checked_at` (supports string/number/URN/date/rich-text). Machine-readable and queryable. *The property must be defined once up front (CLI/SDK) before values can be set.*
- `update_description` — append a short at-risk banner to the model's docs.
- `save_document` — write the full root-cause writeup as a knowledge article into DataHub's knowledge base, so the next person or agent inherits it.

> **Verified:** the MCP Server has both read and write ("mutation") tools, so the entire read → act → write loop runs through MCP — a clean "agent that does real work" story. Assertions/incidents as a write target are **not** guaranteed in OSS Core (parts live in DataHub Cloud), so lean on tags + structured properties + documents, which are confirmed OSS. Treat assertions/incidents as an optional bonus only if your DataHub version supports them.

## 5. Demo dataset & narrative

The sample datasets ship with data problems but not necessarily ML entities, so **seed the ML layer yourself** — which doubles as a showcase of DataHub's write API.

**Recommended:** `nyc-taxi` (~500k trips, 3-stage pipeline with *planted freshness issues*).

1. **Seed** an `MLModel` "NYC Taxi Fare Predictor" + an `MLFeatureTable` (trip distance, pickup zone, hour-of-day, etc.) with lineage back to the taxi trips dataset. Capture a training-time baseline snapshot.
2. **Trigger:** the planted freshness issue means an upstream feature stops updating; separately, inject/point at a distribution shift in one feature.
3. **Run the sentinel:** agent traverses lineage, detects the stale upstream + the drifted feature, computes a PSI drift score, writes "at-risk" + structured property + incident back onto the model, and produces a plain-English root cause ("feature `pickup_zone` distribution shifted (PSI 0.38) and `trip_distance` is 3 days stale — model retrained Jun 3 is now serving on skewed inputs").
4. **Payoff shot:** open the model in the DataHub UI — the tag, incident, and root-cause note are now there for the next engineer.

## 6. Detection logic

- **Schema drift** — diff the upstream schema vs. the training-time schema: added/removed columns, type changes, nullability changes. Deterministic, high-signal, easy to demo.
- **Distribution drift** — Population Stability Index (PSI) and/or KS distance per feature, current stats vs. training baseline. PSI thresholds: <0.1 stable, 0.1–0.25 moderate, >0.25 significant. `scipy` covers this.
- **Freshness skew** — upstream table's last-update timestamp vs. an expected cadence / the model's serving assumption. This is the planted nyc-taxi issue.

Keep the math simple and defensible; the novelty is doing it *across the lineage graph automatically and writing results back*, not the statistics.

## 7. Tech stack

- **Language:** Python (only realistic choice — DataHub SDK + MCP server are Python-first).
- **DataHub:** local Quickstart (`datahub docker quickstart`), `acryl-datahub` SDK for seeding + structured-property definition, and the DataHub MCP Server (self-hosted endpoint `http://<gms-host>:8080/mcp`) with `TOOLS_IS_MUTATION_ENABLED=true` for the read+write loop.
- **Agent:** an LLM with the DataHub MCP tools attached. Options: `pip install datahub-agent-context` (Python 3.10+, needs a personal access token) for LangChain / Google ADK, or connect Claude directly (there's an official DataHub "Claude (Code & Desktop)" setup guide) — handy for fast prototyping.
- **Stats:** `scipy` / `numpy` / `pandas`.
- **Optional CI:** a GitHub Action that runs the check on a schedule or on PR and comments findings.

## 8. Three-week plan (from Jul 22)

**Week 1 (Jul 22–28) — Foundations**
- Quickstart DataHub locally; load `nyc-taxi`.
- Seed `MLModel` + `MLFeatureTable` + lineage via SDK; capture training baseline.
- Get the MCP server / SDK returning a model's full upstream lineage.
- *Milestone:* agent prints complete lineage + schemas for the seeded model.

**Week 2 (Jul 29–Aug 4) — Detection + write-back**
- Implement the three detectors (schema, distribution/PSI, freshness).
- Implement write-back: tag + structured property + incident/assertion + root-cause note.
- *Milestone:* end-to-end run detects the planted issue and annotates the model in the UI.

**Week 3 (Aug 5–10) — Agent, polish, submit**
- Wrap in LLM agent orchestration + natural-language root cause.
- README, `examples/` (sample at-risk report + write-back JSON), Apache 2.0 LICENSE.
- Record <3 min demo video (YouTube/Vimeo, public).
- Ship one OSS contribution (§10). Submit on Devpost + complete the feedback survey ($50 bonus). Keep 1–2 days buffer.

## 9. Things to VERIFY before building (don't assume)

*(Most now verified against the docs — status noted below.)*

1. ~~MCP Server capabilities~~ — **RESOLVED.** Reads: `search`, `get_entities`, `get_lineage`, `get_lineage_paths_between`, `list_schema_fields`, `get_dataset_queries`. Writes (set `TOOLS_IS_MUTATION_ENABLED=true`): `add_tags`, `add_structured_properties`, `update_description`, `add/remove_terms`, `add_owners`, `set_domains`, plus `save_document`. The full read→write loop runs through MCP.
2. **Historical profiles/stats** — *still the #1 risk.* Confirm whether DataHub retains time-series column stats (datasetProfile) for a distribution baseline, and whether the sample data includes them. Mitigation stands: **capture your own baseline at seed time**. Verify in the profiling docs.
3. ~~Structured properties~~ — **RESOLVED (mostly).** `add_structured_properties` supports string/number/URN/date/rich-text values; the property definition must be registered once first (CLI/SDK). Confirm that one-time definition flow.
4. **Assertions / incidents** — **partly resolved:** **not guaranteed in OSS Core** (assertions / data-contracts / health-dashboard live largely in DataHub Cloud). Don't depend on them; use tags + structured properties + `save_document` for write-back. Confirm what your version supports if you want them as a bonus.
5. **ML entity model** — confirm current aspect names for `MLModel` / `MLFeatureTable` / training-run linkage (`DataProcessInstance`) in the metamodel entity docs so the seed script is correct.

## 10. Open-source contribution (bonus criterion — cheap points)

Pick one, PR it during the hackathon window:
- Package the skew check as a reusable **DataHub Skill** and PR to `datahub-project/datahub-skills` (best fit — directly extends the agent stack the hackathon is about).
- Contribute **docs** on ML-lineage-based drift monitoring.
- A small **fix or example** in `datahub-project/datahub` for ML metadata emission.

## 11. Repo structure

```
ml-skew-sentinel/
├── LICENSE                       # Apache 2.0 — visible in About section (required)
├── README.md                     # what/why/setup/demo — judged on this
├── pyproject.toml
├── src/sentinel/
│   ├── lineage.py                # read ML lineage (MCP/SDK)
│   ├── detectors/
│   │   ├── schema_drift.py
│   │   ├── distribution_drift.py # PSI / KS
│   │   └── freshness.py
│   ├── writeback.py              # tags, structured properties, incidents
│   └── agent.py                  # LLM orchestration + root-cause narrative
├── scripts/
│   └── seed_ml_metadata.py       # emit MLModel + feature table + lineage
├── examples/                     # sample outputs for judges (recommended)
│   ├── sample_at_risk_report.md
│   └── sample_writeback.json
└── demo/
    └── demo_script.md            # <3 min video shot list
```

## 12. How it maps to the judging criteria (all equally weighted)

| Criterion | How this scores |
|---|---|
| Use of DataHub | Reads the context graph + ML lineage via MCP **and writes tags/structured properties/incidents back** — the "beyond reading" behavior judges call out. |
| Technical Execution | End-to-end, runs on a seeded model against a planted issue; deterministic detectors + defensible stats. |
| Originality | Autonomous cross-lineage skew/drift agent — extends DataHub's assertions rather than rebuilding them. |
| Real-World Usefulness | Training-serving skew & silent drift are top ML failure modes; instantly relatable to any ML team. |
| Submission Quality | Clean README, `examples/` folder, tight <3 min demo with a clear before/after in the UI. |
| Bonus (OSS) | A PR'd DataHub Skill or docs contribution. |

## 13. Submission checklist

- [ ] Public repo, **Apache 2.0 license visible in the About section**
- [ ] Testable project URL (repo + clear setup, or hosted demo)
- [ ] Written description
- [ ] Demo video <3 min, public on YouTube/Vimeo
- [ ] `examples/` folder with sample outputs
- [ ] New code, built in-window; disclose any pre-existing code
- [ ] Feedback survey submitted (opt in for the $50 bonus)
