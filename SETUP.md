# SETUP.md — Local DataHub for the build loop

The one-time setup from the DataHub welcome email, plus the bits it leaves out. This runs
**on your machine** (the agent can't reach your localhost), so you run these; report the
results back and the loop proceeds from task **B0** in `BACKLOG.md`.

## 0. Prerequisites (the email skips these)

- **Docker Desktop installed and running** — `datahub docker quickstart` needs it. Give it
  ~8 GB RAM in Docker settings; DataHub is several containers.
- **Python 3.10+** — `python3 --version`.

## 1. Install + start DataHub (~20 min)

```bash
pip install acryl-datahub
datahub docker quickstart          # pulls + starts the stack; first run is slow
```

Open **http://localhost:9002** — login **datahub / datahub** (default *local dev* creds;
fine locally, never reuse them elsewhere or commit them).

GMS/API runs on **http://localhost:8080**.

## 2. Load sample data to build against

```bash
datahub datapack load showcase-ecommerce   # Snowflake/dbt/Looker/... cross-platform lineage
# optional lightweight starter:
datahub datapack load bootstrap
```

## 3. Create a token + fill .env

DataHub UI → **Settings → Access Tokens → Generate**. Copy it into the project `.env`
(see `.env.example`). The `.env` is gitignored — **the token never goes into the repo.**

## 4. Wire the MCP server (reads + writes)

Point the DataHub MCP server at your local GMS and **enable mutation tools** so the agent can
write back:

```
DATAHUB_MCP_URL=http://localhost:8080/mcp
TOOLS_IS_MUTATION_ENABLED=true
```

Setup/config per the MCP server docs: https://github.com/acryldata/mcp-server-datahub
(there's an official "Claude (Code & Desktop)" connection guide too).

## 5. Task B0 — the check that unblocks everything

In the UI, open a well-connected `showcase-ecommerce` asset, then:

1. **Query history** — call `get_dataset_queries` on it (via MCP, or check the asset's
   Queries tab). Does real SQL history come back?
   - **Yes** → the blast-radius core has queries to parse. Proceed to B1.
   - **Thin/empty** → run the fallback: ingest a query log via the `sql-queries` connector
     (generates column-level lineage from the log). Then proceed.
2. **Sanity** — confirm `parse_sql_lineage()` returns column lineage for one real query.

Report back what B0 returns (query history present? did you need the fallback?) and the loop
starts building B1.

## Help

`#agent-hackathon` in DataHub Slack — the DataHub team and other builders are there.
