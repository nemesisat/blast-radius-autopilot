# BACKLOG.md — Prioritized Tasks

Status: ☐ todo · ◐ in progress · ☑ done · ⏸ blocked. **ALL TASKS COMPLETE (B0–B13).**
Evidence in `PROGRESS.md`. **39 tests green** + live DataHub read+write verified.

## P0 — path to a working end-to-end demo

- ☑ **B0 — Confirm query history / fallback.** Live DataHub down at start → blessed fallback:
  seeded synthetic `examples/showcase-ecommerce/` (catalog + query log). *Verified:* 10 queries
  reference `analytics.fct_orders` across 4 teams.
- ☑ **B1 — Scaffold `blast-radius-autopilot/`.** Apache-2.0 LICENSE, README, pyproject (src
  layout), `.env.example`, `.gitignore`. *Verified:* `pip install -e .` + `import autopilot` OK.
- ☑ **B2 — Read layer** (`catalog.py`). Offline JSON loader + online `DataHubCatalogReader`
  (schema/lineage/queries → MCP/SDK). *Verified:* loads the showcase catalog (2 datasets, 5 assets).
- ☑ **B3 — Impact core** (`lineage.py` + `impact.py`). sqlglot column-usage engine + WHERE/JOIN
  raw scan; BREAKS/DEGRADES/SAFE with confidence gate. *Verified:* `test_lineage.py` 13/13,
  `test_impact.py` 5/5.
- ☑ **B4 — Fix generation** (`fixgen.py`). Mechanical dbt drop/rename; clean minimal diff.
  *Verified:* `test_fixgen.py` 3/3 incl. `git apply --check`.
- ☑ **B5 — Write-back (gated)** (`writeback.py` + `assessment.py`). Approve-before-write;
  `--require-review` queues regulated data. *Verified:* `test_writeback.py` 4/4 + live round-trip.
- ☑ **B10 — Tests.** Full suite covers impact + WHERE/JOIN supplement + fixgen + write-back +
  reports + loop + skill. *Verified:* `pytest` → **39 passed**.

## P1 — dataset breadth, polish, bonus

- ☑ **B6 — Dataset-agnostic loop runner** (`loop.py` + `loop.config.yaml`). *Verified:*
  `test_loop.py` 5/5; `--loop` runs 5 datasets unchanged (see `examples/CAPTURED_RUNS.md`).
- ☑ **B7 — Powerful examples (≥5 dataset types).** showcase-ecommerce, nyc-taxi, healthcare
  (synthetic), fiction-retail, finance (synthetic). *Verified:* all 5 run end-to-end; captured.
- ☑ **B8 — Demo video script + README polish.** `demo/demo_script.md` (<3-min); overlap-first README.
- ☑ **B9 — OSS Skill.** `datahub-skill/` (SKILL.md + runnable `skill.py`), Apache-2.0. *Verified:*
  `test_skill.py`. **Upstream PR to `datahub-skills` = human-only (GitHub auth) — see PROGRESS.**

## P2 — reporting (added 2026-07-23)

- ☑ **B11 — Visual HTML Blast Radius report** (`report_html.py`). Self-contained; inline-SVG lineage
  graph (red/amber/green nodes + glyph+label), scorecard, teams, migration diff; theme-aware.
  *Verified:* `test_reports.py`; rendered + screenshotted.
- ☑ **B12 — PR-comment report** (`report_pr.py`). CI-style comment + `open_local_pr()` (real local
  git PR). *Verified:* `test_reports.py`.
- ☑ **B13 — Catalog Fragility leaderboard** (`fragility.py`). Ranks riskiest columns catalog-wide.
  *Verified:* `test_fragility.py` 4/4; text + HTML + screenshot.
- ☑ **B14 — Grounded Migration Planner** (`planner.py`). Turns the impact result into a
  step-by-step safe-change plan — DERIVED FACTS ONLY (topologically-ordered steps: models →
  BI last, each with owner + BREAKS/DEGRADES + action + labeled parser confidence; teams;
  tests = impacted downstreams; rollback references the generated PR; risk from impact).
  Effort/timeline/deploy window are explicit "⟨human to decide⟩" placeholders, never computed.
  `--plan` in run.py (writes MIGRATION_PLAN.md) + a grounded section in the HTML report; optional
  `phrase_with_llm` rewords only (gated on ANTHROPIC_API_KEY). *Verified:* `test_planner.py` 6/6
  incl. a guard asserting NO fabricated tokens (no hour/day/%/numeric-confidence); full suite
  **45 passed**; flagship run captured (`out/migration_plan_run.txt`) + HTML + screenshot
  (`out/live_ui/06_migration_plan.png`).

## P0 — correctness (added 2026-07-30)

- ☑ **B15 — Safety semantics: missing evidence must never read as proof of safety.** Fixed two
  VERIFIED correctness defects found by the 2026-07-29 live-MCP run, test-first.
  - **Defect 1 (false negative, verified in production data):** a SQL parse failure was scored
    **SAFE / confidence "high"**. `lineage.py` set `usage="none", confidence="low"` on ParseError,
    then `impact.py` overwrote confidence back to `"high"` because `usage=="none"`, and "none" maps
    to SAFE. On the live ADDRESSES run this filed the Jinja-templated dbt `order_details` model as
    SAFE while that model **joins addresses and references `country_id` 4×** — making the whole run
    read risk LOW. **Fix:** `parse_error` is now a distinct usage state carried end-to-end to a new
    fourth verdict `UNKNOWN`, confidence stays `low`, and the `"none"`→high promotion applies only
    to a *parsed, proven* non-reference.
  - **Defect 2 (severity mis-grade):** on a DROP, a reference resolving to the column but sitting
    only in WHERE/JOIN/GROUP/HAVING/ORDER was called DEGRADES. Dropping a column a WHERE names makes
    the query **error**. **Fix:** any resolved reference ⇒ BREAKS (both ops). DEGRADES is now
    reserved for "executes fine, output changes" — i.e. `SELECT *` losing a column (new `star` usage
    state). Ambiguous attribution still gated to low confidence, never a hard BREAKS.
  - **UNKNOWN is its own state**, deliberately not a lean either way: never counted safe, never
    inflated into a break, and it **never moves the numeric risk score**. Coverage is reported as an
    independent dimension (`"HIGH among assessed · 5 of 24 analysed"`), and ≥1 UNKNOWN forces
    `review_required` → **every catalog mutation is queued for a human** even when the caller did not
    ask for review. Consumers exposing no SQL at all (PowerBI measures, Looker views) are now
    carried as UNKNOWN instead of being silently omitted from the denominator.
  - Surfaced in `report_html` (UNKNOWN legend/node/tile + Coverage tile), `report_pr` (REVIEW
    REQUIRED banner + reviewer checklist item), `planner` (each UNKNOWN becomes a manual-review step,
    still derived-only), `assessment` (UNKNOWN section + `blast_radius_unassessed` /
    `blast_radius_coverage` / `blast_radius_review_required` structured properties), and the CLI.
    Zero-coverage edge case reports **no risk level at all** rather than a reassuring LOW over an
    empty evidence set.
  - *Verified:* new `tests/test_safety.py` **26 tests** (a–i + write-back gate + planner + reports +
    zero-coverage), written failing first (13 failed / 4 passed pre-fix) then green; **full suite
    45 → 73 passed**. Flagship re-run captured (`out/b15_flagship_run.txt`): 4 breaks/2 degrades →
    **6 breaks/0 degrades**, same CRITICAL, same 41 runs / 3 teams, coverage 10 of 10, still
    auto-applies. Live MCP re-run captured for both tables (`out/mcp_live_report.*`,
    `out/mcp_live_addresses_report.*`, screenshots `out/live_ui/08_*`, `09_*`); ADDRESSES' false SAFE
    is now UNKNOWN and the run is REVIEW REQUIRED. README + `datahub-skill/SKILL.md` claims reworded
    to match what is actually proven.

## P1 — proof-carrying migrations (added 2026-07-30)

- ☑ **B16 — Proof-Carrying Migrations** (`verify.py`). Turns a *generated* fix into a *verified* fix.
  `verify_migration(change, before_impact, patch, repo, *, catalog=...)` treats the diff as a
  hypothesis and tries to falsify it: **(1) ISOLATE** — `shutil.copytree` the repo into a temp
  workspace (excluding `.git`) and `git apply` **there**, so the real working tree is never touched
  on any path including errors; workspace removed in a `finally`. **(2) VALIDATE** — re-parse every
  patched `.sql` with sqlglot; file-level scope check against the fix's declared files.
  **(3) RE-RUN** — recompute impact over the patched corpus with the SAME analyzer + change, by
  substituting patched file contents for their queries via `Asset.dbt_path -> defining_query_id`.
  **(4) COMPARE** — per-consumer verdict transitions + count/coverage deltas. **(5) VERDICT** —
  `PASS` / `REVIEW_REQUIRED` / `FAIL`, each with accumulated machine-readable reason codes
  (`breaks_eliminated`, `breaks_not_reduced`, `patch_apply_failed`, `patched_sql_unparseable`,
  `safe_consumer_regressed`, `unknown_consumers_present`, `coverage_incomplete`,
  `manual_work_remaining`, `fix_incomplete_column_still_referenced`, `scope_violation`, …).
  - **PASS is a strict conjunction:** patch applied ∧ SQL parses ∧ in scope ∧ breaks_after == 0 ∧
    no new degrades ∧ unknown_after == 0 ∧ coverage complete ∧ no regressions ∧ no manual work ∧ no
    residual column references. **FAIL** on non-applying patch, unparseable patched SQL, out-of-scope
    edit, breaks unchanged/increased, or a previously-SAFE consumer regressing. Everything else is
    **REVIEW_REQUIRED**.
  - **Fail-closed carried forward from B15:** the verifier re-runs the analyzer whose blind spots
    B15 exposed, so an UNKNOWN/unassessed consumer is a blind spot, not a clean result. Zero breaks
    over a partial corpus can never be PASS.
  - **STATIC ONLY, stated everywhere.** No query is executed, no warehouse contacted, no data read,
    no dbt build invoked. The disclaimer is emitted in the CLI, `VERIFICATION.md`, the HTML section,
    the PR comment, the assessment document, and the planner notes — and a test asserts no
    *affirmative* execution claim appears anywhere in the result.
  - **Wired in:** `--verify` on `run.py` (before/after table + verdict; writes `out/VERIFICATION.md`
    + `out/verification.json`); a **Verification** section in `report_html`; verdict + delta table +
    reviewer-checklist item in `report_pr`; `writeback.py` gated so a non-PASS verification queues
    **every** mutation for a human (`auto = not (require_review or review_required or unverified)`)
    plus structured properties `blast_radius_verification_status` / `_breaks_before` / `_breaks_after`
    / `_coverage` / `_verified_at` / `_method` and the evidence appended to the assessment document;
    `planner.py` records a per-step `verified` state and stays derived-only (the no-fabricated-tokens
    guard still passes).
  - *Verified:* new `tests/test_verify.py` **25 tests** (a–h + scope + write-back gate + planner +
    both reports + the honesty guard), written failing first — proven to discriminate by running
    them against a deliberately naive always-PASS stub (**12 failed / 4 passed**; the 4 were the
    isolation cases a do-nothing stub trivially satisfies). Full suite **98 passed** (was 73).
  - *Captured runs:* `out/verification_pass_run.txt` (**PASS** — new `examples/verified-migration/`,
    breaks 2→0, both consumers BREAKS→SAFE, coverage 3 of 3, write-back **6 written / 0 queued**);
    `out/verification_run.txt` (**REVIEW_REQUIRED** — offline flagship, breaks 6→5, only 1 of 6
    breaking consumers is a dbt model, **0 written / 8 queued**);
    `out/verification_partial_run.txt` (**REVIEW_REQUIRED** — incomplete fix pinpointed to
    `rpt_referrals.sql:9`); `out/verification_mcp_live_run.txt` (**FAIL** — live MCP datapack target,
    breaks 2→2 unchanged because the two Tableau consumers use `category_name` in WHERE/GROUP BY,
    which fixgen deliberately never auto-rewrites). Artifacts `out/b16_*`,
    `out/mcp_live_VERIFICATION.md`, screenshots `out/live_ui/10..12_b16_*`.
  - New fixture `examples/verified-migration/` (synthetic) — the only example whose breaking
    consumers are all dbt models, so it can actually reach PASS. Honest note recorded: no
    pre-existing example can PASS, because every one of them has BI consumers no mechanical fix
    reaches.

## P0 — the approval trail belongs in the graph (added 2026-08-01)

- ☑ **B20.3 — write the human-approval audit into DataHub.** B19 made the approval bound,
  single-use, attributed and separately accounted — and then kept all of it in a local
  `WriteBackResult` and a manifest file on the approver's disk. The catalog, which is what
  every other human actually looks at, recorded that a dataset had a pending change and
  nothing about who consented to writing it. Six new structured properties on the changed
  dataset close that: `blast_radius_approved_by` / `_approved_at` / `_manifest_id` /
  `_verification_status_at_approval` / `_approved_writes` / `_approved_failures`.
  *Scope, stated plainly:* only B20.3. Items 1/2/4/5 of the B20 list are **not built** and are
  documented as limitations. No verdict logic changed; `verify.py` is untouched.
  - ☑ **Asserted against the payload that actually leaves the process, not the returned
    document.** This is the whole reason the round exists. `WriteBack` builds the assessment
    TWICE (B17.4): the copy EMITTED to the catalog is built *without* write-back context, and
    the copy RETURNED to the caller carries it. So the pre-existing
    `test_b19_6_structured_properties_record_the_applying_path`, which asserts on
    `doc.properties`, proves only that a dict can be formatted — it cannot tell "recorded in
    DataHub" from "recorded in a variable we then discarded". Every B20.3 test stubs
    `DataHubGraph` at the CLIENT seam, lets the real `_emit()` / `_set_structured_properties()`
    run, and decodes the `structuredProperties` aspect from its own wire form (`to_obj()`).
  - ☑ **A CLAIM CORRECTED, not quietly patched.** Verifying the above turned up that the
    `blast_radius_writeback_*` family — which B19.6's BACKLOG/PROGRESS/README/TEST_GUIDE all
    said "the catalog itself carries", including `_applied_by`, `_approver` and
    `blast_radius_approval_manifest_id` — **never reached the catalog at all**. Confirmed
    against a live instance: 26 properties on the target, zero of them `*_writeback_*`. Those
    keys are report-only by construction. The claim is corrected in place in all four
    documents and pinned by `test_b20_3_the_writeback_property_family_is_report_only`, so it
    cannot drift back. The catalog-resident record of who approved what is the B20.3 family.
  - ☑ **The two paths stay distinguishable IN THE CATALOG.** An automatic (PASS) write carries
    none of the six — not blank, not `"system"`, not `"auto"`. Absence is the signal, and it is
    asserted on the emitted payload plus a regex sweep for any approval-shaped key under any
    other name.
  - ☑ **A separate, disclosed emit — not a quietly enlarged one.** The manifest is written
    before the approval exists, so it cannot list a record *of* that approval. Enlarging the
    approved `add_structured_properties` payload would have made the emitted write differ from
    the payload summary the human read, so the audit is a distinct emit instead:
    `written_human_approved` still equals exactly the approved set and `reconciles()` still
    holds over `total`, the audit gets its own `audit_status` rather than a bucket, and the
    manifest now **tells the approver up front** that approving records their identity in the
    catalog (note text + a "what approving records about you" table in the `.md`).
  - ☑ **The audit emit carries the base properties too**, because a `structuredProperties`
    emit REPLACES the aspect — sending six fields alone would have deleted the assessment we
    had just written. Caught by writing the read-back test before the code.
  - ☑ **Outcomes, honestly.** `_approved_writes` / `_approved_failures` are recorded after the
    apply loop, so they are what happened, not what was planned: 3 written / 5 failed is
    recorded as 3 and 5. Zero writes with non-zero failures still records the approval — a
    human consented and it did not land, which is exactly what an audit is for. A failed audit
    emit sets `audit_status=failed` with the error and says so on every surface; silently
    losing the trail while reporting a clean approval would be the B17.4 lie again.
  - ☑ **Refusals record nothing.** No approver (`None` / `""` / `"   "`) → `no_approver`,
    zero aspects emitted; a FAIL → `fail_not_approvable`, zero aspects; a replay →
    `already_consumed`. An "unknown" approver in a shared catalog would be worse than no record.
  - *Verified:* **15 new tests** in `tests/test_approval.py`. 14 written FAILING first —
    **9 failed / 5 passed** (`out/b20_3_failing_first.txt`); the 5 pre-fix passes are the
    calibration guards a naive fix would have broken (the auto path carrying no approver, and
    the three refusal paths). The 15th, the report-only guard, was written *after* the fix
    because it pins a false claim discovered during verification. Full suite
    **166 → 181 passed**. **No pre-existing test changed expectation** — the only edit to
    existing test code was the module docstring.
  - *Regression check:* `examples/verified-migration/` **still reaches PASS and still
    auto-writes** — `6 planned, 0 written (auto)`, on the `would apply` path, with **zero**
    approval-shaped keys in the emitted payload (`out/b20_3_verification_pass_run.txt`,
    and section 2 of `out/b20_3_approval_audit_run.txt`). No gate touched.
  - *Captured runs:* `out/b20_3_approval_audit_run.txt` (all four offline paths on the real
    emit path), `out/b20_3_live_readback.txt` (**live** — approved against a running DataHub
    and read back over GraphQL: **15/15 assertions PASS**, 26 properties on the target, base
    assessment intact), `out/b20_3_verification_pass_run.txt`, `out/b20_3_failing_first.txt`,
    screenshots `out/live_ui/15_b20_3_approval_audit_properties.png` +
    `16_b20_3_approval_audit_viewport.png`. New scripts:
    `scripts/b20_3_approval_audit_run.py`, `scripts/b20_3_live_readback.py`,
    `scripts/b20_3_capture_audit_ui.py` (the UI capture **fails** unless the audit is really on
    the rendered page — its first run failed correctly, because DataHub renders property
    *display names* and the gate was looking for qualified names).
  - *Docs:* `demo/demo_script.md` gained **Shot 6c** — the DataHub Properties tab as the payoff
    shot — with rebalanced timings, a live-DataHub rehearsal sequence, and a note to film only a
    synthetic approver address. `README.md` gained *The approval trail is in the graph*;
    `TEST_GUIDE.md` gained *What you see in DataHub afterwards* plus the correction notice;
    `out/README.md` re-indexed to post-B20.3.
  - ☒ **B20 items 1 / 2 / 4 / 5 — not built, by decision.** Documented as limitations, not
    attempted. Feature work is closed; the remaining work is submission.

## P0 — final fail-closed round + human-approval path (added 2026-08-01)

- ☑ **B19 — Final fail-closed round + human-approval path.** THE LAST FEATURE WORK. Four rules,
  each of which is now a test: **(1)** absence of evidence is never proof of safety and never
  permission to write; **(2)** *gated* means "needs a human", not "impossible"; **(3)** a FAIL is
  never overridable by anyone or anything; **(4)** the record always distinguishes what a machine
  decided from what a human approved.
  - ☑ **B19.1 — an unknown schema is a gap, not a verdict.** A dataset that resolves with **zero
    recorded columns** used to PASS: breaks went to zero, every count-based gate was satisfied,
    and nothing noticed we had never seen the table's columns. B18 already FAILed a *provably
    absent* column, but borrowing that verdict here would be a lie in the other direction — an
    empty schema is not evidence the change is wrong. New reason code `schema_unknown`, new gate
    `target_schema_known`, deliberately **REVIEW_REQUIRED and never FAIL**; `_resolve_target()`
    now returns three outcomes instead of two.
    *Was:* 0 columns known → **PASS** `['breaks_eliminated']`. *Now:* REVIEW_REQUIRED, with the
    dataset named and the reference-level findings explicitly separated from the schema-level claim.
  - ☑ **B19.2 — git quotes paths, and we were reading the quotes.** With `core.quotepath=true`
    (the DEFAULT) git renders any non-ASCII path in C-quoted octal form, and **the quotes wrap the
    `a/`/`b/` prefix too**: `--- "a/models/r\303\251sum\303\251.sql"`. Read literally that matches no
    `Asset.dbt_path` on earth, so B18.2's deletion and rename detection silently did nothing for
    every non-ASCII-named model. New `unquote_git_path()` (octal → UTF-8 **bytes**, accumulated and
    decoded once, plus the other C escapes), applied inside `_strip_ab()` so decoding happens
    **before** prefix-stripping and every downstream comparison — scope, mapping, deleted, renamed,
    unmapped — sees the real name. Validated against real `git diff` output for a unicode name
    *and* a name with spaces (which git does **not** quote, so both forms must work).
    *Was:* deleting `"models/r\303\251sum\303\251.sql"` → `deleted_files == []`, invisible.
    *Now:* detected, decoded, blocks PASS, and B18's four-way partition invariant is re-asserted
    over paths with unicode and spaces.
  - ☑ **B19.3 — no PASS, no automatic write.** The most serious finding of the round: a run with
    **no `--verify` at all` auto-applied every mutation.** The old gate was
    `verification is not None and not auto_applicable`, so absence of a verification read as
    permission — and that was the *default* path for every invocation, including `--loop`. The gate
    is now positive: auto-write requires `verification.status == PASS`. Every refusal carries a
    machine-readable `Mutation.queue_reason`, and **all** applicable gates are reported in
    "what must change first" order (`not_verified+require_review`), because a reviewer who only saw
    `not_verified` on a regulated catalog would fix verification and be surprised it still queued.
    *Was:* `5/5 mutations AUTO-APPLY` with nothing verified. *Now:* 0 written, all queued,
    `queued because: not_verified`.
  - ☑ **B19.4 — approval manifests: bound, single-use, explicit.** Refusal alone left a reviewer
    with nowhere to go, so a REVIEW_REQUIRED run now writes `out/APPROVAL-<change>.json` plus a
    readable `.md` listing **every** queued mutation with its tool, target URN and payload summary.
    `--approve <file> --approver <who> --write` applies exactly those and nothing else. New
    `src/autopilot/approval.py`. Three properties, each tested: **BOUND** — fingerprinted over the
    change, catalog, target URN, verdict, reasons and the exact queued set incl. payload summaries;
    any drift → `manifest_stale` (an edited file fails against its own fingerprint too).
    **SINGLE-USE** — burned on success (`consumed_at` + `approver` written back); replay →
    `already_consumed`. **ATTRIBUTED** — approver from `--approver`/`BRA_APPROVER`, never invented;
    absent or blank → `no_approver`. The burn happens *after* the mutations are applied, so a crash
    mid-apply leaves the approval usable rather than silently spending it.
    *Bug found and fixed in my own first cut:* the fingerprint included
    `blast_radius_assessed_at`, a **timestamp**, so it changed on every run and no manifest could
    ever be approved from a second process. An approval must bind to the decision, not to the
    clock. `_summarise_payload()` now excludes `*_at` keys, with a regression test.
  - ☑ **B19.5 — a FAIL can never be approved.** `build_manifest()` writes nothing for a FAIL (or a
    PASS, or an unverified run). Presenting a legitimate older manifest while the verdict is FAIL is
    refused **first**, before any other check, with `fail_not_approvable` — verified through the
    `WriteBack` API *and* through the CLI's own `apply_approval()`. `--loop` cannot write at all
    (it does not verify, so rule 1 leaves it only the queue) and has no approval route by design.
    The absence of an override is asserted **structurally**: a test reads the real signatures of
    `WriteBack.__init__/run/approve`, `plan_mutations`, `run_loop` and `apply_approval`, the real
    flag list off `build_parser()`, and every `getenv()` name in those three modules, and fails on
    anything matching `force|override|ignore_fail|skip_verif|allow_fail|no_verify|unsafe|yolo`.
  - ☑ **B19.6 — split accounting.** `written` is no longer a bucket; it is a derived union of the
    disjoint `written_auto` and `written_human_approved`. `reconciles()` sums both and still equals
    `total`. `summary_line()` always names **both** paths so a zero is as explicit as a count, and
    a human-approved write carries the approver inline. Every surface follows — CLI, HTML, PR
    comment, assessment markdown, `--loop` summary — plus new structured properties
    `blast_radius_writeback_written_auto` / `_written_human_approved` / `_applied_by` / `_approver`
    / `blast_radius_approval_manifest_id` / `_queue_reason`.
    **⚠️ CORRECTED BY B20.3:** this bullet originally ended "…so the catalog itself records
    which path applied each change." That was wrong. Those properties are attached to the
    assessment built WITH write-back context, and the copy emitted to the catalog is
    deliberately built WITHOUT it (B17.4), so none of them ever reached DataHub — verified
    against a live instance. They are report-only. B20.3 is what actually puts the approval
    trail in the graph, under `blast_radius_approved_*`.
  - *Also fixed along the way:* `WriteBack` built its DataHub client in `__init__`, so
    `--loop --write` demanded GMS credentials to reach a conclusion it could reach without them
    (it can now only ever queue). The client is built lazily on first emit.
  - *Verified:* **34 new tests** — 9 in `tests/test_verify.py` (B19.1/B19.2) and 25 in a new
    `tests/test_approval.py` (B19.3–B19.6). Written failing first: **33 failing** on the first run
    (the 1 pass was the aspect-schema probe). Full suite **132 → 166 passed**.
  - *Regression check:* `examples/verified-migration/` **still reaches PASS and still auto-writes**
    (`6 planned, 0 written (auto)` under dry-run; `would apply`, not `QUEUE`) — no gate weakened.
    Nine pre-existing tests changed expectation, every one of them because B19.3 inverted the
    unverified default on purpose: `test_writeback_auto_applies_when_fully_assessed` →
    `test_writeback_gate_on_full_coverage_is_verification_only`,
    `test_dry_run_plans_without_writing` → `test_unverified_run_queues_and_writes_nothing`, and the
    seven `test_b17_4_*` accounting tests now supply a real PASS verification (new `wb_pass`
    fixture) so they keep exercising the write path they were written for.
  - *Captured runs:* `out/b19_verification_pass_run.txt` (**PASS**, auto-write path intact),
    `out/b19_verification_review_run.txt` (**REVIEW_REQUIRED**, 8 queued + manifest emitted),
    `out/b19_approval_run.txt` (approval applying exactly 8 as human-approved, then **all five
    refusals applying 0 mutations**), `out/APPROVAL-*.json` + `.md`, `out/b19_test_run.txt`
    (166 passed), `out/loop_summary.txt` (all 5 datasets queued, with reasons), artifacts
    `out/b19_pass*` / `out/b19_review*`.
  - *Docs:* `demo/demo_script.md` gained **Shot 6b** (manifest → approval → the FAIL refusal) and a
    rehearsal warning that a manifest is single-use, so a rehearsal must be followed by
    regenerating it. `TEST_GUIDE.md` gained a *Who is allowed to write* section with the two-step
    live route. `README.md` gained *Who may write, and who approves*. B18 artifacts marked
    superseded; `out/README.md` refreshed.

## P0 — final correctness + honesty round (added 2026-07-30)

- ☑ **B18 — Final correctness + honesty round.** B17 hardened the verdict once the change and
  the diff were both well-formed. B18 covers the cases where they are not, and pins down exactly
  what reaches DataHub. Same governing rule: a migration may PASS only when every known consumer
  is confidently assessed and no unresolved impact remains. **New in B18: a consumer whose
  defining SQL vanished is not a consumer that became safe.** All three new gates went into the
  SINGLE verdict source (`verify._decide()`'s `_PASS_GATES`, now fifteen clauses) — no verdict
  logic was added anywhere else.
  - ☑ **B18.1 — the change must resolve before any count means anything.** A typo'd table or
    column produced an impact report over ZERO consumers, and zero breaks over zero consumers
    satisfied every count-based gate — so the verifier returned **PASS about a change it had
    never assessed**. New `_resolve_target()` + `VerificationResult.target_resolved` /
    `.target_problem`; new gate `change_target_resolved`; reason codes `target_not_found` and
    `column_not_found` kept **distinct** because a wrong table name is a naming/lineage problem
    and a wrong column name is a schema problem. Both are hard **FAIL** (an unresolved change is
    not "improved but incomplete", it is a request we could not act on). The failing name and the
    columns/datasets that *do* exist are echoed into every surface.
    Deliberate non-gate: an **empty** dataset schema does not trigger `column_not_found` —
    unknown schema is not proof the column is absent, and absence of evidence is never proof.
    *Was:* `PASS: ['breaks_eliminated']` over 0 consumers. *Now:* `FAIL` + the reason + the name.
  - ☑ **B18.2 — destructive diffs are first-class outcomes.** `patched_files()` only read
    `+++ b/<path>`, which made two whole classes of edit invisible: a DELETION writes
    `+++ /dev/null`, and a pure RENAME emits no `---`/`+++` pair at all. Both were absent from the
    recomputation *and* from the report, so a consumer whose SQL had been removed or moved came
    back **SAFE** (`safe 1 → 2`). New `parse_diff()` → `DiffPaths(written, deleted, renamed)`
    handling git and bare-difflib forms; new `deleted_files` / `renamed_files` /
    `unresolved_renames` / `diff_sql_paths`; reason codes `patched_file_deleted` and
    `patched_file_renamed`; gates `no_consumer_sql_deleted` and `renames_recomputed`. Calibrated
    as **REVIEW_REQUIRED**, consistent with B17.3's unmapped-file gate: this is unresolved impact,
    not a broken patch.
    A rename is **allowed** to PASS when its new path maps to a catalog consumer and was actually
    re-analysed there — `_patched_catalog()` now takes `rename_targets` so a file moved *into* a
    mapped path is recomputed rather than skipped, and rename targets are never double-counted as
    coverage gaps. Scope checking was extended to cover deleted and renamed paths too: deleting a
    file outside the declared scope is as much an out-of-scope edit as rewriting one.
    **Partition invariant extended:** every `.sql` path a diff accounts for lands in exactly one
    of `file_query_map` / `unmapped_files` / `deleted_files` / `renamed_files`, asserted by test.
    *Was:* delete → `PASS`, rename → `PASS`, both with `safe 1 → 2`. *Now:* `REVIEW_REQUIRED`
    with the path named in the CLI, `VERIFICATION.md`, HTML, PR comment and JSON.
  - ☑ **B18.3 — what lands in DataHub, verified against the aspect schema.** Investigated first,
    as instructed. `InstitutionalMemoryMetadata` fields are
    `{url, description, createStamp, updateStamp, settings}` — **there is no document-body
    field**, and the old code built `payload={"title", "content"}` then passed only url +
    description to the aspect, silently dropping the assessment markdown while the module
    docstring claimed `save_document (the full Impact Assessment)`.
    **Decision: options (i) + (ii), not a fake.** (i) `persist_assessment_body()` writes the full
    markdown to `assessment_dir` (default `out/`) as `ASSESSMENT-<change>.md`, and the
    institutional-memory link points at exactly that file — written *during planning*, so a link
    is never planned before its target exists. (ii) Wording corrected everywhere to state the
    split: **stored in DataHub** = structured properties + tags + a one-line description footer +
    a link (url + title); **stored outside and linked** = the assessment body. A regex honesty
    guard now fails the build on any "the catalog stores the assessment body" phrasing.
    `_save_document(urn, title, url)` no longer takes a body it cannot send.
  - ☑ **B18.4 — stale claims and stale artifacts swept.** `src/autopilot/__init__.py` docstring
    (still said "the exact column-level fallout from real query history … opens the PR"),
    `DESIGN.md` (the `save_document: full Impact Assessment` line, the three-state
    BREAKS|DEGRADES|SAFE classification, "open PR"), `README.md` (persistence claim, PASS-gate
    table, test count, a new **What lands in DataHub, exactly** section), `demo/demo_script.md`
    (the write-back landing narration now says "link to the assessment", plus a rehearsal-checklist
    item so it is not fluffed on camera), and the root `README.md`.
    **Old `out/` artifacts** were the real hazard — `PR_COMMENT.md`, `report.json`,
    `flagship_run.txt` and `loop_summary.txt` still carried pre-B15 `4 breaks / 2 degrades` and a
    dry run reporting `8 written`. Those four were **regenerated** with current code; 20 genuinely
    historical files were **marked in place** (a `⚠️ SUPERSEDED / HISTORICAL ARTIFACT` banner on
    `.md`/`.txt`, a sibling `<name>.SUPERSEDED.txt` for `.json` where a banner would break
    parsing), and a new `out/README.md` indexes what is current vs superseded and states where the
    assessment body lives. Nothing in the repo now shows contradictory numbers without saying so.
    New `tests/conftest.py` redirects the default assessment directory to a temp dir for the whole
    session, so fixture output can never again be mistaken for captured evidence in `out/`.
  - *Verified:* **13 new tests** in `tests/test_verify.py`, written failing first — captured at
    **12 failed / 1 passed**. The one that passed pre-fix is the aspect-schema probe, and it *is*
    the B18.3 investigation result. Full suite **119 → 132 passed**.
  - *Regression check:* `examples/verified-migration/` **still reaches PASS** — no gate weakened.
    Every pre-existing verdict is byte-identical to the B17 captures: the offline flagship is
    still `REVIEW_REQUIRED` with exactly the same three reasons (`breaks_remaining`,
    `ambiguous_consumers_present`, `manual_work_remaining`) and the same `0 written / 8 queued`;
    all five loop datasets unchanged. **No existing test changed expectation.** The only test
    edits were harness plumbing: `_StubWriteBack` and the B17.4 write-back tests gained an
    `assessment_dir`, so they persist the assessment body to a temp dir instead of `out/`.
  - *Captured runs:* `out/b18_verification_pass_run.txt` (**PASS**),
    `out/b18_verification_review_run.txt` (**REVIEW_REQUIRED**, flagship),
    `out/b18_destructive_diff_run.txt` (all four B18 paths + the still-PASSing guard, side by
    side), `out/b18_test_run.txt` (132 passed), artifacts `out/b18_pass*` / `out/b18_review*`,
    and `out/README.md` as the index.
  - *Not done — unchanged from B17:* the **live MCP target was still not re-run.** The MCP server
    reads a local DataHub at `localhost:8080`, which refuses connections (Docker daemon not
    running), and the captured artifacts lack the target's schema fields, so a replay would mean
    inventing the input. Those artifacts are now explicitly marked historical.

## P0 — proof-carrying hardening (added 2026-07-30)

- ☑ **B17 — Proof-Carrying Migration Hardening.** B16 shipped a verifier that could still say PASS
  over unresolved impact. B17 closes every confirmed false-PASS path, makes write-back accounting
  truthful, and re-states the claims to match the evidence. **Governing rule, now enforced in one
  place:** a migration may PASS only when every known consumer is confidently assessed and no
  unresolved impact remains. Absence of evidence is never proof of safety.
  - **One source of truth for the verdict.** The PASS conjunction lives entirely in
    `verify._decide()`'s `_PASS_GATES` tuple — twelve named clauses, all of which must hold. A new
    gate is added in one place and cannot be bypassed by a caller; `VerificationResult.auto_applicable`
    derives from `status`, and write-back derives from `auto_applicable`. Reason codes still
    accumulate, so a reviewer sees every finding, not only the one that decided the verdict.
  - ☑ **B17.1 — ambiguous references block PASS.** An unqualified column that more than one joined
    table provides parsed fine and *was* found; we simply cannot attribute it. New reason code
    `ambiguous_consumers_present`; new gate `no_ambiguous_after`; `ImpactReport.review_required()`
    now fails closed on ambiguity as well as on unassessed consumers. **Kept a distinct state from
    UNKNOWN** — the SQL parsed, so coverage stays complete — and never inflated into a break, never
    counted as safe, never moving the risk score. `risk()["level_qualifier"]` names the real reason
    (`"CRITICAL with 1 unresolved reference(s)"` vs `"CRITICAL among assessed"`), because "could not
    be assessed" and "could not be attributed" are different failures of knowledge.
    *Was:* `breaks 1→0, ambiguous 1` → **PASS**. *Now:* **REVIEW_REQUIRED**, every mutation queued.
  - ☑ **B17.2 — remaining DEGRADES block PASS.** The verifier blocked only *new* degradations, so a
    pre-existing `SELECT *` consumer that silently loses the dropped column could ride along inside a
    PASS. New reason code `degrades_remaining`; new gate `no_degrades_after`. Deliberately calibrated:
    a pre-existing degrade is **REVIEW_REQUIRED** (unresolved impact), while a degrade the patch
    *introduced* is **FAIL** (`new_degrades`, now an explicit hard-fail clause rather than something
    that happened to be caught by the regression check). Over-failing the first would teach reviewers
    to ignore FAIL.
    *Was:* `breaks 1→0, degrades 1` → **PASS**. *Now:* **REVIEW_REQUIRED**, not downgraded to FAIL.
  - ☑ **B17.3 — unmapped patched SQL blocks PASS.** A patched `.sql` file that cannot be resolved
    through `Asset.dbt_path → defining_query_id → Query` was excluded from the recomputed impact and
    reported only as a note, so "zero breaks" covered part of the diff while reading as if it covered
    all of it. `_patched_catalog()` now returns an explicit **file → query map** alongside the
    unmapped list, and a mapping only counts when it resolves to a query that exists *and* the patched
    text is readable (a dangling `defining_query_id` or a vanished file is a gap, not a mapping). New
    `VerificationResult.file_query_map` / `.unmapped_files`, reason code `patched_file_unmapped`, gate
    `diff_fully_recomputed`. Every unmapped file is **named** in `VERIFICATION.md`,
    `verification.json`, the HTML report, the PR comment, the assessment, and the CLI.
    *Was:* patched orphan file → **PASS**. *Now:* **REVIEW_REQUIRED** with the filename on screen.
  - ☑ **B17.4 — truthful write-back accounting.** Two defects: `res.written.append(...)` ran *before*
    the `dry_run` check, so a dry run that touched nothing announced "6 written"; and `_emit()` caught
    its own exceptions, so a live mutation the server rejected was still counted as written.
    `WriteBackResult` now carries `total` (the denominator) plus five **disjoint** buckets —
    `written` (emitted, returned successfully) / `queued_for_review` / `failed` (attempted and raised)
    / `planned` (not attempted because dry-run) / `skipped` — with `reconciles()` asserting they add
    up to `total` on every path. `_emit()` no longer swallows: it raises, and the caller records
    `{mutation, tool, target_urn, error}`. `summary_line()` is derived from the counters and printed
    by `WriteBack.run()` itself, so the CLI, HTML, PR comment, assessment, structured properties, and
    `--loop` summary all restate the same numbers rather than inventing their own.
    *Was:* dry run → `Summary: 6 written`. *Now:* `6 planned, 0 written, 0 queued, 0 failed, 0 skipped`.
  - ☑ **B17.5 — demo rewritten** (`demo/demo_script.md`). The <3-min flow now *shows* proof-carrying
    verification: impact → generated fix → verify → verdict badge → gated write-back, opening on the
    write-back landing in DataHub. Stale `4 BREAKS / 2 DEGRADES` and `38 tests` gone; overlapping
    timestamps fixed; every number matches the 2026-07-30 captures.
  - ☑ **B17.6 — stale claims corrected** in `README.md`, `DESIGN.md`, `datahub-skill/SKILL.md`,
    `datahub-skill/README.md`, `pyproject.toml`, `EXAMPLES.md`. "Exact column-level fallout from your
    real query history" → "evidence-backed column-level impact from available query history and
    downstream SQL definitions, while explicitly reporting unparseable, ambiguous, and non-SQL
    consumers". "Opens the PR" → "generates an applicable patch and a CI-ready PR comment", with the
    tested `open_local_pr()` helper mentioned separately. README gained the full PASS-gate table. The
    static-verification disclaimer is untouched and the honesty-guard test still passes.
  - ☑ **B17.7 — verdict above the fold.** The verdict used to sit below the blast radius, two lineage
    graphs and two plan sections down, so the screenshot showed the problem and not the answer. New
    `_verification_banner()` renders directly under the header: **one** badge (`STATIC MIGRATION
    CHECK: PASS` — the card's old pill + summary line rendered as "PASS PASS"), the five residual
    counters that decided it, and the limitation next to the verdict. New
    `scripts/capture_verification_ui.py` re-captures both verdicts and **fails the capture** if the
    banner is not fully inside a 1280×800 viewport, so the claim cannot rot silently.
  - ☒ **B17.8 — PR-native CI.** Explicitly skipped (out of scope for this pass).
  - *Verified:* **21 new tests** — 20 in `tests/test_verify.py` (the B17 block) plus
    `test_loop_never_reports_a_dry_run_as_written` in `tests/test_loop.py`. Written failing first:
    the test_verify block was captured at **17 failed / 3 passed** before any fix, with the three
    false PASSes reproduced verbatim (`got PASS: ['breaks_eliminated']`). The 3 that passed
    pre-fix are the calibration guards a naive over-tightening would have broken. Full suite
    **98 → 119 passed**.
  - *Regression check:* `examples/verified-migration/` **still reaches PASS** under all twelve gates
    (breaks 2→0, degrades 0→0, unassessed 0→0, ambiguous 0→0, coverage 3 of 3, 2 of 2 patched files
    recomputed) — no gate was weakened to get there. Four pre-existing tests changed expectation
    *intentionally*, all on the flagship's one ambiguous reference: `test_flagship_has_full_coverage_*`
    (now asserts coverage complete **and** review required), `test_regulated_datasets_queue_for_review`
    (the flagship now queues), `test_plan_includes_all_write_tools` (`review_required is True`,
    `blast_radius_ambiguous == 1`), and the dry-run write-back test (now asserts `planned`, not
    `written`).
  - *Captured runs:* `out/b17_verification_pass_run.txt` (**PASS**), `out/b17_verification_review_run.txt`
    (**REVIEW_REQUIRED** — flagship, breaks 6→5 + `ambiguous_consumers_present`, write-back
    **0 written / 8 queued**), `out/b17_writeback_accounting_run.txt` (all five buckets across
    dry-run / clean live / 1-tool-failure / 2-tool-failure / require-review, every row reconciling),
    `out/b17_loop_summary.txt`, `out/b17_test_run.txt`, artifacts `out/b17_pass*` + `out/b17_review*`,
    screenshots `out/live_ui/13_b17_verification_pass_*` and `14_b17_verification_review_required_*`
    (light + dark, viewport-only + full page).
  - *Not done — stated plainly:* the **live MCP target was not re-run** post-B17. The MCP server reads
    a local DataHub at `localhost:8080`, which is down (connection refused; the Docker daemon is not
    running), and the captured artifacts do not include the target's schema fields, so a faithful
    replay is impossible without inventing them. The B17 gates can only tighten a verdict, so the
    captured **FAIL** cannot become a PASS — but that is reasoning, not a captured run.

## Protected / decisions needed

- Multi-category submission (Code Gen + Agents That Do Real Work): **confirm on the rules page**
  (human-only — see PROGRESS).
- `ml-skew-sentinel/` and `data-necromancer/` cores: reused as patterns, **not modified** (honored).
