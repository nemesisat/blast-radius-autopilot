# DataHub Agent Hackathon — Project Workspace

Workspace for **Build with DataHub: The Agent Hackathon** (deadline Aug 10, 2026).
Primary submission: **Blast Radius Autopilot**.

## The build loop (start here)

This project runs on an autonomous build loop with a living guide, a backlog, and strict
verify-and-report discipline — the same structure used on the ipv4scanner project.

| File | What it's for |
|------|---------------|
| [`AGENTS.md`](AGENTS.md) | How the loop operates — the cycle, the rules, the task-prompt template. |
| [`BUILD_GUIDE.md`](BUILD_GUIDE.md) | Living spec + verified DataHub facts (the loop's memory). |
| [`BACKLOG.md`](BACKLOG.md) | Prioritized tasks with IDs and status. |
| [`PROGRESS.md`](PROGRESS.md) | What's done + verified, and the "Do not touch" list. |
| [`EXAMPLES.md`](EXAMPLES.md) | The ≥5 dataset examples proving it works on any dataset. |

## Projects in this workspace

- **`blast-radius-autopilot/`** — primary submission. Computes evidence-backed column-level change
  impact from available query history and downstream SQL definitions, generates the migration fix,
  **statically verifies its own patch**, and contributes the assessment back to the catalog.
  See its `README.md`.
- **`ml-skew-sentinel/`** — built + tested reference: catches training/serving skew from ML
  lineage. Reused as the drift analyzer.
- **`data-necromancer/`** — built + tested reference: reconstructs docs and detects *zombie*
  metadata. Reused as the metadata analyzer.
- **`docs/`** — background build plans.

## Working agreement

- Every capability is **dataset-agnostic** and **public-data-only**.
- Nothing is "done" without evidence (a passing test or a captured run).
- The loop keeps `BUILD_GUIDE.md` and `PROGRESS.md` current so knowledge compounds.

## Current status

**Backlog complete (B0–B19; B17.8 skipped by decision). Feature work closed.** Blast Radius
Autopilot: **166 tests passing**, a live DataHub read+write loop verified, a live-MCP end-to-end run
on the real `showcase-ecommerce` datapack, hardened proof-carrying migrations — static verification
issuing PASS / REVIEW_REQUIRED / FAIL over a sixteen-clause PASS conjunction, gating every catalog
write — and a single-use human-approval path for the REVIEW_REQUIRED case, bound to the change,
verdict and queued set. **No PASS, no automatic write; a FAIL can never be approved.** The
binding's exact scope and the risks it does *not* cover are documented in
[`blast-radius-autopilot/LIMITATIONS.md`](blast-radius-autopilot/LIMITATIONS.md).
See [`PROGRESS.md`](PROGRESS.md) for the evidence and [`BACKLOG.md`](BACKLOG.md) for what each task
closed. Remaining items are human-only (GitHub auth, the demo recording) — listed at the end of
`PROGRESS.md`.
