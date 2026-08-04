# Devpost submission — copy-paste ready

All numbers below are the verified ones. Replace `<...>` placeholders before submitting.

---

## Project name

**Blast Radius Autopilot**

*(Alternates if you want distance from DataHub's own term: "Schema Change Autopilot",
"Proof-Carrying Migrations".) Recommendation: keep Blast Radius Autopilot — owning DataHub's
own vocabulary and then showing what it adds is more disarming than renaming around it.*

## Tagline (one line)

DataHub's Impact Analysis shows you the blast radius of a schema change. Blast Radius Autopilot
defuses it — then proves its own fix before anything is written.

## Category

**Metadata-Aware Code Generation & Development** (primary) — it reads DataHub for the real
schemas, lineage and SQL before generating anything, and the artifact is a git diff a data team
would merge. It also satisfies **Agents That Do Real Work** (reads via MCP, acts, writes results
back so the next person inherits them).

---

## About the project

### The problem

Dropping or renaming one column quietly breaks dashboards, dbt models and ad-hoc queries across
teams. You find out afterwards. DataHub's Impact Analysis already shows you *what is downstream* —
that part is shipped, and we don't claim to have invented it. What it doesn't do is **act** on that
knowledge: it won't write the migration, it won't check whether the migration actually worked, and
it won't record the verdict for the next engineer.

### What Blast Radius Autopilot does

Given a proposed change — `drop order_entry.orders.promotion_id`:

1. **Reads DataHub** — schema, downstream lineage, ownership, query history and downstream SQL
   definitions, over the official **DataHub MCP server**.
2. **Computes column-level impact** — a sqlglot column-usage engine over the real SQL classifies
   every consumer **BREAKS / DEGRADES / SAFE / UNKNOWN**. It also catches columns referenced only in
   `WHERE`/`JOIN`/`GROUP BY` — which DataHub's SQL parser documents that it excludes — so the view is
   more complete than lineage alone.
3. **Generates the migration fix** — a mechanical dbt drop/rename producing a clean, applicable
   git diff. Consumers no mechanical fix can reach (BI tools, ad-hoc SQL) are surfaced for manual
   review rather than silently "fixed".
4. **Proves the fix — proof-carrying migrations.** The patch is applied in an isolated copy, every
   patched file is re-parsed, and impact is **recomputed** on the patched corpus. The before/after
   comparison yields **PASS / REVIEW_REQUIRED / FAIL** over a sixteen-clause conjunction, every
   clause named. A generated fix is never trusted — it is verified.
5. **Gates every write.** No PASS, no automatic write. A REVIEW_REQUIRED run emits a **single-use
   approval manifest** bound to that change, verdict and queued set; a human approves it explicitly
   and their identity is recorded. A **FAIL can never be approved by any route.**
6. **Contributes back to the graph** — structured properties (risk, breaks, degrades, coverage,
   verification status), impact tags on affected downstreams, a pending-change footer, a link to the
   full Impact Assessment, and the **human-approval audit trail** (who approved, when, against which
   verdict, under which manifest) — all written into DataHub and read back over GraphQL.
7. **Reports** — a self-contained visual HTML report, a CI-style PR comment, a grounded
   step-by-step migration plan, and a catalog-wide column-fragility leaderboard.

### The design principle

**Missing evidence must never read as proof of safety.** Every safety decision in the tool follows
from that. Two real false negatives we found and fixed prove we mean it:

- A SQL **parse failure** was being scored `SAFE / confidence high`. On a live run this filed a
  Jinja-templated dbt model as safe while it referenced the target column four times, making the
  whole run read LOW risk. Parse failures are now a distinct **UNKNOWN** verdict — never safe, never
  inflated into a break, and they block PASS.
- A dropped column referenced **only in a `WHERE`** was graded DEGRADES. Dropping it makes the query
  *error*. Any resolved reference is now **BREAKS**; DEGRADES is reserved for "executes fine, output
  changes" (`SELECT *` losing a column).

Coverage is reported as its own dimension — *"CRITICAL among assessed · 6 of 24 analysed"* — never
folded into a reassuring score.

### How we used DataHub

- **MCP Server** (`mcp-server-datahub`) — target discovery and all reads: `search`, `get_entities`,
  `list_schema_fields`, `get_lineage`, `get_dataset_queries`. On the live run the agent discovered
  its own target over MCP (ranking all 78 datasets by downstream fan-out) rather than being pointed
  at one.
- **Write-back** — structured properties, tags, editable description, institutional-memory link,
  and the approval audit trail; verified by an independent GraphQL read-back.
- **Sample data** — the official `showcase-ecommerce` datapack, plus nyc-taxi, healthcare, retail
  and finance examples (all public or synthetic).
- **Open-source contribution** — the impact engine is packaged as a reusable **DataHub Skill**
  (`column-impact-from-queries`, Apache-2.0) and submitted upstream to `datahub-skills`.

### What is verified

- **181 tests passing**, written failing-first for every safety property (each defect above was
  reproduced as a failing test before it was fixed).
- **Live DataHub round-trip** — writes applied and read back over GraphQL.
- **Live MCP end-to-end run** on the real datapack: `ORDER_DETAILS`, 55 columns, 24 downstream
  consumers across 6 platforms. MCP pull ~11.5 s; column analysis ~14 ms.
- **All three verdicts on real runs** — a PASS (breaks 2 → 0, every gate independently satisfied),
  a REVIEW_REQUIRED (breaks 6 → 5; the rest are BI consumers no mechanical fix reaches), and a FAIL
  (breaks unchanged because two Tableau consumers use the column in `WHERE`/`GROUP BY`, which fix
  generation deliberately never rewrites).
- **Five dataset types** through the same code path — the regulated (healthcare, finance) examples
  route every write to human review.

### Honest limits

Verification is **static**: the patch applies, the SQL parses, impact is recomputed. **No query is
executed** — no warehouse is contacted, no data is read, no dbt build runs. It is evidence about SQL
text, not runtime behaviour.

Only consumers that expose parseable SQL can be assessed; on the live run that was **6 of 24**, and
the other 18 were reported as unassessed rather than assumed safe. The datapack ships no query
history, so that run's corpus was the real SQL definitions read over MCP — stated plainly in the
output. Remaining scope boundaries (approval-manifest payload binding, partial-failure retry, the
single-operator assumption) are documented in `LIMITATIONS.md` rather than left for a reader to
find.

### Try it

Runs offline in one command, no DataHub required:

```bash
pip install -e .
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" \
          --verify --plan --html out/report.html
```

Against a live instance: `--online --target-urn "<urn>" --verify --write`.

---

## Built with

`python` · `datahub` · `mcp` · `mcp-server-datahub` · `sqlglot` · `dbt` · `graphql` · `docker`
· `pytest`

## Links to fill in

- Repo: `<public GitHub URL — Apache-2.0 visible in About>`
- Video (<3 min, public): `<YouTube/Vimeo URL>`
- DataHub Skill PR: `<datahub-skills PR URL>`
