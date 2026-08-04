# BUILD_GUIDE.md — Living Spec & Verified Knowledge

The loop reads this first and updates it as it learns. If a fact here is wrong, fix it here
*and* note the correction in `PROGRESS.md`. Nothing hard-won gets rediscovered.

## What we're building

**Blast Radius Autopilot** — an agent that, for a proposed schema change, derives the
column-level blast radius from real queries, generates the migration fix, opens a PR, and
writes the impact assessment back into DataHub. Full spec: `blast-radius-autopilot/DESIGN.md`.

Positioning: own the overlap — *"DataHub's Impact Analysis shows you the blast radius; this
defuses it."*

Category: **primary = Metadata-Aware Code Generation**, combined with **Agents That Do Real
Work** (reads via MCP, acts, writes back — it already does both). Optional **Production ML**
touch: include downstream ML models in the blast radius. Multi-category *listing* is
unconfirmed — confirm on the rules page; otherwise submit under Code Generation.

## Verified DataHub facts (do not rediscover)

- **MCP read tools:** `search`, `get_entities`, `get_lineage`, `get_lineage_paths_between`,
  `list_schema_fields`, `get_dataset_queries`.
- **MCP write tools** (set `TOOLS_IS_MUTATION_ENABLED=true`): `add_tags`,
  `add_structured_properties`, `update_description`, `add_owners`, `set_domains`,
  `save_document`. The full read→write loop runs through MCP.
- **Column-level lineage:** DataHub's SQL parser (sqlglot-based) is stated at 97–99%
  accuracy and covers Snowflake, BigQuery, Redshift, **dbt**, Looker, PowerBI. Exposed as
  `DataHubGraph.parse_sql_lineage()`. **Use that method directly — avoid `SqlParsingAggregator`**
  (not an officially supported SDK surface).
- **Parser gap:** columns used *only* in `WHERE`/`JOIN`/`GROUP BY`/`HAVING` are NOT counted
  as lineage → supplement with a raw column-reference scan over the same queries.
- **Structured properties** must be *defined once* before values can be set.
- **ML metadata** seeding mirrors `docs.datahub.com/docs/api/tutorials/ml` (MLModelGroup →
  MLModel → training run → dataset lineage).
- **Assertions/incidents** are largely DataHub *Cloud* — for OSS, prefer tags + structured
  properties + `save_document`.
- **Query-history fallback:** if `get_dataset_queries` is thin on the sample data, ingest a
  query log via the `sql-queries` connector — it generates column-level lineage from the log.

## Dataset-agnostic design (the primitives)

Every capability must run on any dataset by using only these universal primitives — never
dataset-specific columns:

| Primitive | Source |
|-----------|--------|
| Schema (columns + types) | `list_schema_fields`, `get_entities` |
| Lineage (table + column, via parser) | `get_lineage`, `parse_sql_lineage()` |
| Real queries | `get_dataset_queries` |
| Profiles / stats | dataset profile aspect |
| Ownership / freshness | `get_entities` (operation aspect) |

Adding a new dataset = point discovery at it. No code change. This is what makes the
"works with all kinds of datasets" requirement true rather than aspirational.

## Sample datasets available

`showcase-ecommerce` (Snowflake/dbt/Looker/PowerBI/Tableau, cross-platform lineage — best
for blast-radius), `nyc-taxi` (planted freshness issues), `healthcare` (synthetic — no real
PHI), `fiction-retail` (clean canvas), plus any user-provided public dataset.

## Reusable assets already in this repo

`ml-skew-sentinel/` and `data-necromancer/` are working, tested reference implementations —
reuse their repo structure, Apache-2.0 setup, MCP read/write patterns, and detector/investigator
code. **Do not modify their working cores** (see PROGRESS "Do not touch").

## Decisions log (append-only)

- 2026-07-22 — Chose Blast Radius Autopilot over Necromancer/Sentinel as the grand-prize swing.
- 2026-07-22 — Derive column impact via `parse_sql_lineage()` over pulled queries, not the
  stored graph → removes the single unverified dependency.
- 2026-07-22 — Adopted the ipv4scanner build-loop structure for this project.
- 2026-07-22 — **Primary demo dataset = `showcase-ecommerce`** (DataHub's *synthetic* sample
  catalog; chosen for its cross-platform column-level lineage). Strictly public/synthetic data
  only — never real Hattan/Masafi/company data in the repo, code, or video.
- 2026-07-22 — **No external platforms required.** Snowflake/dbt/Looker/PowerBI/Tableau are
  just labels on synthetic metadata inside the datapack — no real accounts, warehouses, or BI
  tools needed. The project reads/writes only the local DataHub instance. The dbt migration
  fix operates on SQL files in a sample git repo we control (no dbt Cloud / warehouse).
- 2026-07-22 — **Category framing finalized:** primary Code Generation + Agents That Do Real
  Work; optional ML-model-in-blast-radius touch; confirm multi-category listing on rules.
- 2026-07-23 — **Impact engine = sqlglot directly** (same engine behind DataHub's
  `parse_sql_lineage()`), so column impact is derived identically offline and online. The engine
  computes both projection usage (the lineage part) and the WHERE/JOIN/GROUP raw scan (the gap
  DataHub's parser documents it excludes). Schema-aware attribution; ambiguous unqualified columns
  across joined tables are gated to low confidence (mirrors DESIGN's `confidence_score` gate).
- 2026-07-23 — **Impact semantics.** DROP: projected=BREAKS, filter-only=DEGRADES, none=SAFE.
  RENAME: any reference=BREAKS, none=SAFE. Change-risk score 0–100 from breaks×20 + degrades×8 +
  run-weight + team-spread → LOW/MODERATE/HIGH/CRITICAL.
- 2026-07-23 — **Fix generation is formatting-preserving.** Minimal line edit for one-col-per-line
  dbt models (clean, mergeable PR diff), sqlglot regeneration as fallback; generated SQL is
  re-parsed to prove validity and the diff is checked with `git apply`. Drops that touch WHERE/JOIN
  logic are flagged for human review, never auto-rewritten (scope discipline).
- 2026-07-23 — **Write-back safe-by-default gate.** Recording an assessment is additive
  (add_structured_properties/add_tags/save_document/update_description → institutional memory on
  OSS), so it auto-writes with `--write`; `--require-review` (regulated catalogs) queues everything
  for a human. `save_document` maps to InstitutionalMemory on OSS (true save_document is Cloud).
- 2026-07-23 — **acryl-datahub 1.6.0.15 installs on Python 3.12** (warns >3.11 untested but works).
  Build/runtime venv = py3.12. System python is 3.14 (too new for acryl-datahub).
- 2026-07-23 — **LIVE round-trip verified against `datahub docker quickstart`.** Local GMS at
  `http://localhost:8080` accepts SDK writes with **no token** (quickstart). All four write-backs
  land + confirmed via GraphQL read-back: add_tags, update_description, add_structured_properties
  (**must `ensure_property_definitions()` first** — emit `StructuredPropertyDefinitionClass` with
  `valueType=urn:li:dataType:datahub.string`, `entityTypes=[urn:li:entityType:datahub.dataset]`,
  `cardinality=SINGLE`), and InstitutionalMemory (**needs a valid `AuditStamp createStamp`**, not
  None). See `blast-radius-autopilot/scripts/live_datahub_demo.py`.
- 2026-07-23 — **Loop is config-driven** (`loop.config.yaml`, YAML or JSON). `require_review` per
  catalog (or per run) queues all writes; proven across 5 datasets unchanged (dataset-agnosticism).
- 2026-07-23 — **Reports:** self-contained HTML (inline SVG lineage, status palette red/amber/green
  with glyph+label, theme-aware), CI PR comment + `open_local_pr()` (real local git PR), and a
  catalog-wide column fragility leaderboard.
- 2026-07-23 — **ENV: macOS TCC intermittently blocked `~/Desktop`** for this automation mid-build
  (read/list/overwrite denied, new-create allowed), then recovered. Canonical dev+test tree kept at
  `~/bra/blast-radius-autopilot` and rsync'd to Desktop. Lesson for future loops: keep the runnable
  tree outside protected macOS folders (Desktop/Documents/Downloads) or grant Full Disk Access.
