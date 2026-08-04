# Blast Radius Autopilot — <3-minute demo shot list

**One-liner to open with:** _"DataHub's Impact Analysis shows you the blast radius of a schema change. Blast Radius Autopilot **defuses** it — and then checks its own work."_

The through-line of the video is **proof-carrying verification**: impact → generated fix →
verify → verdict badge → **gated** write-back. The fix is never trusted because it was
generated; it is trusted only because it was re-checked, and when it cannot be proven the
agent refuses to approve it.

Shots 1–6b run **offline** against synthetic catalogs in `examples/` — no live DataHub needed.
Their numbers are from the captured runs of **2026-07-30** (post-B17). Shot 6c is the one beat
that **needs a live DataHub**; its numbers are from the live run of **2026-08-03**
(`out/b20_live_full_readback.txt`, 26/26 assertions).

> **Open on the write-back landing in DataHub.** Before the terminal, show the
> **`analytics.fct_orders`** asset in the DataHub UI with the Autopilot contribution on it —
> the `pending-schema-change` tag, the `blast_radius_*` structured properties, the
> pending-change footer, and the institutional-memory **link** to the Impact Assessment. Say:
>
> > _"This is the end state: the assessment is attached to the asset in the catalog, next to the
> > data it describes. Here is how it got there — and why the agent would not let it in without
> > proof."_
>
> Be precise if asked: DataHub OSS's `institutionalMemory` aspect stores a **url + title**, not
> a document body. The catalog holds the properties, tags, footer and that link; the assessment
> markdown itself is `out/ASSESSMENT-<change>.md`, which is what the link opens.
>
> ⚠️ **Open on `analytics.fct_orders`, NOT on the real datapack `order_entry.orders`.** Verified
> live on 2026-08-03 — this changed on purpose and the old instruction is now wrong:
>
> - `order_entry.orders` still carries marks in the catalog, but they are from the
>   **2026-07-25 pre-B19 auto-write**: `blast_radius_assessed_at = 2026-07-25`, `breaks=3`,
>   `degrades=1`. Current analysis of that same change says **breaks 4 / degrades 0**. Those
>   numbers on screen would contradict the terminal.
> - That write **cannot be reproduced**. `drop order_entry.orders.promotion_id` verifies
>   **FAIL / `no_patch_provided`** — all four of its breaking consumers are a Snowflake view,
>   two PowerBI reports and an ad-hoc query, with **zero dbt models**, so no patch is generated.
>   FAIL earns no manifest and can never be approved, so that asset has no write route at all
>   today (`out/b20_live_flagship_verify.txt`).
> - `analytics.fct_orders` is the target that genuinely reaches REVIEW_REQUIRED → manifest →
>   human-approved write, and it was written live on 2026-08-03 with all 26 read-back
>   assertions passing. It is also the asset Shot 6c returns to.
>
> ⚠️ **Two cosmetic artefacts of an additive write-back**, if the camera lands on them: the
> downstream `Revenue by State` carries **both** `impact-degrades` (pre-B15 run) and
> `impact-breaks` (current), and `fct_orders` carries **two** institutional-memory links with
> the same title (a pre-B18 placeholder URL beside the current file URL). `_add_tags` and
> `_save_document` never remove, by design. Either avoid those two spots or say plainly that
> write-back is additive and the catalog holds history.

---

### Shot 1 — the proposed change (0:00–0:20)

Show:

```text
drop analytics.fct_signups.referrer_code
```

> _"A developer wants to remove one column. Before it merges, Autopilot asks DataHub who
> depends on it."_

### Shot 2 — the original blast radius (0:20–0:45)

```bash
autopilot --catalog examples/verified-migration/catalog.json \
          --change "drop analytics.fct_signups.referrer_code"
```

Point at the scorecard:

```text
🔴 2 breaks   🟡 0 degrades   🟢 1 safe   ⚪ 0 unassessed   ◐ 0 ambiguous
COVERAGE: 3 of 3 analysed
risk HIGH (56/100)
```

> _"Two consumers reference the column — including in clauses DataHub's SQL parser documents
> that it excludes. Coverage is 3 of 3: nothing here went unread."_

### Shot 3 — the generated migration (0:45–1:10)

Show the two minimal dbt patches printed in the terminal:

```text
dbt_project/models/rpt_signups_by_plan.sql
dbt_project/models/rpt_referrals.sql
```

> _"Generating a patch is easy. Trusting it blindly is not."_

### Shot 4 — verification: the fix checks itself (1:10–1:45)  ← the money shot

```bash
autopilot --catalog examples/verified-migration/catalog.json \
          --change "drop analytics.fct_signups.referrer_code" \
          --verify \
          --html out/b17_pass_report.html \
          --json out/b17_pass.json
```

Show the verification block:

```text
MIGRATION VERIFICATION (static)  —  ✅ PASS
  metric          before   after   delta
  breaks               2       0      -2
  degrades             0       0      +0
  safe                 1       3      +2
  unassessed           0       0      +0
  ambiguous            0       0      +0
  coverage      3 of 3 analysed -> 3 of 3 analysed
  patched files recomputed: 2 of 2
```

> _"The patch was applied to an isolated copy — never the real tree — the patched SQL was
> re-parsed, and the blast radius was recomputed by the same analyzer. Both patched files were
> mapped back to a real consumer, so the recomputation covers the whole diff."_

Then say the limit out loud, because it is on screen:

> _"This is static. No query was executed, no warehouse was contacted, no data was read."_

### Shot 5 — the verdict badge (1:45–2:05)

Open `out/b17_pass_report.html`. The verdict banner is the **first thing under the header**:

```text
STATIC MIGRATION CHECK: PASS
Breaks 2 → 0   Degrades 0 → 0   Unassessed 0 → 0   Ambiguous 0 → 0   Coverage 3 of 3 analysed
No queries were executed. No warehouse was contacted. No data was read.
```

> _"One badge, the counters that decided it, and the limitation right next to the verdict."_

### Shot 6 — fail-closed contrast + gated write-back (2:05–2:30)

Same command, the flagship catalog:

```bash
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" \
          --verify --html out/b17_review_report.html
```

```text
STATIC MIGRATION CHECK: REVIEW REQUIRED
breaks 6 -> 5      ambiguous 1 -> 1      coverage 10 of 10 analysed
why:
  - breaks_remaining
  - ambiguous_consumers_present
  - manual_work_remaining
manual work: Revenue by State, Sales by ZIP, ZIP Heatmap, q_adhoc_join_on_zip, q_adhoc_zip_export

WRITE-BACK (dry-run):
  gate: verification REVIEW_REQUIRED — every mutation queued for a human.
Summary: 0 planned, 0 written, 8 queued, 0 failed, 0 skipped.  (dry run — nothing was written)
```

> _"It fixed the dbt model, but five dashboards and ad-hoc queries remain, and one column
> reference can't be attributed to a source table at all. So: **zero written, eight queued.**
> The agent refuses to approve its own migration."_

Land the honesty point on the counters themselves:

> _"And that summary is the real accounting. A dry run reports what it planned, never what it
> wrote — and a live mutation that fails is reported failed, not written."_

### Shot 6b — gated is not a dead end: the approval route (2:30–2:42)

Same run also wrote an **approval manifest** — point at the line:

```text
Approval manifest -> out/APPROVAL-drop-analytics-fct-orders-customer-zip.json
  (8 mutation(s) await a human; apply with --approve <that file> --approver <you>)
```

Open `out/APPROVAL-drop-analytics-fct-orders-customer-zip.md` — the human-readable view:
a table of **exactly** the 8 writes, the verdict they were queued under, and the command.
Then approve it:

```bash
autopilot --catalog examples/showcase-ecommerce/catalog.json \
          --change "drop analytics.fct_orders.customer_zip" --verify \
          --approve out/APPROVAL-drop-analytics-fct-orders-customer-zip.json \
          --approver reviewer@example.com --write
```

```text
APPROVED by reviewer@example.com — manifest f374130bcb5ce6f1 (8 mutation(s), verification REVIEW_REQUIRED)
Summary: 0 planned, 0 written (auto), 8 written (human-approved by reviewer@example.com),
         0 queued, 0 failed, 0 skipped.
  Approval audit recorded in the catalog: approved_by=reviewer@example.com,
  at=2026-08-03T10:12:33+00:00, manifest=f374130bcb5ce6f1,
  verification_at_approval=REVIEW_REQUIRED, writes=8, failures=0
  manifest f374130bcb5ce6f1 consumed — approvals are single-use
```

> _"'Gated' has to mean 'needs a human', not 'impossible'. So the agent hands the reviewer
> exactly the list of writes it wanted to make. Approving applies those eight and nothing
> else — and the catalog records that a **human** approved them, not that a machine decided."_

### Shot 6c — the graph now knows who approved it (2:42–2:52) — B20.3

Cut to DataHub, `analytics.fct_orders` → **Properties** tab (24 blast_radius_* properties). Six of them are the
approval trail, and this is the payoff shot:

| Property (as DataHub displays it) | Value |
|---|---|
| Blast Radius Approved By | `reviewer@example.com` |
| Blast Radius Approved At | `2026-08-03T10:12:33+00:00` |
| Blast Radius Manifest Id | `f374130bcb5ce6f1` |
| Blast Radius Verification Status At Approval | `REVIEW_REQUIRED` |
| Blast Radius Approved Writes | `8` |
| Blast Radius Approved Failures | `0` |

Reference shot: `out/live_ui/16_b20_3_approval_audit_viewport.png`. Read back over GraphQL in
`out/b20_live_full_readback.txt` — **26/26 assertions pass**, covering the six audit fields, the
assessment properties, the tag, the institutional-memory link (and that its target file exists),
the description footer, and all four impacted downstreams' tags.

> _"And this is the part that outlives the run. The approval isn't a line in my terminal — it's
> in the graph. Who approved it, when, against which verdict, under which single-use manifest,
> and how many writes actually landed. Six months from now the person asking 'who signed off on
> dropping this column?' asks DataHub, not me."_

Contrast beat, if there is time — open the `verified-migration` PASS run's target: it has the
same assessment properties and **no approver field at all**.

> _"A machine decision has no approver. An automatic write carries none of these six fields, so
> you can tell the two apart by looking."_

Then, if there is time, show the line nobody can cross:

```bash
# the same approval, presented against a FAILED verification
REFUSED: fail_not_approvable — 0 mutations applied
```

> _"A FAIL can never be approved. Not by a flag, not by an env var, not by any entry point.
> There is deliberately nothing to override."_

### Shot 7 — close (2:52–3:00)

> _"DataHub provides the organizational context. Blast Radius Autopilot turns that context into
> a migration, checks its own work, and produces a defensible merge decision — PASS, REVIEW
> REQUIRED, or FAIL, with machine-readable reasons a reviewer can argue with."_

---

## Optional B-roll (only if the cut runs short)

```bash
autopilot --loop loop.config.yaml          # same code, 5 unrelated datasets
autopilot --catalog examples/showcase-ecommerce/catalog.json --fragility
```

If `--loop` is on screen, say what its summary says: it **queues every dataset and writes
nothing**, because it does not verify each fix and rule 1 gives it only the queue. Do not
describe it as writing to the catalog.

Live-MCP B-roll (needs a live DataHub) — the same code reading the real datapack over
`mcp-server-datahub`:

```bash
PATH=~/bra/venv/bin:$PATH python scripts/mcp_live_run.py --verify              # ORDER_DETAILS
PATH=~/bra/venv/bin:$PATH python scripts/mcp_live_run.py --slug mcp_live_addresses \
    --target-urn "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.addresses,PROD)" --verify
```

Both land on **coverage 5 of 24** and **5 of 17** with a **FAIL** verdict, and `get_dataset_queries`
returns **0** on both. If this is on camera, say the corpus out loud: *"the datapack ships no query
history, so this is the real SQL of the downstream definitions, read over MCP — six of the
twenty-four consumers expose any SQL at all, and the other eighteen are reported unassessed, not
safe."* Numbers: `MCP_EVIDENCE.md`, 2026-08-03 section.

---

## What PASS means, and what it does not

Keep this on screen or say it — it is the claim the whole demo rests on.

**Who may write, ever:**

| Verdict | Automatic write | Human approval |
|---|---|---|
| no `--verify` at all | **no** (`not_verified`) | no — nothing was assessed, so there is no verdict to approve |
| `PASS` | **yes** | not needed |
| `REVIEW_REQUIRED` | no | **yes** — via a bound, single-use approval manifest |
| `FAIL` | no | **never**, by any route |

**A PASS means:** the change resolved against the catalog (the table *and* the column exist),
the patch applied in isolation, every patched SQL file parsed, every patched SQL file mapped to
a catalog consumer whose impact was recomputed, no consumer's SQL was deleted or moved
somewhere it could not be re-analysed, and afterwards there are **zero** breaks, zero degrades,
zero unassessed consumers, zero unattributable references, complete coverage, no regression,
and no manual work left.

**A PASS does not mean:** anything ran. No query is executed, no warehouse is contacted, no data
is read, no dbt build is invoked. It is evidence about the SQL, not about runtime behaviour,
row counts, or results — and a reviewer still owns the decision.

---

## Rehearsal checklist

- [ ] `pytest` green — **181 tests** (98 pre-B17 + 21 B17 + 13 B18 + 34 B19 + 15 B20.3).
- [ ] PASS command rehearsed (`examples/verified-migration`) → verdict banner visible without scrolling.
- [ ] REVIEW_REQUIRED command rehearsed (`examples/showcase-ecommerce`) → `0 written / 8 queued` on screen.
- [ ] `out/` pre-cleared so files appear live on camera.
- [ ] Terminal font large; colours visible (BREAKS red / DEGRADES amber / SAFE green / verdict badge).
- [ ] Static-verification disclaimer visible in frame at least once.
- [ ] No obsolete `4 BREAKS / 2 DEGRADES` numbers anywhere on screen.
- [ ] No claim that static verification executed a query, touched a warehouse, or read data.
- [ ] No dry-run result described as "written".
- [ ] If the write-back landing is on screen: say "link to the assessment", not "the assessment
      is stored in DataHub" — the aspect holds a url + title, the body is a file.
- [ ] Opening DataHub write-back landing loaded and ready before recording.
- [ ] **Approval route rehearsed, in this order** (the manifest is single-use, so a rehearsal
      consumes it):
      1. `rm -f out/APPROVAL-*.json out/APPROVAL-*.md`
      2. run the REVIEW_REQUIRED command → confirm the `Approval manifest ->` line appears
      3. run the `--approve … --write` command → confirm `8 written (human-approved by …)`
      4. **re-generate the manifest before recording** (step 1 + 2 again), or the take will
         show `already_consumed`
- [ ] Manifest `.md` open in a second window, so the 8-row table is one keystroke away.
- [ ] Never say "the tool writes to DataHub automatically" — it does that only on a PASS.
- [ ] **Shot 6c (B20.3) needs a LIVE DataHub.** Bring it up and run the approval against it
      before recording, or the Properties tab will show the pre-approval state:
      1. `docker start datahub-opensearch-1 datahub-kafka-broker-1`, wait ~25s, then
         `docker start datahub-datahub-gms-quickstart-1 datahub-frontend-quickstart-1`;
         poll `curl localhost:8080/health` until 200 (GMS takes ~40s after the deps are up)
      2. emit the synthetic flagship datasets so the URNs resolve, then run the two-step
         approval via the CLI (this is what the video shows):
         `--verify --write` → manifest + `0 written`, then
         `--approve out/APPROVAL-… --approver reviewer@example.com --write` → `8 written
         (human-approved)`
      3. `set -a && . ./.env && set +a && python scripts/b20_live_full_readback.py \
         --approver reviewer@example.com --manifest-id <the id from step 2> --expect-writes 8`
         → must end in `ALL ASSERTIONS PASS` (26 of them)
      4. `python scripts/b20_3_capture_audit_ui.py` → refuses to pass off a screenshot that
         does not actually show the audit
- [ ] **Do NOT open the real datapack `order_entry.orders` on camera** — see the warning at the
      top. Its marks are pre-B19 and stale, and that target verifies FAIL/`no_patch_provided`,
      so nothing about it can be reproduced live. Use `analytics.fct_orders`.
- [ ] If the live MCP beat is used as B-roll, re-run both targets first
      (`scripts/mcp_live_run.py`, then `scripts/b20_capture_mcp_ui.py`) — the current captures
      are `out/live_ui/17_b20_*` and `18_b20_*`; the `08_b15_*`/`09_b15_*` shots are superseded.
- [ ] The approver shown on camera is a synthetic address (`reviewer@example.com`) — the six
      audit properties are a real person's identity in a real catalog, so do not film a
      colleague's.
- [ ] Video under three minutes.
