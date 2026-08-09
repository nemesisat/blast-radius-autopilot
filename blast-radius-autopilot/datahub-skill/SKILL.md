---
name: column-impact-from-queries
description: >
  For a proposed column change (drop/rename) on a dataset, compute evidence-backed
  column-level impact from available query history and downstream SQL definitions —
  classifying every downstream consumer as BREAKS / DEGRADES / SAFE / UNKNOWN, and
  reporting ambiguous references separately. Unlike viewing stored lineage, this
  parses the actual SQL and also catches columns used only in WHERE/JOIN/GROUP BY
  (which DataHub's SQL parser documents it excludes), so the impact view is more
  complete — and it says plainly which consumers it could not assess.
license: Apache-2.0
version: 0.1.0
homepage: https://github.com/nemesisat/blast-radius-autopilot
tags: [impact-analysis, lineage, schema-change, code-generation, dbt]
---

# column-impact-from-queries

A reusable DataHub **Skill**: given `{dataset, column, op}`, it reads the dataset's
schema, downstream lineage, and available query history plus downstream SQL definitions,
then runs a column-usage engine (sqlglot — the same engine behind DataHub's
`parse_sql_lineage()`) over each definition to decide how the change lands. It computes
evidence-backed column-level impact while **explicitly flagging unparseable and non-SQL
consumers for review** rather than assuming they are unaffected.

**Four states, not three.** `BREAKS` · `DEGRADES` · `SAFE` · `UNKNOWN`. A consumer whose
SQL will not parse (e.g. an unrendered dbt Jinja model) or which exposes no SQL at all
(PowerBI measures, Looker views) is `UNKNOWN` — never `SAFE`. UNKNOWN does not count as
safe, does not count as a break, does not move the risk score, and forces the whole run
to `review_required`. Coverage is returned alongside the verdict (`"5 of 24 analysed"`)
so callers can tell a complete assessment from a partial one.

**Plus one cross-cutting signal: `ambiguous`.** An unqualified column that more than one
joined table provides parsed fine and the column *was* found — we simply cannot prove which
table it came from. That is a different failure of knowledge from `UNKNOWN` (which means we
could not read the consumer at all), so it is reported on its own axis: never counted as
safe, never inflated into a break, never moving the risk score — and it also forces
`review_required`, because the reference is real and only its attribution is open. When
coverage is complete but something is unattributed, `level_qualifier` says so:
`"CRITICAL with 1 unresolved reference(s)"`.

## When to use
- Before dropping or renaming a column, to see which dashboards / models / queries break,
  degrade, or are safe — which could not be assessed at all, which carry a reference that
  cannot be attributed — and which teams own them.
- In CI on a dbt/schema PR, to post the blast radius as a comment.

## Inputs
| field | required | example |
|---|---|---|
| `dataset` | yes | `analytics.fct_orders` (sql name / urn) |
| `column` | yes | `customer_zip` |
| `op` | yes | `drop` \| `rename` |
| `new_name` | if rename | `postal_code` |
| source | yes | either `--online --target-urn <urn>` (live DataHub) or `--catalog <catalog.json>` (offline) |

## Output (JSON)

Verbatim from `skill.py --catalog examples/showcase-ecommerce/catalog.json --dataset
analytics.fct_orders --column customer_zip --op drop` (2026-07-30), abridged only where marked:

```json
{
  "change": "drop analytics.fct_orders.customer_zip",
  "catalog": "showcase-ecommerce",
  "counts": {"breaks": 6, "degrades": 0, "safe": 3, "unknown": 0, "ambiguous": 1,
             "queries_total": 10, "analysed": 10, "unassessed": 0,
             "runs_impacted": 41, "teams": 3},
  "risk": {"score": 100, "level": "CRITICAL", "review_required": true,
           "coverage": "10 of 10 analysed", "unassessed": 0, "ambiguous": 1,
           "level_qualifier": "CRITICAL with 1 unresolved reference(s)"},
  "verdicts": [{"query_id": "...", "verdict": "BREAKS", "usage": "select",
                "confidence": "high", "team": "...", "reason": "..."}]
}
```

Note `review_required: true` on a catalog with **complete** coverage: every query parsed, but one
column reference could not be attributed to a source table. Coverage and confidence are separate
axes, and either one being short blocks auto-apply.

## Run
```bash
pip install blast-radius-autopilot
python skill.py --catalog examples/showcase-ecommerce/catalog.json \
                --dataset analytics.fct_orders --column customer_zip --op drop
# or against a live instance:
python skill.py --online --target-urn "urn:li:dataset:(...)" \
                --dataset analytics.fct_orders --column customer_zip --op drop
```

## Why it's a meaningful contribution
Viewing downstream lineage is shipped in DataHub. Deriving **column-level** impact
from real queries — including the filter/join usage the parser skips — and returning
it as a structured, CI-postable verdict is the reusable primitive this skill adds.

_Public/synthetic data only in examples. Never commit real/production data._
