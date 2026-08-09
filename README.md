# Blast Radius Autopilot

> **DataHub's Impact Analysis shows you the blast radius of a schema change.
> Blast Radius Autopilot _defuses_ it — then checks its own work.**

Viewing downstream lineage is a shipped DataHub feature, and we're not claiming to have invented
it. What it doesn't do is **act**: it won't write the migration, it won't check whether the
migration actually worked, and it won't record the verdict for the next engineer. That's this.

Built for **Build with DataHub: The Agent Hackathon**.
📺 **[3-minute demo](https://www.youtube.com/watch?v=-DOwanGh9oM)** ·
🔎 **[Browse real output — no install](https://nemesisat.github.io/blast-radius-autopilot/)** ·
📦 [Apache-2.0](LICENSE) · ✅ 198 tests

---

## What it does

Given a proposed change — `drop analytics.fct_signups.referrer_code`:

1. **Reads DataHub over the MCP server** — schema, downstream lineage, ownership, query history
   and downstream SQL definitions.
2. **Computes column-level impact** — a `sqlglot` column-usage engine over the real SQL classifies
   every consumer **BREAKS / DEGRADES / SAFE / UNKNOWN**, including columns referenced only in
   `WHERE` / `JOIN` / `GROUP BY`.
3. **Generates the migration fix** — a mechanical dbt drop/rename as a clean, applicable git diff.
4. **Verifies its own fix** — applies the patch to an *isolated copy*, re-parses every patched
   file, recomputes impact, and issues **PASS / REVIEW_REQUIRED / FAIL** over a sixteen-clause
   conjunction.
5. **Gates every catalog write on that verdict** — no PASS, no automatic write. A human can approve
   a REVIEW_REQUIRED through a single-use manifest; a **FAIL can never be approved**.
6. **Writes back to DataHub** — risk properties, impact tags, a link to the assessment, and the
   human-approval audit trail (who approved, when, against which verdict).
7. **Sweeps the whole catalog** — a read-only ledger of every candidate column change:
   verified-safe (patch attached), needs-review, landmine, unassessed. **43 columns across six
   catalogs in 0.65 seconds.**

## Try it — 30 seconds, no DataHub required

```bash
cd blast-radius-autopilot
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# impact + generated fix + self-verification
autopilot --catalog examples/verified-migration/catalog.json \
          --change "drop analytics.fct_signups.referrer_code" --verify
# → ✅ PASS · breaks 2 → 0 · coverage 3 of 3

# the whole catalog, read-only
autopilot --sweep --catalog examples/showcase-ecommerce/catalog.json

pytest    # 198 passed
```

Against a live instance: `--online --target-urn "<urn>" --verify --write`
(setup in [`SETUP.md`](SETUP.md)).

## The design rule

> **Missing evidence must never read as proof of safety.**

Two verified false negatives shaped the whole project. A SQL parse failure was being scored
`SAFE / confidence high` — on a live run it filed a Jinja-templated dbt model as safe while that
model referenced the target column four times. And a dropped column referenced only in a `WHERE`
was graded `DEGRADES`, when dropping it actually makes the query *error*.

Both were fixed test-first. Parse failures became a distinct fourth verdict, **UNKNOWN** — never
counted safe, never inflated into a break, and it blocks any PASS. Coverage is reported as its own
dimension (*"CRITICAL among assessed · 6 of 24 analysed"*) rather than folded into a reassuring
score.

## What verification does and does not prove

**Proves:** the patch applies cleanly in isolation, every patched SQL file re-parses, the diff
stayed in scope, and the analyzer can no longer find a broken or unassessed consumer.

**Does not prove:** that anything ran. **No query is executed** — no warehouse is contacted, no
data is read, no dbt build is invoked. It is evidence about SQL text, not runtime behaviour.

Residual risks are documented in [`blast-radius-autopilot/LIMITATIONS.md`](blast-radius-autopilot/LIMITATIONS.md)
rather than left to be discovered.

## Repository layout

| Path | What it is |
|---|---|
| **[`blast-radius-autopilot/`](blast-radius-autopilot/)** | **The submission.** Source, 198 tests, examples, captured runs. Start with its [README](blast-radius-autopilot/README.md). |
| [`blast-radius-autopilot/datahub-skill/`](blast-radius-autopilot/datahub-skill/) | `column-impact-from-queries` — the impact engine packaged as a reusable **DataHub Skill** (Apache-2.0), submitted upstream. |
| [`blast-radius-autopilot/out/`](blast-radius-autopilot/out/) | Captured runs, HTML reports, sweep ledger, live-DataHub evidence. Indexed by its own README. |
| [`ml-skew-sentinel/`](ml-skew-sentinel/) · [`data-necromancer/`](data-necromancer/) | Earlier built-and-tested agents from the same effort; their detector and investigator patterns were reused here. |

## How it was built

Python · `sqlglot` · the official `mcp-server-datahub` · DataHub Python SDK + GraphQL ·
`datahub docker quickstart` with the official `showcase-ecommerce` datapack.

Two decisions carried it: **offline-first** (the whole suite runs with no DataHub instance, so a
live instance is stronger evidence rather than a prerequisite) and **metadata-only** (the agent
never reads a row of data — a 6 TB table and a 6 MB table look identical to it, which is why the
catalog-wide sweep costs under a second).

The build itself ran on a documented agent loop — [`AGENTS.md`](AGENTS.md) is the operating manual,
[`BACKLOG.md`](BACKLOG.md) the task list, and [`PROGRESS.md`](PROGRESS.md) the evidence log where
nothing is marked done without a passing test or a captured run.

## License

Apache-2.0. All example data is public or synthetic — no real, production or company data.
