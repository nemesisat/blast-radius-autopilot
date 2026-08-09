# PROGRESS.md — Done, Verified, and Off-Limits

Append newest at top. "Verified" means there is evidence (a passing test, a captured run),
not just "written."

**STATUS: BACKLOG COMPLETE (B0–B21; B17.8 and B20 items 1/2/4/5 skipped by decision). ALL
EVIDENCE GAPS CLOSED as of 2026-08-03 — next is submission (video, repo, Skill PR, Devpost).**
Full suite **198 tests passing** + a **live DataHub read+write loop
verified** + **both live-MCP targets re-run against the current build** (2026-08-03, so no
verdict is carried as reasoning any more) + **hardened proof-carrying migrations** (static
verify → PASS/REVIEW_REQUIRED/FAIL over a **sixteen-clause** PASS conjunction) + a **bound,
single-use human-approval path** whose **audit trail is written into the catalog and read back
over GraphQL (26/26 assertions, live)**. Canonical runnable tree:
`~/bra/blast-radius-autopilot`
Canonical tree is the **Desktop** one, under git since 2026-08-04
(`cd Desktop/AIProject/DataHubHackathon/blast-radius-autopilot && ~/bra/venv/bin/python -m pytest`
→ **198 passed**). `~/bra` is stale scratch and must never be rsynced onto Desktop again.

**B21 (2026-08-05) adds a whole-catalog pass:** `--sweep` assesses every candidate column change
with the same impact → fix → verify chain and emits a ranked ledger (25 landmines / 1 needs
review / 17 verified safe across 43 candidates in the synthetic catalogs). It is **read-only by
construction** — it cannot write to DataHub, and three tests enforce that.

**Two live findings that affect the demo, recorded 2026-08-03 (not bugs, but they change what
can be filmed).** (1) The **real-datapack** flagship `drop order_entry.orders.promotion_id`
verifies **FAIL / `no_patch_provided`** — it has zero dbt consumers, so no patch exists to
verify — and a FAIL is never approvable, so that asset has **no write route today**; the marks
it still carries are from the 2026-07-25 pre-B19 auto-write and are stale. The demo therefore
opens on **`analytics.fct_orders`**, which does reach REVIEW_REQUIRED → manifest → approved
write. (2) Write-back is **additive** by design, so an asset written under older semantics keeps
those marks: `Revenue by State` carries both `impact-degrades` and `impact-breaks`, and
`fct_orders` carries two institutional-memory links with the same title.

**WHO MAY WRITE — the rule, stated plainly (B19).**

| Verdict | Automatic write | Human approval |
|---|---|---|
| no `--verify` run | **no** (`not_verified`) | no — nothing was assessed, so there is no verdict to approve |
| **PASS** | **yes** | not needed |
| **REVIEW_REQUIRED** | no | **yes** — via a fingerprint-bound, single-use approval manifest |
| **FAIL** | no | **never**, by any route |

No PASS, no automatic write. A REVIEW_REQUIRED run is not a dead end: it emits
`out/APPROVAL-<change>.json` (+ a readable `.md`) listing every queued mutation, and
`--approve <file> --approver <who> --write` applies exactly those and nothing else. The manifest is
**bound** (any drift in change/verdict/queue → `manifest_stale`), **single-use** (replay →
`already_consumed`) and **attributed** (no approver → `no_approver`; never inferred).
**Exact scope of that binding (B20 items 1/2/4 were skipped by decision):** the fingerprint
covers the change, the verdict and the queued *set* — it does **not** cover each mutation's
complete canonical payload, mutation IDs are not globally unique, and a partial failure
consumes the manifest rather than emitting a retry manifest. So "applies exactly those and
nothing else" holds for the queued set, not as a cryptographic guarantee that a reviewer's
rendering is byte-identical to what executes. See `blast-radius-autopilot/LIMITATIONS.md` §5–§7. A **FAIL**
produces no manifest and can never be approved — there is deliberately no flag, env var or
parameter anywhere that applies one, asserted structurally by test. `written_auto` and
`written_human_approved` are disjoint everywhere.

**And since B20.3, the graph itself records the approval.** A human-approved write adds six
structured properties to the changed dataset — `blast_radius_approved_by` / `_approved_at` /
`_manifest_id` / `_verification_status_at_approval` / `_approved_writes` / `_approved_failures`
— read back live over GraphQL (`out/b20_3_live_readback.txt`, 15/15). An **automatic** write
carries none of them, so the two paths are distinguishable in the catalog by inspection.
*Correction recorded with it:* the `blast_radius_writeback_*` family that B19.6 claimed the
catalog carried never actually reached DataHub; it is report-only, and a test now pins that.

**What is stored in DataHub vs linked** (verified against the shipped aspect schema, not assumed):
`InstitutionalMemoryMetadata` = `{url, description, createStamp, updateStamp, settings}` — no
document-body field. So the catalog holds `blast_radius_*` structured properties, the
`pending-schema-change` / `impacted-by-upstream-change` tags, a one-line pending-change footer on
`editableProperties.description`, and an institutional-memory **link** (url + title). The full
Impact Assessment markdown is persisted to `out/ASSESSMENT-<change>.md` and is exactly what that
link points at. DataHub Cloud has a real `save_document`; this build does not use it and does not
claim to.

---

## Done + verified

- **2026-08-09 — Published to a public GitHub repo; judge simulation caught a real defect.**
  Repo: <https://github.com/nemesisat/blast-radius-autopilot> · **PUBLIC** · licence detected by
  GitHub as **Apache-2.0** · 378 tracked files · 35 MB clone (15 MB of git objects).

  **The 23 MB demo video was deliberately excluded** — `blast-radius-autopilot/out/demo_video/`
  is gitignored (the cut lives on YouTube). The storyboard, captions, narration text and build
  scripts under `demo/` are tracked. `out/submission_banners/` (1.7 MB) is tracked, as are the
  rest of the captured runs — sample outputs are explicitly recommended by the hackathon rules.
  Verified before every commit that no `.mp4`, no `.mp3` and no `.env` was staged; `.env` is
  absent from the entire history (`git log --all -- '**/.env'` empty), and no key-shaped string
  (`sk-…`, `eyJ…`) appears in any tracked file.

  **Licence detection needed a root `LICENSE`.** GitHub's licensee only reads the repository
  root, and this repo's root is the workspace — the Apache-2.0 files sat one level down in each
  project. `licenseInfo` came back `null` until an unmodified copy was placed at the root; the
  per-project `blast-radius-autopilot/LICENSE` stayed in place.

  **The clean-clone run is what found the bug.** The working copy showed 198 passed, but a fresh
  clone + fresh venv + `pip install -e '.[dev]'` — the exact command the README gives a judge —
  reported **189 passed / 9 failed**. Root cause: `acryl-datahub` was only in the `datahub`
  extra, while `test_approval.py` (7), `test_sweep.py` (1) and `test_verify.py` (1) exercise the
  real DataHub client surface. Two failed on `ModuleNotFoundError: No module named 'datahub'`;
  the other seven failed *silently plausibly* — writes landed in `failed=[…]` with
  `written_auto=[]` rather than erroring, which is the more dangerous shape. Fixed by adding
  `acryl-datahub>=0.15.0` to the `dev` extra. Skipping those tests instead would have kept the
  suite green while quietly retiring the write-back guarantees and contradicting the advertised
  198. Re-verified from a second clean clone: **198 passed in 21.78s**.

  **Judge simulation, from a clean clone at `/tmp/judge` (not the working copy):**

  | Check | Result |
  |---|---|
  | `pip install -e '.[dev]'` → `pytest` | **198 passed** in 21.78s |
  | `autopilot … --change "drop analytics.fct_signups.referrer_code" --verify` | **✅ PASS** · breaks **2 → 0** · coverage 3 of 3 · both consumers BREAKS → SAFE |
  | `autopilot --sweep --catalog examples/showcase-ecommerce/catalog.json` | ledger renders · 13 of 13 assessed · 9 landmines · 4 verified safe · 0 unassessed · 0.2s · read-only |
  | Present in clone | root `LICENSE`, `blast-radius-autopilot/LICENSE`, `LIMITATIONS.md`, `README.md`, `demo/`, `datahub-skill/`, `examples/` |

  Root `README.md` links audited: all 12 relative paths resolve.

  **Demo video linked (same day).** <https://www.youtube.com/watch?v=-DOwanGh9oM> — confirmed
  publicly reachable via YouTube's oEmbed endpoint (HTTP 200, title *"Blast Radius Autopilot —
  AI agent that verifies its own schema migrations (DataHub Agent Hackathon)"*), which private
  or removed videos do not return. Replaced `VIDEO_URL_HERE` in the root `README.md` and the
  remaining URL placeholders in `DEVPOST_SUBMISSION.md` and `SUBMIT_CHECKLIST.md`.

- **2026-08-05 — B21 Overnight Catalog Sweep built + verified (test-first, additive only).**
  The per-change loop, generalised to a whole catalog: enumerate every candidate column change,
  run the **existing** impact → fixgen → verify chain on each, emit a ranked ledger. New
  `src/autopilot/sweep.py` + `src/autopilot/report_sweep.py` + `--sweep` / `--sweep-limit`.
  Written failing first: **16 failed** on `No module named 'autopilot.sweep'`. Full suite
  **181 → 198 passed** (17 new). **No pre-existing test changed expectation.**

  **Additive-only constraint held, verified by diff — not by assertion.**

  | File | Status |
  |---|---|
  | `impact.py` `verify.py` `writeback.py` `fixgen.py` `lineage.py` `planner.py` | **UNTOUCHED** (`git diff --quiet` per file) |
  | `run.py` | **45 insertions, 0 deletions** |

  The demo path is byte-identical: the PASS run still shows `breaks 2 → 0` with 6 planned and
  0 written; the flagship still shows `breaks 6 → 5`, a manifest, and `0 written / 8 queued`.

  **Real ledger totals** (`out/b21_sweep_capture.txt`, all six synthetic catalogs, offline):

  | Catalog | Datasets | Columns | 🔴 Landmine | ❓ Unassessed | ⚠️ Review | ✅ Safe | Errors | Secs |
  |---|---:|---:|---:|---:|---:|---:|---:|---:|
  | showcase-ecommerce | 2 | 13 | 9 | 0 | 0 | 4 | 0 | 0.15 |
  | nyc-taxi | 1 | 8 | 6 | 0 | 0 | 2 | 0 | 0.10 |
  | healthcare | 1 | 6 | 4 | 0 | 0 | 2 | 0 | 0.11 |
  | fiction-retail | 1 | 6 | 2 | 0 | 0 | 4 | 0 | 0.10 |
  | finance | 1 | 5 | 3 | 0 | 1 | 1 | 0 | 0.08 |
  | verified-migration | 1 | 5 | 1 | 0 | 0 | 4 | 0 | 0.11 |
  | **TOTAL** | **7** | **43** | **25** | **0** | **1** | **17** | **0** | **0.65** |

  Every catalog reported **complete coverage** (e.g. "13 of 13 candidate(s) fully assessed"),
  which is why `unassessed` is 0 — these fixtures parse. The unassessed path is exercised by a
  test that adds an unparseable consumer, and it asserts **zero** `verified_safe` rows result.

  **THE READ-ONLY GUARANTEE, and how it is enforced.** A sweep never writes to DataHub — not
  automatically, not gated, not queued. Three independent guards:
  1. `sweep.py` does not import `writeback` and never constructs a DataHub client. A test
     asserts the string `WriteBack` does not appear in the module source.
  2. A test monkeypatches ten `WriteBack` methods, `plan_mutations`, **and**
     `DataHubGraph.__init__` to raise, then runs two full sweeps: **zero calls**.
  3. The `--sweep` branch in `run.py` **returns before the write-back code is reachable**, so
     the guarantee does not depend on the branch behaving well.
  A test also asserts no function in the module exposes a parameter matching
  `write|emit|approve|mutat|apply`, so a `--write` cannot be grown here next month without
  failing the build.

  **The "safe" bucket is split, deliberately.** Two different things were about to be called the
  same thing: `basis="verified_patch"` (a fix was generated, applied in isolation, re-parsed,
  and the impact re-run came back clean) versus `basis="no_references"` (nothing that parses
  references the column, so no patch was needed **and none was verified**). Both are genuinely
  safe to change; only the first involved verifying anything. Of the **17** safe rows, **8** are
  `verified_patch` and **9** are `no_references`. Letting the second borrow the first's
  credibility would be this project's characteristic error in miniature.

  **Bucket precedence, and why.** `unassessed` is checked **first** — everything below it is a
  statement about a corpus we could read, and if part was unreadable then no such statement is
  available. Then `landmine` (proven breaks no *generated fix* reaches — derived from the fix
  list by URN, not inferred from asset type — or a FAIL), then `needs_review`, then
  `verified_safe`. `_classify()` never inspects SQL, never counts anything itself, and never
  overrides a verdict.

  **Resilience, tested at both ends of the chain.** A raise inside `verify_migration` and a
  raise inside `compute_impact` each produce exactly one `error` row while the other three
  candidates are assessed normally and the buckets reconcile. An error row carries the exception
  text and **no verdict and no basis** — an error means we do not know, and may not borrow a
  verdict from anywhere.

  **Isolation is inherited, not reimplemented.** After a full sweep: the real dbt model is
  byte-identical, `git status --porcelain` on the fixture repo is empty, and no verify/sweep temp
  directory survives.

  **Three bugs of my own, found during the build and capture.** (1) The resilience test targeted
  `customer_zip`, which generates no patch and therefore never reaches `verify_migration` — the
  test proved nothing until retargeted to `amount`; I also added a `compute_impact` failure case
  so resilience does not depend on which stage broke. (2) The ledger's Detail column was pushed
  off the table's horizontal scroll, leaving every row tall and apparently empty — moved under
  the column name. (3) `_entry_detail()` emitted markdown into the HTML renderer, which escapes
  its input, so `**REVIEW_REQUIRED**` and backticks rendered literally — split by output format.
  Patch links were also absolute and would break in a fresh clone; now rendered relative to the
  working directory.

  **Artifacts.** `out/SWEEP.md` · `out/SWEEP.html` · `out/sweep.json` (flagship),
  `out/sweep/<catalog>/` (all six), `out/b21_sweep_capture.txt`, patches under
  `out/sweep/<catalog>/patches/`, screenshots
  `out/live_ui/19_b21_sweep_ledger.png` (+ `_dark`, `_full`, `_dark_full`). New scripts
  `scripts/b21_sweep_capture.py` and `scripts/b21_capture_sweep_ui.py` — the UI capture **fails**
  unless the header totals, all five bucket labels and the read-only scope line are really on the
  rendered page, and unless the page does not scroll horizontally.

  **Deferred by decision: the live-catalog sweep.** The live DataHub is in use for the demo video
  recording, and a sweep over it — however read-only — would compete for the same GMS the
  recording depends on. Nothing about the sweep is offline-specific: it takes any `Catalog`, so
  pointing it at a live read is a matter of loading the catalog online, not new code. **No live
  instance was touched in this task.**

- **2026-08-04 — Desktop is now the single source of truth under git; full A–K end-to-end test
  pass.** No feature work. Three jobs: stop the file loss, restore what it destroyed, test
  everything.

  **The file loss, and how it is now impossible.** Development happened in `~/bra` and was
  mirrored onto Desktop with `rsync -a --delete`. `--delete` removes anything in the destination
  that is absent from the source, so files authored directly on Desktop were destroyed:
  `LIMITATIONS.md` (recreated 2026-08-04), and `LICENSE` + `DESIGN.md` once before on 2026-07-23.
  Fixes: (a) the Desktop tree is a **git repo** as of commit `f07f5c8`, so any future deletion is
  recoverable and visible; (b) `~/bra` carries a `SCRATCH-DO-NOT-SYNC-FROM-HERE.md` stating that
  it is stale, that Desktop is canonical, and that rsync from it must never run again — with or
  without `--delete`. **I retired the sync rather than merely dropping the flag.** `~/bra/venv`
  is still used as the interpreter, now pointed at the Desktop tree (`pip install -e` re-homed
  `autopilot` there, confirmed by `autopilot.__file__`).

  **`out/` is tracked on purpose.** `blast-radius-autopilot/.gitignore` previously excluded it,
  which would have left a fresh clone full of dangling links to the very artifacts that make the
  claims checkable. 15 MB, 162 files, scanned for secrets (none — the only "token" hit is an MCP
  budget log line, and the long strings are hashes/URNs). Only `out/b20_3_scratch/` is excluded.
  **No secrets tracked:** `git ls-files | grep -i env` returns exactly the two `.env.example`
  placeholder files, both with empty token values; the real `.env` and `.venv/` (155 MB) are
  ignored, verified with `git check-ignore -v`.

  **Restored.** `LIMITATIONS.md` committed (117 lines, §1–§9). The claim-scope paragraph is back
  in `blast-radius-autopilot/README.md` immediately after the bound/single-use/attributed
  paragraph, and a new **Documentation** table links `LIMITATIONS.md` first (that README had no
  docs list at all). Both previously-dangling references now resolve: root `README.md:46` and
  `PROGRESS.md:47`.

  **A–K results — every row was run, and the two failures below are real.**

  | | Check | Result |
  |---|---|---|
  | A | install + import + `acryl-datahub` | **PASS** — editable install re-homed to Desktop; acryl-datahub **1.6.0.15**, sqlglot 30.13.0, pytest 9.1.1 |
  | B | full suite | **PASS — 181 passed** |
  | C | offline flagship `--verify --plan --html --pr-comment` | **PASS** — REVIEW_REQUIRED, **breaks 6→5**, 3 reasons; all four outputs written |
  | D | PASS path (`verified-migration`) | **PASS** — PASS, **breaks 2→0**, coverage 3 of 3, `would apply` (6 planned, not queued) |
  | E | incomplete-fix path | **PASS with a corrected expectation** — the exact `file:line` **is** named (`rpt_referrals.sql:8: still references referrer_code — WHERE s.referrer_code IS NOT NULL`), but the verdict is **REVIEW_REQUIRED, not FAIL** — see below |
  | F | 5 datasets via `--loop` | **PASS** — all 5 ran; healthcare + finance both carry `require_review` in `queued because` |
  | G | fragility leaderboard | **PASS** — `amount` (100) outranks `customer_zip` (100, fewer runs) |
  | H | **live** DataHub write path | **PASS** — GMS 200; REVIEW_REQUIRED → manifest, **0 written** with `--write` given; then approved → **8 human-approved**; GraphQL read-back **26/26 assertions PASS** |
  | I | **live MCP**, both targets | **PASS** — ORDER_DETAILS 55 cols / 24 downstreams / **queries 0** / 6 SQL defs / 5 of 24 / **FAIL**, pull 13.73 s, parse 0.013 s. ADDRESSES 9 / 17 / **0** / 7 / 5 of 17 / **FAIL** (`no_patch_provided`), pull 10.68 s, parse 0.013 s |
  | J | skill offline | **PASS after fixing my own invocation** — takes `--dataset/--column`, not `--change`; returns structured JSON (risk CRITICAL 100, breaks 6, coverage 10 of 10, `review_required: True`) |
  | K | guards | **PASS** — no `.env` tracked; **348 cited paths across 15 docs all resolve** after fixing 2 genuine dangles; working tree clean at the final commit |

  **E — the expectation was wrong, not the tool.** An incomplete fix is deliberately
  REVIEW_REQUIRED. B16 split this in two on purpose: a file-level **scope violation** is a FAIL,
  while a **residual column reference** is an observation that names the line and lets the impact
  re-run decide severity. The first cut did FAIL on residual references and misfired on a
  legitimately regenerated rewrite, producing a bogus FAIL with the wrong reason. An incomplete
  fix *does* contribute to a FAIL when the re-run shows breaks did not move at all — the live MCP
  ORDER_DETAILS target fails on `breaks_not_reduced` **+** `fix_incomplete_column_still_referenced`
  together. New repeatable `scripts/test_E_incomplete_fix.py`; the old
  `out/verification_partial_run.txt` predates B18/B19 and cited `rpt_referrals.sql:9`, a line that
  no longer exists in that file.

  **Two genuine dangling citations found by K and fixed.** (1) `PROGRESS.md` cited four
  screenshots — `01_fct_orders_overview.png` … `04_downstream_impacted.png` — that **no longer
  exist**: the 2026-07-25 real-datapack capture overwrote slots 01–04 with differently-named
  files showing the real `orders` asset, and the synthetic originals were not preserved. The entry
  now says so. (2) `out/README.md` listed a `report.html` artifact that was never regenerated
  after B18. New `scripts/check_referenced_paths.py` guards both, with a reasoned allowlist for
  the 8 path-shaped tokens that are not evidence citations (example-command outputs,
  test-fixture values, an upstream DataHub filename). I verified the guard still fails on a real
  break by planting a bogus citation and watching it flag it.

  **A third institutional-memory link appeared, from this very migration.** `_save_document` is
  idempotent *by url*, so moving canonical from `~/bra` to Desktop changed the `file://` URL and
  added a third link with the same title beside the pre-B18 placeholder and the `~/bra` path. Same
  additive-write behaviour recorded on 2026-08-03, now with a new instance and a known cause.

  **Artifacts:** `out/test_C_flagship.{txt,html}`, `out/test_C_PR.md`, `out/test_D_pass.txt`,
  `out/test_E_incomplete_fix.md`, `out/test_F_loop.txt`, `out/test_G_fragility.txt`,
  `out/test_H_step1.txt`, `out/test_H_step2.txt`, `out/test_H_readback.txt` (26/26),
  `out/test_I_order_details.txt`, `out/test_I_addresses.txt`, `out/test_J_skill.json`.

- **2026-08-03 — LIVE MCP re-run + live approval round-trip, against the current build. THE
  LAST OPEN EVIDENCE GAP IS CLOSED.** No feature work: run, capture, record. Since B17 the docs
  had carried the live-MCP verdict as *reasoning* ("the gates can only tighten, so the captured
  FAIL cannot have become a PASS") because the Docker daemon was down for three consecutive
  sessions. It is up, so that is now a **captured run** instead of an argument.

  **Preflight, as measured.** GMS `localhost:8080/health` **200**; frontend `9002` **200**;
  5 containers up healthy — **`datahub-actions` is NOT running**, recorded rather than hidden
  (not needed for these reads/writes). `.env` token **200**. Datapack still loaded: **78
  datasets**, 6 dashboards, 16 charts. **`QUERY` entities in the instance: 0.**
  `mcp-server-datahub` **0.6.0** already installed; server self-reports `datahub 3.4.5`,
  `is_oss=True`, **20 tools** (the 2026-07-25 note saying "8" had counted only the read tools).
  GMS `v1.5.0.6`.

  **Both MCP targets, exactly what the tools returned.**

  | | ORDER_DETAILS | ADDRESSES |
  |---|---:|---:|
  | `list_schema_fields` | 55 columns | 9 columns |
  | `get_lineage` (downstream, 2 hops) | 24 | 17 |
  | **`get_dataset_queries`** | **0** | **0** |
  | real SQL definitions used (`mcp:view_logic`) | **6** | **7** |
  | downstreams exposing no SQL | 18 | 10 |
  | coverage | **5 of 24 analysed** | **5 of 17 analysed** |
  | breaks / degrades / safe / UNKNOWN | 2 / 1 / 2 / **19** | 0 / 0 / 5 / **12** |
  | risk | **HIGH among assessed (50/100)** | **LOW among assessed (0/100)** |
  | `--verify` verdict | **FAIL** | **FAIL** |
  | MCP pull | **10.47 s** | **9.05 s** |
  | sqlglot parse + impact | **0.010 s** | **0.009 s** |

  **`get_dataset_queries` returned 0 on both.** The datapack ships no query history and none is
  implied; the corpus is real downstream `viewProperties.logic` read over MCP. **Seeded SQL
  used: 0.** The impact numbers are **byte-identical to the B15 capture** — the semantics fix
  has held across four subsequent rounds, and `order_history` (Jinja dbt) still parses as
  **UNKNOWN / low / `parse_error`**, never SAFE. What is new is verdict detail: the pre-B17
  capture gave `FAIL` with one reason; the sixteen-clause conjunction now names **six**
  (`breaks_not_reduced`, `breaks_remaining`, `degrades_remaining`,
  `unknown_consumers_present`, `coverage_incomplete`,
  `fix_incomplete_column_still_referenced`). Both Tableau consumers use `category_name` in
  `WHERE` + `GROUP BY`, which fixgen never auto-rewrites, so the 3 generated fixes cannot
  reduce the break count.

  **The live write path, end to end.** With `--write` **given** and the verdict
  REVIEW_REQUIRED, **nothing was written** — 8 queued, `verification_review_required+unresolved_impact`,
  manifest emitted. Then `--approve … --approver reviewer@example.com --write` applied exactly
  those 8 as human-approved and burned the manifest. **Independent GraphQL read-back: 26
  assertions, ALL PASS** (`out/b20_live_full_readback.txt`) — 24 structured properties, the six
  B20.3 audit fields (`approved_by=reviewer@example.com`, `approved_at=2026-08-03T10:12:33+00:00`,
  `manifest_id=f374130bcb5ce6f1`, `verification_status_at_approval=REVIEW_REQUIRED`,
  `approved_writes=8`, `approved_failures=0`), the `pending-schema-change` tag, an
  institutional-memory **link whose target file exists**, the `⚠️` description footer, and all
  four impacted downstreams carrying `impacted-by-upstream-change` + `impact-breaks`.

  **Five findings — reported, not fixed (this session was run-and-record).**
  1. **The real-datapack flagship cannot reach the approval path at all.**
     `showcase-ecommerce-live` / `drop order_entry.orders.promotion_id` verifies
     **FAIL / `no_patch_provided`**: all four breaking consumers are a Snowflake view, two
     PowerBI reports and an ad-hoc query — **zero dbt models** — so fixgen emits nothing. FAIL
     earns no manifest and is never approvable, so that target has **no write route today**.
     The synthetic flagship reaches REVIEW_REQUIRED only because it has one dbt consumer.
  2. **`no_patch_provided` → FAIL is arguably mis-calibrated** (same finding on ADDRESSES).
     "Nothing to check" ≠ "the fix is broken", and FAIL is the one verdict a human can never
     approve — so a target needing no mechanical fix can never have its assessment recorded.
     REVIEW_REQUIRED would fit the meaning. Fail-closed, so not dangerous; left alone.
  3. **The real datapack `orders` still carries stale marks** from the 2026-07-25 pre-B19
     auto-write: `assessed_at 2026-07-25`, `breaks=3`, `degrades=1` (pre-B15 semantics; current
     is breaks 4 / degrades 0). That write cannot happen today.
  4. **Additive write-back accumulates verdict tags across semantics changes.**
     `Revenue by State` carries **both** `impact-degrades` (pre-B15) and `impact-breaks`
     (current); `_add_tags` never removes, by design.
  5. **Institutional-memory links accumulate when the URL changes.** `_save_document` dedupes
     by url, so the pre-B18 placeholder `https://blast-radius-autopilot.local/assessment` still
     sits beside the current `file://…/ASSESSMENT-….md` — two links, same title.

  Findings 3–5 are one shape: an additive write-back meeting a catalog that holds older writes.
  None is a false PASS; none was introduced by B20.3.

  **Artifacts.** `out/mcp_live_report.{html,json}`, `out/mcp_live_addresses_report.{html,json}`,
  `out/mcp_live_VERIFICATION.md`, `out/mcp_live_addresses_VERIFICATION.md`, run logs
  `out/b20_mcp_live_run.txt` + `out/b20_mcp_live_addresses_run.txt`,
  `out/b20_live_flagship_verify.txt` (the FAIL finding),
  `out/b20_live_approval_step1.txt` + `_step2.txt` (the two-step CLI route),
  `out/b20_live_full_readback.txt` (26/26), screenshots
  `out/live_ui/17_b20_mcp_live_order_details_*` + `18_b20_mcp_live_addresses_*` +
  `16_b20_3_approval_audit_viewport.png`. New scripts
  `scripts/b20_live_full_readback.py`, `scripts/b20_capture_mcp_ui.py` (both fail rather than
  emit unearned evidence). Superseded and marked: `out/verification_mcp_live_run.txt`
  (in-place banner) and `out/mcp_report.html`, `live_ui/05_mcp_report.png`,
  `07_mcp_live_report.png`, `08_b15_mcp_live_report.png`,
  `09_b15_addresses_review_required.png` (sibling `.SUPERSEDED.txt`).

  **Docs.** `MCP_EVIDENCE.md` gained a 2026-08-03 section with the tool returns, timings, the
  live approval read-back and all five findings, plus a current-section pointer at the top and
  the older sections relabelled historical. `demo/demo_script.md` **corrected where it did not
  match live reality**: the opening now points at `analytics.fct_orders` instead of the real
  datapack `orders` (whose marks are stale and unreproducible), with the reason stated; Shot 6b/6c
  values updated to today's live run; the two additive-write artefacts flagged so they are not
  filmed as contradictions; the rehearsal checklist now carries the real container start order,
  the CLI two-step, and the 26-assertion read-back; new live-MCP B-roll with the honest
  provenance line to say on camera.

  **Full suite at the time of this run: 181 passed** (unchanged — no code was modified).

- **2026-08-01 — B20.3 The human-approval audit is written into DataHub (test-first).** B19 made
  the approval bound, single-use, attributed and separately accounted — and then kept every bit
  of it in a local `WriteBackResult` and a manifest file on the approver's disk. Six new
  structured properties put it in the graph. Written failing first: **9 failed / 5 passed**
  before any fix. Full suite **166 → 181 passed** (15 new tests in `tests/test_approval.py`).
  Scope was exactly B20.3; B20 items 1/2/4/5 were not attempted, by decision.

  **What the catalog now records on a human-approved write**, verified by GraphQL read-back
  against a running DataHub (`out/b20_3_live_readback.txt` — **15/15 assertions PASS**, 26
  structured properties on the target):

  | Property | Read back live |
  |---|---|
  | `blast_radius_approved_by` | `reviewer@example.com` |
  | `blast_radius_approved_at` | `2026-07-31T22:49:11+00:00` |
  | `blast_radius_manifest_id` | `bfb4e6b0be235a6f` |
  | `blast_radius_verification_status_at_approval` | `REVIEW_REQUIRED` |
  | `blast_radius_approved_writes` | `8` |
  | `blast_radius_approved_failures` | `0` |

  Base assessment properties survived intact alongside them (`blast_radius_status`
  `pending-change`, `_risk` `CRITICAL`, `_breaks` `6`, `_verification_status`
  `REVIEW_REQUIRED`). Visible in the UI: `out/live_ui/16_b20_3_approval_audit_viewport.png`.

  **The test discipline is the point of this round.** `WriteBack` builds the assessment twice
  (B17.4): the copy EMITTED to the catalog is built *without* write-back context, and the copy
  RETURNED to the caller carries it. So B19's
  `test_b19_6_structured_properties_record_the_applying_path`, which asserts on
  `doc.properties`, proves only that a dict can be formatted — it cannot distinguish "recorded
  in DataHub" from "recorded in a variable we then discarded". Every B20.3 test therefore stubs
  `DataHubGraph` at the **client** seam, lets the real `_emit()` and
  `_set_structured_properties()` run, and decodes the `structuredProperties` aspect from its own
  wire form (`to_obj()`).

  **A false claim found by that discipline, and corrected rather than patched over.** The
  `blast_radius_writeback_*` family — which B19.6's BACKLOG, PROGRESS, README and TEST_GUIDE all
  said "the catalog itself carries", including `_applied_by`, `_approver` and
  `blast_radius_approval_manifest_id` — **never reached the catalog at all**. Confirmed against
  the live instance: 26 properties on the target, **zero** matching `*_writeback_*`. Those keys
  are report-only by construction. Corrected in place in all four documents (the B19 entries are
  annotated, not rewritten) and pinned by
  `test_b20_3_the_writeback_property_family_is_report_only`.

  **The design decisions worth stating.**
  - *A separate, disclosed emit — not a quietly enlarged one.* The manifest is written before
    the approval exists, so it cannot list a record *of* that approval. Enlarging the approved
    `add_structured_properties` payload would have made the emitted write differ from the
    payload summary the human read. So the audit is its own emit:
    `written_human_approved` still equals exactly the approved set, `reconciles()` still holds
    over `total`, the audit gets `audit_status` instead of a bucket — and the manifest now
    **tells the approver before they consent** that approving records their identity in the
    catalog (note text plus a *what approving records about you* table in the `.md`).
  - *The audit emit carries the base properties too.* A `structuredProperties` emit REPLACES the
    aspect, so sending the six fields alone would have deleted the assessment just written. The
    read-back test was written before the code and caught exactly this.
  - *Outcomes, not intentions.* `_approved_writes` / `_approved_failures` are recorded after the
    apply loop: 3 written / 5 failed is recorded as 3 and 5, reconciling with the counters. Zero
    writes with non-zero failures still records the approval — a human consented and it did not
    land, which is what an audit is for.
  - *It fails loudly.* A rejected audit emit sets `audit_status=failed` with the error, on every
    surface. Silently losing the trail while reporting a clean approval would be the B17.4 lie
    again.
  - *Refusals record nothing.* No approver (`None` / `""` / `"   "`) → `no_approver`, **0**
    aspects emitted; a FAIL → `fail_not_approvable`, **0** aspects. An "unknown" approver in a
    shared catalog is worse than no record.
  - *The two paths stay distinguishable in the catalog.* An automatic (PASS) write carries none
    of the six — asserted on the emitted payload, plus a regex sweep for any approval-shaped key
    under any other name.

  **Regression check.** `examples/verified-migration/` **still reaches PASS and still
  auto-writes** — `6 planned, 0 written (auto)` on the `would apply` path, with zero
  approval-shaped keys emitted (`out/b20_3_verification_pass_run.txt`; section 2 of
  `out/b20_3_approval_audit_run.txt`). No gate touched, `verify.py` untouched, **no pre-existing
  test changed expectation** — the only edit to existing test code was a module docstring.

  **Evidence.** `out/b20_3_failing_first.txt` (9 failed / 5 passed pre-fix; the 5 are the
  calibration guards a naive fix would have broken), `out/b20_3_approval_audit_run.txt` (all
  four offline paths on the real emit path), `out/b20_3_live_readback.txt` (live GraphQL
  read-back), `out/b20_3_verification_pass_run.txt`, screenshots `out/live_ui/15_b20_3_*` and
  `16_b20_3_*`. New scripts `scripts/b20_3_approval_audit_run.py`,
  `scripts/b20_3_live_readback.py`, `scripts/b20_3_capture_audit_ui.py` — the UI capture
  **fails** unless the audit is really on the rendered page, and its first run failed correctly
  (DataHub renders property *display names*; the gate was looking for qualified names).

  **Docs.** `demo/demo_script.md`: new **Shot 6c** (the DataHub Properties tab as the payoff
  shot), rebalanced shot timings, a live-DataHub rehearsal sequence, and a note to film only a
  synthetic approver address. `README.md`: *The approval trail is in the graph, not just in the
  run*. `TEST_GUIDE.md`: *What you see in DataHub afterwards* + the correction notice.
  `out/README.md` re-indexed to post-B20.3.

  **Environment note.** The Docker daemon was down at the start of this session (the same
  blocker recorded in B17–B19). It was started and the existing quickstart stack was brought up
  in dependency order — opensearch → kafka → gms → frontend — which is what made the live
  read-back and the UI capture possible. The **live MCP target is still not re-run**: that is a
  separate gap (the captured MCP artifacts lack the target's schema fields), and it remains
  marked historical.

- **2026-08-01 — B19 Final fail-closed round + human-approval path (test-first).** Written failing first: **33 failing** before any fix (the 1 pass was the aspect-schema
  probe). Full suite **132 → 166 passed** (34 new tests: 9 in `tests/test_verify.py`, 25 in a new
  `tests/test_approval.py`).

  | # | Path | Test | Was (captured) | Now |
  |---|---|---|---|---|
  | B19.1 | dataset resolves with **0 known columns** | `test_b19_1_unknown_schema_forces_review_not_pass` | **`PASS`** `['breaks_eliminated']` | `REVIEW_REQUIRED` + `schema_unknown`; explicitly **not** `FAIL`, and not conflated with B18's `column_not_found` |
  | B19.2 | delete of a git-quoted unicode path | `test_b19_2_deleting_a_quoted_unicode_path_blocks_pass` | `deleted_files == []` — invisible; we compared `models/r\303\251sum…` to `models/résumé…` | detected + **decoded**, blocks PASS, partition invariant holds with unicode + spaces |
  | B19.3 | run with **no `--verify` at all** | `test_b19_3_no_verification_queues_everything` | **`5/5 mutations AUTO-APPLY`** — absence of evidence read as permission, on the *default* path | 0 written, all queued, `queue_reason=not_verified` |
  | B19.4 | REVIEW_REQUIRED has no way forward | `test_b19_4_review_required_emits_a_manifest` | `ModuleNotFoundError: autopilot.approval` | a bound, single-use manifest listing every queued mutation |
  | B19.5 | nothing enforces the FAIL line | `test_b19_5_no_entry_point_offers_a_fail_override` | `WriteBack has no attribute 'approve'` — no approval path existed, so nothing enforced its limits either | `fail_not_approvable` on every entry point; **0** mutations applied |
  | B19.6 | one undifferentiated `written` | `test_b19_6_auto_and_human_buckets_are_disjoint_and_reconcile` | no `written_auto` / `written_human_approved` | disjoint buckets, reconciling, on every surface — **and, from B20.3, in the catalog too**; the `blast_radius_writeback_*` properties added here are report-only and never reached DataHub, see the B20.3 correction |

  **The fixes.**
  - *B19.1.* `_resolve_target()` returns three outcomes now, not two, because there are three
    different facts: dataset absent → FAIL (the change names nothing), column provably absent →
    FAIL (the change is wrong), schema **empty** → REVIEW (we cannot tell either way). Borrowing
    B18's FAIL for the third would have been a lie in the opposite direction. Gate
    `target_schema_known` sits in `_PASS_GATES` and deliberately **not** in `hard_fail`.
  - *B19.2.* `unquote_git_path()` decodes C-quoted paths: octal escapes are UTF-8 **bytes**, so
    they are accumulated into a bytearray and decoded once — decoding each escape separately would
    mangle every multi-byte character. Called from inside `_strip_ab()`, so decoding happens before
    prefix-stripping (git wraps the quote around `a/` too) and every downstream comparison sees the
    real name. Verified against actual `git diff` output, both `core.quotepath` settings, for a
    unicode name and a name with spaces.
  - *B19.3.* The gate is positive now: `status == PASS` is the licence. `Mutation.queue_reason`
    carries every applicable gate in "what must change first" order — `not_verified`,
    `verification_review_required` / `verification_fail`, `require_review`, `unresolved_impact` —
    joined with `+`, because reporting only the first would send a reviewer on a wasted trip
    (fix verification, still queues, no idea why).
  - *B19.4.* New `src/autopilot/approval.py`. The fingerprint covers change, catalog, target URN,
    verdict, reasons **and** the queued set including payload summaries — so re-writing different
    values to the same URN invalidates the approval, but re-ordering the queue does not. The
    manifest is burned **after** the writes land, so a crash mid-apply leaves it usable rather than
    silently spending an approval that never took effect.
    **A bug I introduced and then caught with a real run:** the first fingerprint included
    `blast_radius_assessed_at` — a timestamp — so it changed every second and *no* manifest could
    ever be approved from a second process. An approval must bind to the decision, not to the
    clock. Fixed by excluding `*_at` keys from the payload summary, with
    `test_b19_4_fingerprint_is_bound_to_the_decision_not_the_clock` locking it.
  - *B19.5.* `fail_not_approvable` is checked **first**, before staleness or consumption, so
    someone presenting a stale manifest against a failed migration is told about the FAIL. The
    "no override exists" claim is asserted structurally rather than by trying strings: the test
    reads real signatures, the real `build_parser()` flag list, and every `getenv()` name in
    `writeback`/`run`/`loop`.
  - *B19.6.* `written` became a read-only property over two disjoint buckets, so a caller cannot
    append to it without naming the authorising path. `_emit_into(..., bucket)` takes the bucket
    from the caller that knows it, rather than inferring it after the fact.
  - *Incidental fix.* `WriteBack` built its DataHub client in `__init__`, so `--loop --write`
    demanded GMS credentials to reach a conclusion it can now reach without them. Built lazily on
    first emit.

  **Evidence — the approval route end to end** (`out/b19_approval_run.txt`):

  ```
  verification REVIEW_REQUIRED   manifest 0a632c76cec17577   8 mutation(s) awaiting a human
  1. approve                 -> 8 human-approved / 0 auto   emitted=8   exactly the queued set: True
  2. re-approve same manifest-> REFUSED already_consumed        0 applied
  3. approve against a FAIL  -> REFUSED fail_not_approvable     0 applied
  4. approve, no approver    -> REFUSED no_approver             0 applied
  5. tampered manifest       -> REFUSED manifest_stale          0 applied
  6. different change        -> REFUSED manifest_stale          0 applied
  ```

  **Regression check.** `examples/verified-migration/` **still reaches PASS and still auto-writes**
  — `6 planned, 0 written (auto)` under dry-run, on the `would apply` path, not the queue. No gate
  weakened. Nine pre-existing tests changed expectation, all of them because B19.3 inverted the
  unverified default deliberately: `test_writeback_auto_applies_when_fully_assessed` became
  `test_writeback_gate_on_full_coverage_is_verification_only` (with full coverage the only
  remaining gate is verification, and it must say so, not blame the consumers);
  `test_dry_run_plans_without_writing` became `test_unverified_run_queues_and_writes_nothing`; and
  the seven `test_b17_4_*` accounting tests now supply a real PASS verification via a new `wb_pass`
  fixture, so they keep testing the write path they exist for. The offline flagship's verdict is
  unchanged (REVIEW_REQUIRED, breaks 6→5, same reasons) — what changed is that it now also emits a
  manifest. `--loop` now queues all five datasets with reasons, which is the correct consequence of
  rule 1 and is stated in `loop.py`'s docstring, `README.md` and `TEST_GUIDE.md`.

  **Docs.** `demo/demo_script.md`: new **Shot 6b** — manifest → approval → the FAIL refusal — plus
  a *who may write* table and a rehearsal warning that approving consumes the manifest, so a
  rehearsal must be followed by regenerating it or the take shows `already_consumed`.
  `TEST_GUIDE.md`: a *Who is allowed to write* section with the two-step live route and the three
  things to know (single-use, bound, approver never inferred). `README.md`: *Who may write, and who
  approves*. B18 artifacts marked superseded; `out/README.md` refreshed to post-B19.

  **Not done at the time — NOW RESOLVED (re-run live 2026-08-03; see the top entry).** The **live MCP target was not re-run in this round**: the MCP
  server reads a local DataHub at `localhost:8080`, which refuses connections (Docker daemon not
  running), and the captured artifacts lack the target's schema fields — which B19.1 makes doubly
  relevant, since a schemaless target is now itself a REVIEW_REQUIRED finding. Those artifacts stay
  marked historical.

- **2026-07-30 — B18 Final correctness + honesty round: unresolvable changes, destructive diffs,
  and what actually persists (test-first).** B17 hardened the verdict once the change and the diff
  were both well-formed. B18 covers the cases where they are not. Written failing first: **12
  failed / 1 passed** before any fix (the one pass is the aspect-schema probe, which *is* the
  B18.3 investigation result). Full suite **119 → 132 passed**. All three new gates went into the
  single verdict source; no verdict logic was added anywhere else.

  | # | Path | Test | Was (captured) | Now |
  |---|---|---|---|---|
  | B18.1 | target dataset not in catalog | `test_b18_1_unresolvable_target_dataset_fails` | **`PASS`** `['breaks_eliminated']` over **0 consumers** (`target_urn is None`, `queries_total == 0`) | `FAIL` + `target_not_found`, the missing name echoed everywhere |
  | B18.1 | target column not on the dataset | `test_b18_1_missing_column_fails_with_its_own_reason` | **`PASS`** `['breaks_eliminated']` | `FAIL` + `column_not_found` (distinct reason) + the columns that do exist |
  | B18.2 | diff DELETES a consumer's `.sql` | `test_b18_2_deleting_a_consumers_sql_file_blocks_pass` | **`PASS`**, and `safe 1 → 2` — the deleted consumer *gained* a clean bill of health; `files_patched` never contained it | `REVIEW_REQUIRED` + `patched_file_deleted`, path named |
  | B18.2 | diff RENAMES a consumer's `.sql` | `test_b18_2_renaming_a_consumers_sql_file_blocks_pass` | **`PASS`**, `safe 1 → 2` — a pure rename emits no `---`/`+++` pair, so the move was invisible | `REVIEW_REQUIRED` + `patched_file_renamed`, both paths named |
  | B18.3 | catalog "stores the full assessment" | `test_b18_3_institutional_memory_stores_only_a_link_...` | aspect fields are `{url, description, createStamp, updateStamp, settings}` — **no body field**; `payload["content"]` was built and then dropped | body persisted to a file, link points at it, wording corrected, regex guard enforces it |

  **The fixes.**
  - *B18.1 — resolve the change before trusting any count.* New `_resolve_target(catalog, change)`
    plus `VerificationResult.target_resolved` / `.target_problem`, computed before the patch is
    even applied and turned into a verdict only by `_decide()`. New gate
    `change_target_resolved`; both codes are hard **FAIL**, because an unresolved change was never
    assessed — that is not a migration that "improved but is incomplete", it is a request we could
    not act on. `target_not_found` and `column_not_found` stay separate on purpose: they send a
    reviewer to different places. **Deliberate non-gate:** an *empty* dataset schema does not
    trigger `column_not_found` — unknown schema is not proof the column is absent, and absence of
    evidence is never proof.
  - *B18.2 — deletions and renames are outcomes, not omissions.* New `parse_diff()` returns
    `DiffPaths(written, deleted, renamed)`, handling both `git diff` (with `diff --git` +
    `rename from/to` + `deleted file mode`) and bare `difflib.unified_diff` output; verified
    against `git apply` for all three forms. New `deleted_files`, `renamed_files`,
    `unresolved_renames`, `diff_sql_paths`; new gates `no_consumer_sql_deleted` and
    `renames_recomputed`, both calibrated to **REVIEW_REQUIRED** to match B17.3 (unresolved
    impact, not a broken patch). `_patched_catalog()` gained `rename_targets`, so a file moved
    *into* a path the catalog maps is **recomputed, not skipped** — a rename may still PASS on
    that route, and `test_b18_2_rename_to_a_mapped_path_is_recomputed_not_skipped` proves the gate
    is not a blanket block. Rename targets are never added to `unmapped_files`, so no path is
    double-counted. Scope checking now covers deleted and renamed paths as well as written ones.
    **Partition invariant, extended:** every `.sql` path a diff accounts for is in exactly one of
    `file_query_map` / `unmapped_files` / `deleted_files` / `renamed_files`. A rename is one
    logical file, accounted for by its OLD path; the new path appears in `file_query_map` when the
    diff also carried content for it.
  - *B18.3 — investigated, then decided.* Probed the shipped classes rather than assuming:
    `InstitutionalMemoryMetadata` has no field that can hold a document. Took options **(i)+(ii)**
    — did **not** fake it, and did not abuse `description` to smuggle the markdown in. (i)
    `persist_assessment_body()` writes the full markdown to `assessment_dir` (default `out/`) as
    `ASSESSMENT-<change>.md`; the link's `url` is that file's URI, and the write happens during
    *planning* so a link is never planned before its target exists. (ii) Every surface reworded to
    state the split — the mutation summary itself now reads "add institutional-memory link '<title>'
    -> <path> (catalog stores the link + title only; the full assessment body is that file)", and
    `test_b18_3_no_surface_claims_the_catalog_stores_the_document_body` fails the build on any
    "catalog stores the body" phrasing while requiring the location to be named.
    `_save_document(urn, title, url)` no longer accepts a body it cannot send.
  - *B18.4 — stale claims + stale artifacts.* Swept `src/autopilot/__init__.py` (its docstring
    still promised "the exact column-level fallout from real query history … opens the PR"),
    `DESIGN.md` (the `save_document: full Impact Assessment` line, the three-state classification,
    "open PR"), `README.md` (persistence claim, the PASS-gate table now lists all fifteen gates,
    test count, and a new *What lands in DataHub, exactly* section), `demo/demo_script.md` (the
    opening DataHub narration now says "link to the assessment", with a rehearsal-checklist item so
    it is not fluffed live), and the root `README.md`.
    The real hazard was `out/`: `PR_COMMENT.md`, `report.json`, `flagship_run.txt` and
    `loop_summary.txt` still carried pre-B15 `4 breaks / 2 degrades` and a dry run announcing
    `8 written`. Those four were **regenerated**; 20 genuinely historical files were **marked in
    place** (banner on `.md`/`.txt`; sibling `<name>.SUPERSEDED.txt` for `.json`, where a banner
    would break parsing); new `out/README.md` indexes current vs superseded and states where the
    assessment body lives. New `tests/conftest.py` points the default assessment directory at a
    temp dir for the session, so fixture output can never again land in `out/` and be mistaken for
    evidence.

  **Regression check — PASS still reachable, nothing else moved.**
  `examples/verified-migration/` still returns **PASS** (`out/b18_verification_pass_run.txt`);
  no gate was weakened to get there. Every pre-existing verdict is byte-identical to the B17
  captures: the offline flagship is still **REVIEW_REQUIRED** with exactly the same three reasons
  (`breaks_remaining`, `ambiguous_consumers_present`, `manual_work_remaining`) and the same
  `0 written / 8 queued`; all five loop datasets unchanged. **No existing test changed
  expectation** — the only test edits were harness plumbing (`_StubWriteBack` and the B17.4
  write-back tests gained an `assessment_dir` so they persist bodies to a temp dir).
  `out/b18_destructive_diff_run.txt` shows all four B18 paths next to the guard case that must
  stay PASS, and it does.

  **Not done at the time — NOW RESOLVED (re-run live 2026-08-03; see the top entry).** The **live MCP target was not re-run in this round**.
  The MCP server reads a local DataHub at `localhost:8080`, which refuses connections (the Docker
  daemon is not running), and the captured artifacts do not include the target's schema fields —
  and schema is exactly what column resolution and ambiguity attribution depend on, so a "replay"
  would mean inventing the input. Those artifacts are now explicitly marked historical. To
  unblock: bring the instance up and re-run
  `PATH=~/bra/venv/bin:$PATH python scripts/mcp_live_run.py --slug b18_mcp_live --verify`.

- **2026-07-30 — B17 Proof-Carrying Hardening: four false-PASS paths closed (test-first).**
  B16 shipped a verifier that could still return PASS while known impact was unresolved. Each path
  below was reproduced as a failing test *before* any fix, and the "was" column is the literal
  pre-fix output. Full suite **98 → 119 passed** (21 new tests; **17 failed / 3 passed** on the
  first run — the 3 were the calibration guards a naive fix would have broken).

  | # | False-PASS path | Test | Was (captured) | Now |
  |---|---|---|---|---|
  | B17.1 | ambiguous reference survives into a PASS | `test_b17_1_ambiguous_reference_blocks_verification_pass` | `breaks 1→0, ambiguous 1` → `PASS: ['breaks_eliminated']` | `REVIEW_REQUIRED` + `ambiguous_consumers_present`, `auto_applicable False`, all mutations queued |
  | B17.1 | impact report itself auto-applies with ambiguity | `test_b17_1_ambiguous_reference_forces_impact_review` | `review_required() → False` | `True`; `auto_applicable() → False` |
  | B17.2 | pre-existing DEGRADES survives into a PASS | `test_b17_2_existing_degrade_blocks_pass` | `breaks 1→0, degrades 1` → `PASS: ['breaks_eliminated']` | `REVIEW_REQUIRED` + `degrades_remaining`, and **not** downgraded to FAIL |
  | B17.3 | patched file mapped to no query survives into a PASS | `test_b17_3_unmapped_patched_sql_blocks_pass` | `PASS: ['breaks_eliminated']`; the unmapped file was only a *note* | `REVIEW_REQUIRED` + `patched_file_unmapped`; `unmapped_files == ['models/rpt_orphan.sql']`, named in every output |
  | B17.4 | dry run reports writes it did not perform | `test_b17_4_dry_run_reports_planned_not_written` | `Summary: 6 written` after touching nothing | `6 planned, 0 written, 0 queued, 0 failed, 0 skipped` |
  | B17.4 | failed live mutation counted as written | `test_b17_4_failed_emit_is_not_counted_as_written` | `_emit()` swallowed the exception; mutation landed in `written` | recorded in `failed` with tool + target URN + error; `_emit()` raises |

  **The fixes.**
  - *One source of truth.* The whole PASS conjunction is now `_PASS_GATES` inside
    `verify._decide()` — twelve named clauses (`patch_applied`, `patched_sql_parses`,
    `diff_in_scope`, `diff_fully_recomputed`, `no_breaks_after`, `no_degrades_after`,
    `no_unknown_after`, `no_ambiguous_after`, `coverage_complete`, `nothing_regressed`,
    `no_manual_work_remaining`, `no_residual_references`), all of which must hold. Nothing else in
    the codebase synthesises a verdict: `auto_applicable` derives from `status`, write-back derives
    from `auto_applicable`. Reason codes still accumulate.
  - *Ambiguous is its own state.* `ImpactReport.review_required()` fails closed on
    `unknown` **or** `ambiguous`, but the two are never conflated: an ambiguous consumer parsed, so
    it stays out of `coverage()["unassessed"]` and coverage can be complete while review is still
    required. It is never inflated into a break and never counted as safe.
    `risk()["level_qualifier"]` now distinguishes `"CRITICAL among assessed"` (something went unread)
    from `"CRITICAL with 1 unresolved reference(s)"` (everything was read, one thing unattributed),
    and the narrative summary, CLI banner, PR comment, and `compute_impact` note each name the actual
    gap instead of reporting one as the other.
  - *Diff coverage is tracked, not inferred.* `_patched_catalog()` returns an explicit
    `file → query_id` map next to the unmapped list, and a mapping counts only when it resolves to a
    query that exists *and* the patched text is readable. Every patched `.sql` file is therefore in
    exactly one of `file_query_map` / `unmapped_files` — a test asserts that partition.
  - *Write-back tells the truth.* `WriteBackResult` = `total` + five disjoint buckets
    (`written` / `queued_for_review` / `failed` / `planned` / `skipped`) + `reconciles()`.
    `summary_line()` is derived from the counters and printed by `WriteBack.run()` itself, so the CLI,
    HTML, PR comment, assessment markdown, structured properties (`blast_radius_writeback_*`), and the
    `--loop` summary cannot restate it differently. The assessment is deliberately built **twice**: the
    copy written into the catalog carries no write-back counters, because a document cannot honestly
    report the outcome of the write that saved it; the copy returned to the caller does.

  **Reconciled write-back counters** (`out/b17_writeback_accounting_run.txt`, 5 mutations planned on
  every path):

  | path | total | written | queued | failed | planned | skipped | reconciles |
  |---|---:|---:|---:|---:|---:|---:|---|
  | dry-run | 5 | 0 | 0 | 0 | 5 | 0 | ✓ |
  | live, clean | 5 | 5 | 0 | 0 | 0 | 0 | ✓ |
  | live, 1 tool fails | 5 | 3 | 0 | 2 | 0 | 0 | ✓ |
  | live, 2 tools fail | 5 | 2 | 0 | 3 | 0 | 0 | ✓ |
  | `require_review` | 5 | 0 | 5 | 0 | 0 | 0 | ✓ |

  **Regression check — PASS is still reachable, and was not bought by weakening a gate.**
  `examples/verified-migration/` still returns **PASS** with every gate satisfied independently:
  breaks 2→0, degrades 0→0, unassessed 0→0, ambiguous 0→0, coverage 3 of 3, `unmapped_files == []`
  (2 of 2 patched files recomputed), no manual work, no residual references, no regressions
  (`out/b17_verification_pass_run.txt`). `test_b17_pass_conjunction_is_still_reachable` asserts each
  clause separately so a future failure says *which* gate closed.

  **Verdicts changed only where intended.** Four pre-existing tests changed expectation, all traceable
  to the flagship's single ambiguous reference — `q_adhoc_ambiguous_zip`, an unqualified `customer_zip`
  across two joined tables that both provide it:
  `test_flagship_has_full_coverage_and_needs_no_forced_review` → renamed
  `..._but_one_unresolved_reference` (coverage complete **and** review required);
  `test_regulated_datasets_queue_for_review` → the non-regulated flagship now queues too;
  `test_plan_includes_all_write_tools` → `blast_radius_review_required is True`,
  `blast_radius_ambiguous == 1`; `test_dry_run_writes_nothing_but_plans` → renamed
  `test_dry_run_plans_without_writing`, asserting `planned` instead of `written`, over a new
  `clean_report` fixture with the ambiguous query removed so the auto-write path stays covered.
  The offline flagship's own verdict is unchanged in kind — still **REVIEW_REQUIRED**, breaks 6→5 —
  with `ambiguous_consumers_present` added to its reasons and write-back **0 written / 8 queued**
  (`out/b17_verification_review_run.txt`).

  **B17.5 demo / B17.6 claims / B17.7 screenshots.**
  - `demo/demo_script.md` rewritten around proof-carrying verification (impact → generated fix →
    verify → verdict badge → gated write-back), opening on the DataHub write-back landing. Stale
    `4 BREAKS / 2 DEGRADES`, `38 tests`, and the overlapping timestamps are gone; the rehearsal
    checklist now says **119 tests**.
  - Claims corrected in `README.md`, `DESIGN.md`, `datahub-skill/SKILL.md`,
    `datahub-skill/README.md`, `pyproject.toml`, `EXAMPLES.md`: "exact column-level fallout from your
    real query history" → the evidence-backed wording; "opens the PR" → "generates an applicable patch
    and a CI-ready PR comment" (with `open_local_pr()` described separately as the tested local
    helper); EXAMPLES' breadth table refreshed from the 2026-07-30 loop run with the write-back buckets
    spelled out. README gained the twelve-gate PASS table. The static-verification disclaimer is
    unchanged and `test_a_static_verification_never_claims_execution` still passes.
  - `_verification_banner()` puts the verdict directly under the header — one badge
    (`STATIC MIGRATION CHECK: PASS`, replacing the card's "PASS PASS" pill + summary-line duplication),
    the five residual counters, and the limitation beside the verdict. New
    `scripts/capture_verification_ui.py` regenerates both reports from the CLI, screenshots them at
    1280×800 in light **and** dark, and **fails** if the banner is not fully above the fold. Captured:
    PASS banner at y=285–498px, REVIEW REQUIRED at y=310–552px (fold 800px) →
    `out/live_ui/13_b17_verification_pass_*`, `14_b17_verification_review_required_*`. The earlier
    `10..12_b16_*` shots are superseded (they showed `CRITICAL` with the verdict below the fold).

  **Not done at the time — NOW RESOLVED (re-run live 2026-08-03; see the top entry).** The **live MCP target was not re-run** after B17. The MCP server
  reads a local DataHub at `localhost:8080`, which refuses connections (the Docker daemon is not
  running), and the captured artifacts (`out/mcp_live_report.json`, `out/mcp_live_materialized/`) do
  not include the target's schema fields — and schema is exactly what ambiguity attribution depends
  on, so a "replay" would mean inventing the input. The captured pre-B17 verdict for
  `order_details / drop category_name` is **FAIL** (breaks 2→2 unchanged). The B17 gates can only
  tighten a verdict, never loosen one, so that run cannot have become a PASS — but that is reasoning,
  not a captured run, and it is labelled as such in the README table. To unblock: bring up the local
  DataHub instance and re-run
  `PATH=~/bra/venv/bin:$PATH python scripts/mcp_live_run.py --slug b17_mcp_live --verify`.

- **2026-07-30 — B16 Proof-Carrying Migrations built + verified (test-first).** A generated fix is no
  longer trusted — it is *verified*. New `src/autopilot/verify.py`. Full suite **73 → 98 passed**.
  **Prerequisite honoured:** B15 was confirmed landed before starting (UNKNOWN verdict exists,
  parse-error → UNKNOWN/low with `review_required`, DROP+WHERE → BREAKS, 73 green) — the verifier
  re-runs the impact analyzer, so a wrong analyzer would have produced false PASSes.
  - **The chain.** `verify_migration(change, before_impact, patch, repo, *, catalog=…)`:
    **ISOLATE** — `copytree` the repo to a temp workspace (excluding `.git`) and `git apply` *there*;
    the real tree is never touched on any path, and the workspace is removed in a `finally`.
    **VALIDATE** — re-parse every patched `.sql` with sqlglot + a file-level scope check.
    **RE-RUN** — recompute impact over the patched corpus with the same analyzer and change,
    substituting patched file contents for their queries via `Asset.dbt_path → defining_query_id`.
    **COMPARE** — per-consumer verdict transitions + count/coverage deltas. **VERDICT** — with
    accumulated machine-readable reason codes.
  - **Verdict logic.** **PASS** is a strict conjunction: patch applied ∧ patched SQL parses ∧ in
    scope ∧ `breaks_after == 0` ∧ no new degrades ∧ `unknown_after == 0` ∧ coverage complete ∧ no
    regressions ∧ no manual work remaining ∧ no residual references to the dropped column.
    **FAIL** on: patch didn't apply, patched SQL unparseable, out-of-scope edit, breaks
    unchanged/increased, or a previously-SAFE consumer regressing. Everything else →
    **REVIEW_REQUIRED**. Reasons accumulate, so the caller sees every finding, not just the
    deciding one.
  - **Fail-closed inherited from B15.** The verifier re-runs the analyzer whose blind spots B15 made
    visible, so a consumer it cannot read is a blind spot, not a clean result. **Zero breaks over a
    partial corpus is never PASS** — the single most important test (`test_e_*`) asserts exactly
    this. Uncertainty is not inflated the other way either: UNKNOWN is never counted as a break.
  - **WHAT STATIC VERIFICATION PROVES:** the patch applies cleanly, the patched SQL parses, the diff
    stayed in scope, and the analyzer can no longer find a broken or unassessed consumer.
    **WHAT IT DOES NOT PROVE:** that anything ran. No query is executed, no warehouse or database is
    contacted, no data is read, no dbt build is invoked. It is evidence about SQL text, not about
    runtime behaviour, row counts, or results. The disclaimer is emitted in the CLI, `VERIFICATION.md`,
    the HTML section, the PR comment, the assessment doc, and the planner notes; a test asserts no
    *affirmative* execution claim appears anywhere (regex with negative lookbehind, so the honest
    negation "no queries were executed" is allowed and the affirmative form is not).
  - **Wired in:** `--verify` on `run.py` → before/after table + verdict, writes `out/VERIFICATION.md`
    + `out/verification.json`; **Verification** section in `report_html`; verdict + delta table +
    reviewer-checklist item in `report_pr`; `writeback.py` gated so a non-PASS verification queues
    **every** mutation for a human, plus structured properties
    `blast_radius_verification_status/_breaks_before/_breaks_after/_coverage/_verified_at/_method`
    and the evidence appended to the assessment document; `planner.py` gains a per-step `verified`
    state and remains derived-only (the B14 no-fabricated-tokens guard still passes).
  - *Evidence — tests:* `tests/test_verify.py` **25 tests** covering (a) clean fix → PASS,
    (b) non-applying patch → FAIL + real tree untouched, (c) unparseable patched SQL → FAIL,
    (d) partial reduction → REVIEW_REQUIRED, (e) **UNKNOWN present + zero breaks → REVIEW_REQUIRED,
    never PASS**, (f) non-dbt manual work → REVIEW_REQUIRED, (g) previously-SAFE regression → FAIL,
    (h) isolation across 4 scenarios (`git status` clean, files byte-identical, temp workspace
    removed), plus scope, write-back gate, planner, both reports, and the honesty guard. Written
    failing first and **proven to discriminate** by running them against a deliberately naive
    always-PASS stub: **12 failed / 4 passed** (the 4 were the isolation cases a do-nothing stub
    trivially satisfies). Then all green.
  - *Evidence — captured runs, all three verdicts on real runs:*
    **PASS** `out/verification_pass_run.txt` — new `examples/verified-migration/`,
    `drop fct_signups.referrer_code`: breaks **2 → 0**, both consumers BREAKS→SAFE, coverage 3 of 3,
    and write-back **6 written / 0 queued** (the gate opens only on PASS).
    **REVIEW_REQUIRED** `out/verification_run.txt` — offline flagship `drop fct_orders.customer_zip`:
    breaks **6 → 5**, `rpt_orders_by_region` BREAKS→SAFE, the other 5 breaking consumers are BI
    dashboards/ad-hoc queries no mechanical fix reaches → **0 written / 8 queued**.
    **REVIEW_REQUIRED** `out/verification_partial_run.txt` — incomplete fix pinpointed to
    `rpt_referrals.sql:9` (`GROUP BY` still references the column).
    **FAIL** `out/verification_mcp_live_run.txt` — live MCP datapack target
    `drop order_details.category_name`: breaks **2 → 2 unchanged**, because both Tableau consumers
    use `category_name` in `WHERE` + `GROUP BY`, which fixgen deliberately never auto-rewrites. The
    verifier names the exact lines. Artifacts `out/b16_*`, `out/mcp_live_VERIFICATION.md`,
    screenshots `out/live_ui/10_b16_verification_pass.png`, `11_b16_verification_review.png`,
    `12_b16_verification_section.png`.
  - *Two bugs of my own, found and fixed during the build:* (1) adding a module-level `import json`
    to `run.py` while two local `import json` statements remained inside `main()` made `json` a
    local variable → `UnboundLocalError` that aborted every `--verify` run after printing the table;
    removed the shadowing imports. (2) My first scope check failed any diff whose *added* lines
    mentioned the dropped column — which misfired on a **regenerated** rewrite that re-emits a
    `GROUP BY` it is not allowed to change, turning a legitimate partial fix into a bogus FAIL with
    a wrong reason ("files outside scope"). Split into a file-level scope check (FAIL) and a
    separate `fix_incomplete_column_still_referenced` observation that reports the exact
    `file:line` and lets the impact re-run decide severity.
  - *Honest limitation recorded:* **no pre-existing example can reach PASS**, because every one has BI
    consumers that no mechanical fix reaches. `examples/verified-migration/` (synthetic, all-dbt
    consumers) was added so the PASS path is demonstrable on a real captured run rather than only in
    unit tests. For the live MCP target the datapack has no checked-out dbt project, so
    `scripts/mcp_live_run.py --verify` **materialises** the MCP-read `viewProperties.logic` into
    `out/mcp_live_materialized/` and labels it explicitly as synthesised-from-metadata, **not** a real
    dbt repo.

- **2026-07-30 — B15 Safety semantics: the two correctness defects are FIXED, test-first.**
  Guiding principle: *missing evidence must never read as proof of safety* — and equally, uncertainty
  is never inflated into a fake break. Full suite **45 → 73 passed**.
  - **DEFECT 1 → FIXED (the verified false negative).** A SQL parse failure was scored
    **SAFE / confidence "high"**: `lineage.py:177` set `usage="none", confidence="low"` on ParseError,
    then `impact.py:78` overwrote confidence back to `"high"` because `usage=="none"`, and "none"
    maps to SAFE. **Fix:** `parse_error` is a distinct usage state carried end-to-end into a new
    fourth verdict **UNKNOWN**; confidence stays `low`; the `"none"`→high promotion now applies only
    to a *parsed, proven* non-reference. The two "none"s are permanently distinct.
    *ADDRESSES before/after (the same dbt model, same MCP data):*
    **before** — `order_details` (Jinja dbt, references `country_id` 4×) = `SAFE / high`, run read
    `risk LOW`, 7 safe, no caveat, write-back would auto-apply.
    **after** — `UNKNOWN / low / usage=parse_error`, run reads **`LOW among assessed · 5 of 17
    analysed · REVIEW REQUIRED`**, and write-back plans **0 auto / 4 queued**.
    *Honest note:* the level string is still "LOW" and should be — the 5 consumers we CAN analyse
    genuinely do not reference `country_id`. Inventing a break we never proved would be the opposite
    error. What changed is that it is no longer a *clean* LOW: it is qualified, gated, and its
    denominator is visible.
  - **DEFECT 2 → FIXED (severity mis-grade).** On a DROP, a reference resolving to the column but
    sitting only in WHERE/JOIN/GROUP/HAVING/ORDER was DEGRADES; dropping a column a WHERE names makes
    the query **error**. **Fix:** any resolved reference ⇒ **BREAKS** (both ops). **DEGRADES** is now
    reserved for "executes fine, output changes" — `SELECT *` losing a column (new `star` usage
    state). Consequence: verdicts are now op-independent; op still drives the reason text and fix gen.
  - **UNKNOWN is load-bearing, not a lean.** Never counted safe, never inflated into a break, and it
    **never moves the numeric risk score**. Coverage is an independent dimension
    (`"HIGH among assessed · 5 of 24 analysed"`); ≥1 UNKNOWN sets `review_required()` which forces
    **every catalog mutation to queue for a human** even when the caller passed
    `require_review=False`. Consumers exposing **no SQL at all** (PowerBI measures, Looker views) are
    now carried as UNKNOWN rather than omitted from the denominator. Zero-coverage edge case reports
    **no risk level at all** instead of a reassuring LOW over an empty evidence set.
  - **Surfaced everywhere:** `report_html` (UNKNOWN legend + grey node + Unassessed & Coverage
    tiles), `report_pr` (REVIEW-REQUIRED banner + reviewer checklist item), `planner` (each UNKNOWN
    becomes a manual-review step; still derived-only — the no-fabricated-tokens guard still passes),
    `assessment` (UNKNOWN section + `blast_radius_unassessed` / `blast_radius_coverage` /
    `blast_radius_review_required` structured properties), `run.py` CLI, and the JSON report.
  - *Evidence — tests:* `tests/test_safety.py` **26 tests** written FAILING first (13 failed /
    4 passed pre-fix; the 4 pre-existing passes were the false-*positive* guards, confirming the bugs
    were all on the false-negative side), then all green. 7 existing tests encoded the old semantics
    and were updated as intended changes, not silently: flagship counts, the powerbi filter-only
    consumer, both star tests, the parse-error test, skill JSON, write-back properties.
  - *Evidence — offline flagship* (`out/b15_flagship_run.txt`): `drop fct_orders.customer_zip`
    **4 breaks / 2 degrades → 6 breaks / 0 degrades**; the 2 filter-only consumers
    (`q_powerbi_revenue_by_state` WHERE-only, `q_adhoc_join_on_zip` JOIN-only) moved to BREAKS. Same
    CRITICAL, same 41 runs, same 3 teams, same 1 gated low-confidence, coverage **10 of 10**, still
    auto-applies (correctly — nothing is unassessed). No other verdict changed.
  - *Evidence — live MCP re-run* (both tables, real datapack, reads over `mcp-server-datahub` 0.6.0):
    **ORDER_DETAILS** `drop category_name` — 24 discovered / 6 with analysable SQL / 18 no-SQL;
    **before** 3 breaks-0 degrades-3 safe, `CRITICAL 62`; **after** **2 BREAKS · 1 DEGRADES ·
    2 SAFE · 19 UNKNOWN**, `HIGH among assessed (50) · 5 of 24 analysed · REVIEW REQUIRED`.
    Two intended reclassifications: `ORDER_DETAILS_REPLICA` (`SELECT * FROM order_details`)
    BREAKS→**DEGRADES** (a `*` view really does still run), and dbt `order_history`
    SAFE→**UNKNOWN**. *The CRITICAL→HIGH drop is a de-escalation and is deliberate* — it comes
    entirely from the star reclassification, not from unknowns diluting the score.
    **ADDRESSES** `drop country_id` — 17 discovered / 7 with analysable SQL / 10 no-SQL →
    0 breaks · 0 degrades · 5 safe · **12 UNKNOWN**, `LOW among assessed · 5 of 17 analysed ·
    REVIEW REQUIRED`. Artifacts: `out/mcp_live_report.{html,json}`,
    `out/mcp_live_addresses_report.{html,json}`, screenshots `out/live_ui/08_b15_mcp_live_report.png`
    + `09_b15_addresses_review_required.png`.
  - **Adapter gap also closed:** `scripts/mcp_live_run.py` previously omitted the 18 no-SQL
    downstreams entirely, so coverage read a flattering *"5 of 6"*. It now registers them as
    definition-less assets → the honest **"5 of 24"**. Core logic untouched by that change.
  - *Claims reworded to match what is proven:* README headline + verdict list + a "Verified live-MCP
    run — stated plainly" section with the real numbers; `datahub-skill/SKILL.md` now documents four
    states and returns coverage. No "exact fallout from your real query history" overclaim remains.

- **2026-07-29 — Full end-to-end run THROUGH the MCP server on an AUTO-SELECTED datapack table,
  using REAL datapack SQL (no seeded queries).** Stronger than the 07-25 MCP run: the target is
  discovered over MCP instead of hardcoded, and the impact corpus is real SQL read over MCP instead
  of the seeded query log. *Preflight:* the DataHub stack had exited 44h earlier (status 255, daemon
  restart) — restarted opensearch→kafka→gms→frontend→actions, GMS 200, `.env` token still valid,
  78 datasets intact; `mcp-server-datahub` was **no longer installed** and was reinstalled (v0.6.0).
  Server reports `datahub 3.4.5, is_oss=True` and **20 tools** (the earlier "8 tools" note
  understated it).
  - **Target discovery (MCP only):** `search(entity_type = dataset)` paginated → 78 datasets, then
    `get_lineage(upstream=False, max_hops=2)` on all 78 (41.4s) → **ORDER_DETAILS wins with 24
    downstreams** across 6 platforms (tableau 8, powerbi 6, looker 2, snowflake 2, dbt 1, 5 other),
    beating the old flagship `orders` (17). Ranking: `out/mcp_ranking.json`.
  - **Pull + counts + timing:** `get_entities` / `list_schema_fields` (**55 columns**) /
    `get_lineage` (**24 downstreams**) / `get_dataset_queries` (**total 0**) / `get_entities` on all
    24 downstreams. **mcp_pull 11.46s, sqlglot parse+impact 0.014s** — parse is 14 ms and touches no
    table data, so it is metadata-bound regardless of the table's real size.
  - **Provenance (stated plainly):** `get_dataset_queries` returned **0** — the datapack ships **no
    query history**, and none is implied. The corpus is instead **6 REAL SQL definitions read over
    MCP** from downstream `viewProperties.logic` (dbt order_history, 4 Tableau Custom SQL,
    ORDER_DETAILS_REPLICA). **Seeded SQL used: 0.** Only **6 of 24** downstreams expose parseable
    SQL — the other 18 (PowerBI/Looker/dashboards) can't be assessed by the parser. `runs`=1 and
    `teams`=0 (no execution counts or owners came over MCP), so the "impacted runs" tile is a
    consumer count, not real execution volume.
  - **Impact:** column also auto-picked (most-referenced real column) = `category_name` (6 refs);
    `drop order_entry_db.analytics.order_details.category_name` → **breaks 3 / degrades 0 / safe 3,
    CRITICAL (62/100)**, incl. correct `SELECT *` star handling at medium confidence. Artifacts
    `out/mcp_live_report.{html,json}` (JSON carries a full `provenance` block) + screenshot
    `out/live_ui/07_mcp_live_report.png`.
  - **Second table (dataset-agnostic):** `ADDRESSES` — 9 cols / 17 downstreams / 0 queries / 7 SQL
    defs; auto-column `country_id` → breaks 0 / safe 7, LOW; `out/mcp_live_addresses_report.*`.
  - **⚠ DEFECT FOUND, NOT FIXED (core was off-limits): a SQL parse failure is scored SAFE with
    confidence "high".** `lineage.py:177` sets `usage="none", confidence="low"` on ParseError, then
    `impact.py:78` overwrites confidence to `"high"` because usage is "none", and `_verdict_for`
    maps "none" → SAFE; the failure survives only as a `report.notes` line. **Consequence:** on the
    ADDRESSES run the Jinja-templated dbt `order_details` model (5000 chars) failed to parse but
    **joins addresses and references `country_id` 4×** — scored SAFE/high, which is why that run
    reads LOW. That LOW is a false negative. Same defect is present-but-harmless on ORDER_DETAILS
    (dbt `order_history` failed to parse and is genuinely unaffected — right by luck, not analysis).
    Candidate fixes: map `parse_error` to a distinct UNKNOWN verdict keeping `confidence="low"`,
    and/or pre-render dbt Jinja in the adapter. **Test suite not re-run this session.**
  - New scripts (adapters only, no `src/autopilot/` changes): `scripts/mcp_rank_tables.py`,
    `scripts/mcp_live_run.py`, plus probes `mcp_probe.py` / `mcp_shape.py` / `mcp_sql_probe.py`.
    Full call log + counts + timing in `MCP_EVIDENCE.md`.

- **2026-07-25 — B14 Grounded Migration Planner built + verified.** New `src/autopilot/planner.py`
  (`build_plan` / `render_plan_md` / optional `phrase_with_llm`) turns the impact result into a
  step-by-step safe-change plan using **derived facts only** — topological step order (models →
  BI last), each step = asset + owner + BREAKS/DEGRADES + action (apply generated fix | manual
  review) + labeled column-analysis (parser) confidence; teams-to-involve = distinct owners;
  tests = impacted downstreams; rollback references the generated PR; risk from the impact result.
  Effort/timeline/deploy-window are explicit `⟨human to decide⟩` placeholders — never computed.
  Wired `--plan` into run.py (writes `MIGRATION_PLAN.md`) and a "Migration plan — grounded" section
  into the HTML report; no impact/fixgen core changes. *Evidence:* `test_planner.py` 6/6 (topo
  order, owner rollup, rollback-references-PR, and a guard asserting NO fabricated tokens —
  hour/day/%/numeric-confidence); **full suite 45 passed**; flagship `drop
  order_entry.orders.promotion_id` run captured (`out/migration_plan_run.txt`, 0 forbidden tokens,
  4 labeled parser-confidence lines) + regenerated HTML (`out/live_report.html`) + screenshot
  (`out/live_ui/06_migration_plan.png`). demo_script updated with the plan beat.

- **2026-07-25 — Reads via the DataHub MCP server (mcp-server-datahub); report built from MCP data.**
  Stood up the official **`mcp-server-datahub` v0.6.0** over stdio (authed with the `.env` token,
  connected to local GMS `is_cloud=False, version=1.5.0.6`); an MCP client listed 8 tools and
  pulled the real `orders` asset **over MCP**: `search` (1182 hits), `list_schema_fields`
  (**15 columns**), `get_entities` (name/tags/description), `get_lineage` (**17 downstreams** incl.
  order_details + PowerBI measures), `get_dataset_queries` (**total 0** — empty, noted). Fed the
  MCP-pulled **schema + lineage** into the unchanged `autopilot.impact` + `report_html` (queries
  from the seeded log since MCP returned none) → `out/mcp_report.html` (breaks 3 / degrades 1 /
  CRITICAL), screenshot `out/live_ui/05_mcp_report.png`. Reproducible via
  `scripts/mcp_pull_report.py`. Full call log: `MCP_EVIDENCE.md`. No core-logic changes; `.env`
  gitignored/local-only.

- **2026-07-25 — ALL demo scenarios loaded into local DataHub + write-backs applied (browsable).**
  Datapack reloaded (**78 datasets** indexed). Applied + read-back-verified (all PASS):
  - **Flagship (real datapack)** `orders` — `drop order_entry.orders.promotion_id`: 15 real cols +
    `pending-schema-change` + 7 blast_radius_* props + assessment doc; downstream `order_details`
    (55 cols) tagged `impact-breaks`, PowerBI `Essential_KPI_Measures` tagged `impact-degrades`.
  - **nyc-taxi** `trips` (8 cols) full write-back; `rpt_trip_metrics` tagged `impact-breaks`.
  - **fiction-retail** `customers` (6 cols) full write-back; `rpt_loyalty` tagged `impact-breaks`.
  - **healthcare** `encounters` (6 cols) + **finance** `fct_revenue` (5 cols): emitted/browsable,
    write-back correctly **review-gated → QUEUED** (0 written, 6/7 queued) — the compliance gate.
  Added a thin online wrapper `scripts/emit_example.py` (reuses load_catalog + WriteBack + SDK emit;
  no core-logic change) to emit each example's schemas + run write-back online. Printed + saved a
  **`TEST_GUIDE.md`** (per-scenario search terms + what to see in the UI). Read-back proof in
  `LIVE_DATAHUB_EVIDENCE.md`. `.env` gitignored/local-only; 39 offline tests still green.

- **2026-07-25 — LIVE verified on the REAL `showcase-ecommerce` DATAPACK (not hand-seeded).**
  Loaded DataHub's official pack via `datahub datapack load showcase-ecommerce` (verified pack,
  1049 entities across Snowflake/Looker/PowerBI/Tableau; 32 real datasets indexed). Ran the agent
  against the **real** target `snowflake … b2fd91.order_entry_db.order_entry.orders` with change
  `drop order_entry.orders.promotion_id` (a real column), `--write`.
  - **Query history:** the datapack ships **none** (verified `QUERY` entities = 0,
    `usageStats.topSqlQueries` = 0) → used the blessed FALLBACK: a query log against the REAL
    `orders` columns (`examples/showcase-ecommerce-live/`). Schemas + downstreams are the
    datapack's real ones.
  - **GraphQL read-back — all 10 assertions PASS:** `orders` retains its **15 real columns** and now
    carries our `pending-schema-change` tag (alongside the datapack's own Large Table / Most Queried
    tags), the CRITICAL description footer, **7** `blast_radius_*` structured properties
    (breaks=3, degrades=1, risk=CRITICAL), and the institutional-memory assessment doc. Real
    downstreams tagged: `order_details` (**55 real columns**, full SQL view def) →
    `impacted-by-upstream-change` + `impact-breaks`; PowerBI `Essential_KPI_Measures` (12 real cols)
    → `impact-degrades`. **Confirms real populated downstreams, no "No data" stubs.**
  - **UI screenshots** (replace the toy captures) in `blast-radius-autopilot/out/live_ui/`:
    `01_orders_overview.png`, `02_orders_properties.png`, `03_orders_documentation.png`,
    `04_downstream_order_details.png`. Full read-back in `LIVE_DATAHUB_EVIDENCE.md`.
  - *Issues hit + fixed:* `datahub datapack --help` crashes (wheel ships empty `resources/`), but
    `load` works; UI capture first grabbed loading skeletons on the heavy real pages → fixed to wait
    on page-specific real content before screenshotting. New flagship = real `orders.promotion_id`
    (see `demo/demo_script.md`).

- **2026-07-23 (re-run) — LIVE re-verified end-to-end on THIS machine.** Repeated the full flow to
  reconfirm: DataHub healthy (6 containers, GMS+frontend 200, datahub/datahub login 200); existing
  `.env` token still authenticates (200); `scripts/live_datahub_demo.py --write` applied 8 mutations
  clean; **independent GraphQL read-back — all 7 assertions PASS** with a fresh
  `blast_radius_assessed_at = 2026-07-23T17:35:11+00:00` (proves a genuine new run, not cached):
  tag `pending-schema-change`, description footer, 7 `blast_radius_*` props (status=pending-change,
  risk=CRITICAL, score=100, breaks=4, degrades=2, teams=3), institutional-memory assessment doc, and
  downstream `rpt_orders_by_region` carrying `impacted-by-upstream-change` + `impact-breaks`. UI
  re-captured (onboarding popup dismissed) to `blast-radius-autopilot/out/live_ui/` (01–04). No
  issues this run. `.env` gitignored + local-only. See `LIVE_DATAHUB_EVIDENCE.md`.

- **2026-07-23 — LIVE verified on THIS machine (run + read-back + UI capture).** Separate from the
  build-time run: brought up `datahub docker quickstart` (all 6 containers healthy), minted a
  personal access token via the frontend GraphQL `createAccessToken` → `.env` (gitignored, never
  committed), ran `python scripts/live_datahub_demo.py --write` (flagship `drop
  analytics.fct_orders.customer_zip`), then proved it with an **independent GraphQL read-back**
  (all 7 assertions PASS):
  - `fct_orders`: tag `pending-schema-change`; description footer ("…breaks 4 and degrades 2…
    CRITICAL"); **7** `blast_radius_*` structured properties (status=pending-change, risk=CRITICAL,
    score=100, breaks=4, degrades=2, teams=3, assessed_at); institutional-memory doc "Blast Radius
    Assessment — drop analytics.fct_orders.customer_zip".
  - downstream `rpt_orders_by_region`: tags `impacted-by-upstream-change` + `impact-breaks`.
  **UI screenshots** for the video were captured to `blast-radius-autopilot/out/live_ui/` as
  `01_fct_orders_overview.png`, `02_fct_orders_properties.png`, `03_fct_orders_documentation.png`,
  `04_downstream_impacted.png`. **Those four files no longer exist** — the 2026-07-25
  real-datapack capture replaced slots 01–04 with `01_orders_overview.png`,
  `02_orders_properties.png`, `03_orders_documentation.png`, `04_downstream_order_details.png`,
  which show the real `orders` asset instead of this synthetic one. The original synthetic
  captures were not preserved; this reference is kept for the record, not as a live citation.
  Full read-back + notes in `LIVE_DATAHUB_EVIDENCE.md`.
  *Issue hit + fixed:* the UI-capture login first clicked the wrong submit button ("Sign in with
  SSO") and captured the login page; fixed to `button[data-testid='sign-in']` with a post-login
  assertion, then re-captured. No secrets committed (`.env` gitignored; not copied to the canonical tree).

- **2026-07-23 — Canonical → Desktop SYNC + VERIFY complete.** `rsync -a --delete` (subtree-scoped)
  mirrored `~/bra/blast-radius-autopilot` → `Desktop/.../blast-radius-autopilot`; trees now in full
  parity (dry-run clean). **Fresh-venv `pytest` from the Desktop copy = 39 passed.** Previously-missing
  artifacts now present on Desktop: `LIVE_DATAHUB_EVIDENCE.md`, `out/examples/` (10 per-dataset runs),
  `examples/CAPTURED_RUNS.md`, `out/showcase_report.html`, `out/PR_COMMENT.md`, screenshots
  (`out/report_light.png`, `out/fragility.png`). No secrets copied (`.env` absent; only `.env.example`);
  build-junk (`__pycache__`/`.egg-info`/`.pytest_cache`) cleaned. All file-path citations in
  PROGRESS/BACKLOG/EXAMPLES resolve. **Note:** `--delete` also removed two Desktop-only files not in
  the canonical tree — `LICENSE` and `DESIGN.md`; both were immediately restored to canonical **and**
  Desktop (LICENSE re-copied from the untouched Apache-2.0 file in `data-necromancer/`), so the
  protected Apache-2.0 LICENSE and the product spec are intact.

- **2026-07-23 — LIVE DataHub round-trip verified (bonus).** The background `datahub docker
  quickstart` came up healthy (gms/frontend/kafka/mysql/opensearch/actions). `scripts/live_datahub_demo.py`
  emitted the synthetic datasets, computed the blast radius, ran the REAL write-back, and read it
  back via GraphQL. *Evidence:* tags `pending-schema-change`, description footer, **7 structured
  properties**, and the assessment doc (institutional memory) all confirmed on live `fct_orders`;
  impacted downstream assets tagged. Also caught + fixed two real SDK bugs (structured-property
  definition must precede value set; institutional-memory needs a valid AuditStamp). See
  `LIVE_DATAHUB_EVIDENCE.md`.

- **2026-07-23 — B11/B12/B13 (reporting) built + verified.**
  - **B11 HTML report** (`report_html.py`): self-contained; inline-SVG lineage graph with
    red/amber/green nodes (glyph + label, never colour alone), scorecard tiles, risk meter, teams,
    migration diff; light/dark theme-aware. *Evidence:* `test_reports.py`; rendered + screenshotted.
  - **B12 PR-comment** (`report_pr.py`): CI-style comment + `open_local_pr()` (branch → apply fix →
    commit → `PR_COMMENT.md`, no remote needed). *Evidence:* `test_reports.py` incl. a real local git PR.
  - **B13 Fragility leaderboard** (`fragility.py`): ranks riskiest columns catalog-wide. *Evidence:*
    `test_fragility.py` 4/4; text + HTML rendered + screenshotted. Honest finding: `amount` outranks
    `customer_zip` (aggregated in 7 queries).

- **2026-07-23 — B6/B7 (loop + ≥5 examples) built + verified.** `loop.py` + `loop.config.yaml` run
  the SAME code across 5 datasets (showcase-ecommerce, nyc-taxi, healthcare-synthetic,
  fiction-retail, finance-synthetic); regulated sets queue every write for review. *Evidence:*
  `test_loop.py` 5/5; captured in `examples/CAPTURED_RUNS.md` + `out/examples/`.

- **2026-07-23 — B8/B9 (demo + OSS skill) built.** `demo/demo_script.md` (<3-min shot list),
  README leads with the overlap framing; `datahub-skill/` (SKILL.md + runnable `skill.py`,
  Apache-2.0). *Evidence:* `test_skill.py` runs the skill → structured impact JSON.

- **2026-07-23 — B1–B5 built + verified (the P0 end-to-end core).**
  - **B1 scaffold:** Apache-2.0 LICENSE, pyproject (src layout), `.env.example`, `.gitignore`.
    *Evidence:* `pip install -e .` OK; `import autopilot` OK.
  - **B2 read layer** (`catalog.py`): offline JSON loader + online `DataHubCatalogReader`
    (schema/lineage/queries → MCP/SDK). *Evidence:* loads the showcase catalog (2 datasets, 5 assets).
  - **B3 impact core** (`lineage.py` + `impact.py`): sqlglot column-usage engine (select/filter/none)
    + WHERE/JOIN raw-scan gap closer, schema-aware attribution, low-confidence gate, star handling.
    *Evidence:* `test_lineage.py` 13/13, `test_impact.py` 5/5 — flagship `drop customer_zip` =
    4 breaks / 2 degrades / 3 safe / 1 low-conf, 41 runs, 3 teams, CRITICAL.
  - **B4 fix generation** (`fixgen.py`): mechanical dbt drop/rename, formatting-preserving minimal
    diff (sqlglot regen fallback); re-parsed for validity. *Evidence:* `test_fixgen.py` 3/3 incl.
    `git apply --check`.
  - **B5 write-back** (`writeback.py` + `assessment.py`): gated approve-before-write; structured
    props / tags / save_document / description; `--require-review` queues. *Evidence:*
    `test_writeback.py` 4/4; live round-trip above.
  - **CLI** (`run.py`): blast radius + scorecard + fix diff + write-back plan; `--loop`,
    `--fragility`, `--html`, `--pr-comment`, `--json`, `--online`.

- **2026-07-23 — B0 (query history / fallback) verified.** Live DataHub not reachable at build
  start; executed the blessed fallback: seeded synthetic `examples/showcase-ecommerce/`. *Evidence:*
  10 queries reference `analytics.fct_orders` across 4 teams → unblocked.

- **2026-07-22 — Build-loop structure adopted; `data-necromancer/` & `ml-skew-sentinel/` built +
  tested; DataHub APIs verified; Blast Radius Autopilot design finalized.** (Prior baseline.)

## Decisions & assumptions (autonomous)

- **Build/runtime = Python 3.12 venv.** acryl-datahub supports ≤3.12; system default 3.14 too new.
  Canonical venv after the Desktop lock (below): `~/bra/venv`.
- **Offline-first, DataHub-optional.** The whole loop runs on synthetic JSON fixtures mirroring the
  MCP read surface; a live instance is bonus evidence, never a blocker. (It did come up — verified.)
- **Engine = sqlglot directly** (same engine as DataHub's `parse_sql_lineage()`) so impact is
  identical online/offline; online can swap in `DataHubGraph.parse_sql_lineage()`.
- **Impact semantics** (as of B15 + B17.1). DROP and RENAME: any resolved reference = BREAKS,
  whether projected *or* in WHERE/JOIN/GROUP BY/HAVING/ORDER BY — dropping a column a filter names
  makes the statement error, it does not silently drift. `SELECT *` that carries the column =
  DEGRADES (still runs, output changes). Parsed and provably untouched = SAFE. Unreadable or no SQL
  definition = UNKNOWN, never SAFE. Ambiguous unqualified columns (>1 joined table provides it) →
  low confidence, reported on their own axis: never counted as a break, never counted as safe, never
  moving the risk score — and (B17.1) they **force review**, because the reference is real and only
  its attribution is open.
- **Fix gen mechanical only;** WHERE/JOIN logic flagged for review, never auto-rewritten.
- **Write-back safe-by-default** (assessment is additive); `require_review` catalogs queue all.
  `save_document` maps to InstitutionalMemory on OSS (true save_document is Cloud).
- **All example data public/synthetic.** Healthcare/finance carry compliance notes + are review-gated;
  no real PHI/PII or company data anywhere.
- **ENVIRONMENT — Desktop TCC lock (handled, did not block).** Mid-build, macOS privacy protection
  intermittently revoked this automation's access to `~/Desktop` (read/list/overwrite denied;
  new-file create allowed), then later recovered. Mitigation: all code was developed + tested in the
  home mirror `~/bra/blast-radius-autopilot` (all tools + Bash work there) and rsync'd to Desktop.
  During the lock, final docs were written as `*.FINAL.md` new files; after recovery these were
  folded back into the real `PROGRESS.md`/`BACKLOG.md`/`EXAMPLES.md`. `LIVE_DATAHUB_EVIDENCE.md`
  retained as standalone evidence.

## Human-only remaining (I cannot do these for you)

_Feature work is closed as of B18. Everything below is submission work._

1. ~~**Push to a public GitHub repo**~~ — **done 2026-08-09**:
   <https://github.com/nemesisat/blast-radius-autopilot>, public, description + 6 topics set.
2. ~~**Set Apache-2.0 visible in the repo "About"**~~ — **done 2026-08-09** via a root `LICENSE`;
   GitHub reports `licenseInfo.key = apache-2.0`.
3. ~~**Record the <3-min demo video**~~ — **done 2026-08-09**:
   <https://www.youtube.com/watch?v=-DOwanGh9oM>, public, linked from the root `README.md`.
   The rendered cut stays gitignored; `demo/` carries the shot list, storyboard and captions.
4. **Open the real upstream Skill PR** to `datahub-skills` for `blast-radius-autopilot/datahub-skill/`
   (needs GitHub auth; confirm that repo's contribution layout first).
5. **Open the real dbt migration PR** on the on-camera repo (needs GitHub auth; the tool already
   produces branch/diff/comment locally via `open_local_pr()`).
6. **Opt into the feedback survey.**
7. **Confirm multi-category listing on the rules page** (Code Generation + Agents That Do Real Work);
   otherwise submit single-category (Code Generation).

## Do not touch (honored)

- The working cores of `data-necromancer/src/` and `ml-skew-sentinel/src/` — reused as patterns,
  not modified.
- Any `LICENSE` file — Apache-2.0 kept as-is.
