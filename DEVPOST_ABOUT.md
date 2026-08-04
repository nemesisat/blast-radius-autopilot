# Devpost — "About the project" (paste as Markdown)

---

## Inspiration

Every data engineer has done this: you drop one column, and three days later someone asks why the
executive dashboard has been blank since Tuesday. The change looked local. It wasn't.

DataHub already answers *"what is downstream of this?"* — its Impact Analysis is a shipped feature,
and we're not claiming to have invented it. What it doesn't do is **act** on that answer. It won't
write the migration, it won't check whether the migration actually worked, and it won't remember the
verdict for the next person who touches that table.

So we set out to build the layer that acts: an agent that reads DataHub, works out exactly what a
proposed schema change breaks, writes the fix, and — the part we didn't expect to become the whole
project — **proves its own fix before anything is allowed to be written**.

## What it does

Given `drop order_entry.orders.promotion_id`, the agent:

1. reads schema, lineage, ownership, query history and downstream SQL over the **DataHub MCP server**;
2. classifies every consumer **BREAKS / DEGRADES / SAFE / UNKNOWN** using a `sqlglot` column-usage
   engine over the real SQL — including columns referenced only in `WHERE`/`JOIN`/`GROUP BY`, which
   DataHub's own parser documents that it excludes;
3. generates a mechanical dbt migration fix as a clean git diff;
4. **verifies that fix**: applies it in an isolated copy, re-parses every patched file, recomputes
   impact on the patched corpus, and issues **PASS / REVIEW_REQUIRED / FAIL** over a sixteen-clause
   conjunction;
5. **gates every catalog write on that verdict** — no PASS, no automatic write; a human can approve a
   REVIEW_REQUIRED via a single-use manifest; a FAIL can never be approved;
6. writes the assessment, the impact tags, the risk properties and the **human-approval audit trail**
   back into DataHub, where the next engineer inherits them.

## How we built it

Python, `sqlglot` for the column-usage engine (the same parser generation behind DataHub's own
`parse_sql_lineage()`), the official `mcp-server-datahub` for reads, the DataHub Python SDK +
GraphQL for the write-back, and a local `datahub docker quickstart` loaded with the official
`showcase-ecommerce` datapack for live testing.

Two architectural decisions carried the whole build:

**Offline-first.** Every capability runs against JSON fixtures that mirror the MCP read surface, so
the entire test suite (now **181 tests**) executes with no DataHub instance at all. A live instance
became a *stronger* evidence path, never a prerequisite. That decision saved the project on the day
Docker wasn't running.

**Metadata-only.** The agent never reads a single row of data — only schemas, lineage, query text and
ownership. A 6 TB table and a 6 MB table look identical to it. On the live run, the MCP pull took
~11.5 s and the entire column analysis took **14 ms**.

We also built it under a discipline that turned out to matter more than any feature: **every fix was
written as a failing test first**, and nothing was recorded as done without either a passing test or
a captured run.

## Challenges we ran into

### The tool was lying to us — twice

The live MCP run against the real datapack is what exposed it. Our analyzer reported the `ADDRESSES`
table as **LOW risk**. It wasn't. A Jinja-templated dbt model failed to parse, and the failure was
being scored as `SAFE` with confidence `high` — while that model joined `addresses` and referenced
the target column **four times**. A parse failure had been quietly promoted into a clean bill of
health.

The second was subtler. A dropped column referenced only in a `WHERE` clause was graded `DEGRADES`.
But dropping a column that a `WHERE` names doesn't degrade the query — it makes it **error**.

Both were fixed test-first, and they reshaped the project around one rule:

> **Missing evidence must never read as proof of safety.**

Parse failures became a distinct fourth verdict, `UNKNOWN` — never counted safe, never inflated into
a break, and it blocks any PASS. Coverage became its own reported dimension
(*"CRITICAL among assessed · 6 of 24 analysed"*) instead of being folded into a reassuring score.

### Then the verifier had the same disease

Once we had a verifier issuing PASS, we went looking for ways it could say PASS while real impact was
still unresolved. We found several, each reproduced as a failing test before it was fixed: an
ambiguous column reference surviving into a PASS; a pre-existing `DEGRADES` surviving into a PASS; a
patched file that mapped to no query in the corpus (so its effect was never actually recomputed); a
diff that *deleted* a consumer's SQL file, which made the consumer's references vanish and earned it
a clean verdict; a target dataset that didn't exist, producing a confident PASS over zero consumers.

The PASS conjunction ended up with sixteen named clauses, all of which must hold, in a single place
in the code — because we learned that a verdict synthesised in two places will eventually disagree
with itself.

### The catalog couldn't store what we claimed

We had been saying the full Impact Assessment was written into DataHub. We probed the actual aspect
rather than trusting the claim: open-source DataHub's `InstitutionalMemoryMetadata` is
`{url, description, createStamp, updateStamp, settings}` — there is **no field that can hold a
document body**. We had been building the content and dropping it.

We didn't fake it and we didn't smuggle the markdown into the description field. The body is
persisted to a file, the catalog stores the link and title, and every surface now says exactly which
is which — enforced by a test that fails the build on any wording claiming otherwise.

### The honest result wasn't the flattering one

The datapack ships **no query history** (`get_dataset_queries` returns 0), and only **6 of 24**
downstream consumers expose parseable SQL — PowerBI measures and Looker views can't be assessed by a
SQL parser at all. We report those 18 as *unassessed*, not safe.

And on the live target, verification returns **FAIL**: two Tableau consumers use the column in
`WHERE` and `GROUP BY`, which our fix generation deliberately refuses to rewrite. A tool that only
demoed green would have been more impressive and less true. We ship all three verdicts on real runs.

## Accomplishments we're proud of

- **181 passing tests**, every safety property written failing-first.
- A **live DataHub round-trip** verified by independent GraphQL read-back — including the approval
  audit trail (who approved, when, against which verdict, under which manifest).
- **All three verdicts on real runs**: a PASS (breaks 2 → 0, every gate independently satisfied), a
  REVIEW_REQUIRED (breaks 6 → 5), and a FAIL that correctly refuses to certify an incomplete fix.
- The same code path across **five very different dataset types**, with the regulated examples
  (healthcare, finance) routing every write to human review.
- A `LIMITATIONS.md` that documents our own residual risks rather than leaving them to be found.

## What we learned

That the hard part of an agent that writes to your catalog isn't the writing — it's **earning the
right to write**. Most of our engineering went into the difference between *"I found no problem"*
and *"there is no problem."* Those are not the same sentence, and a tool that conflates them is
worse than no tool, because it launders uncertainty into confidence.

We also learned to distrust our own green checkmarks. Every one of the defects above was found by
running against real metadata and then asking *"how could this verdict be wrong?"* — never by the
test suite passing.

## What's next

Per-mutation payload hashing so a reviewer's rendering is cryptographically identical to what
executes; retry manifests for partial failures; atomic state and idempotency keys for the
multi-operator case; a CI mode that posts the blast radius on any PR touching a schema and fails the
check on CRITICAL; and pre-rendering dbt Jinja so templated models become analysable instead of
UNKNOWN.

**And the boundary we won't blur:** verification here is *static*. The patch applies, the SQL parses,
impact is recomputed. **No query is executed** — no warehouse is contacted, no data is read, no dbt
build runs. It is evidence about SQL text, not runtime behaviour. Saying so plainly is the point.
