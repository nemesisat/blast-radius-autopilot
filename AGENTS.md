# AGENTS.md — Build Loop Operating Manual

This project is built by an autonomous coding loop (Claude Code / Codex, task by task),
run the same way the ipv4scanner redesign was: **structured task-prompts + a living guide
+ strict verify-and-report discipline, so knowledge compounds and nothing regresses.**

The loop's job is to build **Blast Radius Autopilot** (see `blast-radius-autopilot/DESIGN.md`)
to a submittable state for the DataHub Agent Hackathon.

## The loop — one cycle = one task

1. **PICK** — take the top unblocked task from `BACKLOG.md`.
2. **DIAGNOSE** (if it's a bug) — find the actual cause first. Do **not** fix on a guess;
   if the cause isn't obvious, report the diagnosis before changing code.
3. **IMPLEMENT** — one task, on its own branch. Small and reviewable.
4. **VERIFY** — prove it works with evidence: run the tests; for any DataHub read/write,
   verify against a live/demo instance (or a dry-run with captured output). **Never mark a
   task done without evidence.**
5. **RECORD** — update `BUILD_GUIDE.md` with any new decision/fact (so it's never
   rediscovered), tick the task in `BACKLOG.md`, log it in `PROGRESS.md`.
6. **REPORT** — hand back a short verification checklist per task. Queue several and let the
   human review in batches; surface anything needing a decision immediately.
7. **REPEAT.**

## Standing rules

- **One task per branch.** Implement + verify each before the next.
- **Verify every change with evidence** — the "contrast-audit habit": for every new thing,
  run the relevant quality gate (unit test, a real query, a dry-run diff) *before* claiming
  done. Assume nothing passes until shown.
- **Diagnose before fix.** No blind edits.
- **Keep `BUILD_GUIDE.md` current.** It is the loop's memory. If a fact was hard-won
  (an API quirk, a verified tool name), write it down so the next cycle doesn't rediscover it.
- **Dataset-agnostic — non-negotiable.** Every capability must work on *any* dataset type
  via the generic metadata primitives (see `BUILD_GUIDE.md`). No hardcoding to one sample.
  Ship working examples across **≥5 dataset types** (`EXAMPLES.md`).
- **Public data only.** Writes go into whatever catalog is connected — use DataHub's demo
  instance or the hackathon sample data, never real/production data.
- **Approve-before-write + confidence-gate.** Only strongly-evidenced changes auto-write;
  everything else is queued for human review.
- **Protected list.** Never touch items under "Do not touch" in `PROGRESS.md`.
- **Report** when a batch is done, or sooner if a decision is needed.

## Structured task-prompt template

Every task handed to the loop uses this shape (same format as the ipv4scanner prompts):

```
Task <ID> — <title>   (P0 | P1)
Context: <1–2 lines> + see BUILD_GUIDE.md §<section>
Do:
  1. <step>
  2. <step>
Verify: <exact checks / evidence required to call it done>
Rules: one branch; diagnose before fix; dataset-agnostic; public data only.
Report: <what to hand back — checklist + evidence>. Don't touch <protected>.
```

## The files that make up this structure

| File | Role |
|------|------|
| `AGENTS.md` | This manual — how the loop operates. |
| `BUILD_GUIDE.md` | Living spec + verified facts (the loop's memory). |
| `BACKLOG.md` | Prioritized task list with IDs and status. |
| `PROGRESS.md` | What's done + verified, and the "Do not touch" list. |
| `EXAMPLES.md` | The ≥5 dataset examples the loop must produce/maintain. |
