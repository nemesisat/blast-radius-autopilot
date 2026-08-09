# Recording guide — how to actually shoot the demo

`demo_script.md` says **what** to show and say. This says **how to record it**.
Budget: ~2 hours end to end, including retakes. No paid software needed.

> **Golden rule: record in short clips, one per shot. Never attempt one perfect 3-minute take.**
> If a clip goes wrong you re-shoot 20 seconds, not everything.

---

## Phase 0 — Set the stage (20 min, do this once)

**Machine hygiene**
- [ ] Turn on **Do Not Disturb** (macOS: Control Centre → Focus). No notification banners on camera.
- [ ] Quit Slack, Mail, Messages, anything that can pop a toast.
- [ ] Clean the desktop, or record a **window only** rather than the full screen.
- [ ] Close every browser tab except the ones you need. Hide the bookmarks bar (`⌘⇧B`).

**Terminal**
- [ ] New window, dark theme, **font size up** (`⌘+` five or six times — text must be readable at 1080p).
- [ ] Make it wide enough that the scorecard and verification table don't wrap.
- [ ] `cd` into the project and activate the venv **before** you start recording.
- [ ] Practise `clear` between shots so each clip starts clean.

**Secrets — non-negotiable**
- [ ] Never open `.env` on camera. Never `cat` it, never `env | grep`.
- [ ] If your prompt shows a token or a path you'd rather not publish, change the prompt first.
- [ ] Use a **throwaway DataHub token**; you can revoke it after recording.

**Browser / DataHub**
- [ ] Log into DataHub **before** recording (you don't want the login screen in the video).
- [ ] Pre-open tabs: the `analytics.fct_orders` asset page, `out/b17_pass_report.html`,
      `out/SWEEP.html`.

---

## Phase 1 — Warm everything up (20 min) — the step people skip

Run every command **once, before recording**. Cold runs are slow (imports, compilation, first
MCP pull) and slow is what kills a 3-minute video.

```bash
cd ~/Desktop/AIProject/DataHubHackathon/blast-radius-autopilot
source .venv/bin/activate          # or your venv path

# 1. DataHub up and the asset showing its marks (Shot 0)
datahub docker quickstart          # if not already running
open http://localhost:9002         # search analytics.fct_orders — confirm tags/properties visible

# 2. Warm the offline shots
autopilot --catalog examples/verified-migration/catalog.json \
          --change "drop analytics.fct_signups.referrer_code" --verify

# 3. Warm the sweep
autopilot --sweep --catalog examples/showcase-ecommerce/catalog.json --sweep-limit 13
```

⚠️ **The manifest is single-use.** If you rehearse the approval beat, that manifest is burned.
Before the real take, regenerate a **fresh** manifest, then approve it on camera. Rehearse →
regenerate → record. Do not skip this or the approval will fail live with `already_consumed`.

---

## Phase 2 — Record the clips (40 min)

**Tool: macOS built-in.** `⌘⇧5` → "Record Selected Portion" → drag around your terminal or
browser window → Record. Stop from the menu bar. Each clip lands on the Desktop as `.mov`.

Record in this order, one clip each, naming them `01_...`, `02_...` so assembly is trivial:

| Clip | What's on screen | Target length |
|---|---|---|
| 01 | DataHub UI: `analytics.fct_orders` with the tags, `blast_radius_*` properties, footer, assessment link | 0:20 |
| 02 | Terminal: the impact run — scorecard + coverage | 0:25 |
| 03 | Terminal: the two generated dbt patches | 0:20 |
| 04 | Terminal: `--verify` → the ✅ PASS verification table | 0:35 |
| 05 | Terminal: the FAIL / REVIEW case — the agent refusing | 0:25 |
| 06 | Terminal: manifest → `--approve … --approver you` → writes land; then the DataHub UI showing the approval audit fields | 0:30 |
| 07 | Browser: `out/SWEEP.html` ledger — verified safe / needs review / landmines | 0:15 |

**≈2:50 total. Aim to come in under 3:00 with room to spare — judges are not required to watch past three minutes.**

Tips that matter:
- Pause ~1 second after a command finishes before you stop recording. Gives you clean trim points.
- If you fluff a line, **stop, re-record that clip only.**
- Move the mouse slowly and deliberately. Point at the number you're talking about.
- Don't scroll fast. If something's below the fold, scroll it into view *before* you start talking.

---

## Phase 3 — Narration (30 min)

Two options — pick one:

**A. Narrate live while recording** (simpler). Read the italic lines from `demo_script.md` as
you drive. Use the built-in mic; sit close; no fan noise.

**B. Silent clips + voiceover after** (better result, needs editing). Record the clips silent,
assemble them in iMovie, then record one continuous voiceover over the timeline.

Either way, **write your lines down first** and read them. Improvised narration runs long and
wanders, and length is your hard constraint.

Lines you must not fluff:
- The opener: *"DataHub's Impact Analysis shows you the blast radius. Blast Radius Autopilot defuses it — and then checks its own work."*
- The honesty line: *"This is static verification — the patch applies and the SQL parses. **No query was executed.**"*
- The gate: *"No PASS, no automatic write. A human approved this, and the catalog records who."*

---

## Phase 4 — Assemble (20 min)

**iMovie** (free, pre-installed):
1. New Movie → drag the clips in, in order.
2. Trim dead air at each clip's head and tail.
3. Add a 4-second title card at the front: **Blast Radius Autopilot** + the tagline.
4. Optional end card: repo URL.
5. Check the total duration. **Must be under 3:00.**
6. Share → File → 1080p → Best quality.

No music. It adds nothing and the rules restrict third-party copyrighted audio.

---

## Phase 5 — Upload (10 min)

1. YouTube → Create → Upload video.
2. Visibility: **Public.** (The rules require public visibility — not Unlisted, not Private.)
3. Title: `Blast Radius Autopilot — DataHub Agent Hackathon`
4. Description: the tagline + the GitHub repo URL + a one-line note that verification is static.
5. **Not** made for kids.
6. Copy the URL → paste into the Devpost form.

---

## Phase 6 — Final check before you call it done

- [ ] Watch it start to finish, once, all the way through.
- [ ] Under 3:00.
- [ ] Audio audible the whole way; no long silences.
- [ ] **No token, no `.env`, no private path on screen** — scrub through and check.
- [ ] The numbers on screen match the numbers you say out loud.
- [ ] The "no query was executed" line is in there.
- [ ] It's Public and the link opens in a private browser window.
- [ ] Revoke the throwaway DataHub token if you used one.

---

## If you only have 45 minutes

Cut to four clips: **01** (DataHub end state) → **04** (PASS verification) → **06** (refuse →
approve → write lands) → **07** (sweep ledger). Narrate live. That is still a complete story:
*it assesses, it proves, it refuses, a human approves, and it did the whole catalog.*
