# Final submission — commands + copy

Everything below runs from the project root:
`~/Desktop/AIProject/DataHubHackathon`

---

## Step 0 — two edits first (5 min, do NOT skip)

**a) Fix the LICENSE copyright line.** It still says "Data Necromancer contributors" from when the
file was restored after the rsync deleted it.

```bash
grep -n "Copyright" blast-radius-autopilot/LICENSE
# edit that one line to: Copyright 2026 <Your Name>
```

**b) Fix the Skill homepage placeholder.**

```bash
grep -n "your-org" blast-radius-autopilot/datahub-skill/SKILL.md
# replace <your-org>/blast-radius-autopilot with your real GitHub path
```

---

## Step 1 — safety sweep before anything is public

```bash
cd ~/Desktop/AIProject/DataHubHackathon

# Nothing secret is tracked (must print nothing)
git ls-files | grep -iE '\.env$|token|secret|credential'

# No API keys anywhere in tracked files (must print nothing)
git grep -nE '(sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,})' -- . || echo "clean"

# .gitignore covers the right things
grep -E '\.env|\.venv|__pycache__|egg-info|pytest_cache' .gitignore
```

If `.env` is tracked: `git rm --cached blast-radius-autopilot/.env` and add it to `.gitignore`.

---

## Step 2 — commit and push

```bash
git add -A
git status                      # eyeball the list once
git commit -m "Blast Radius Autopilot — DataHub Agent Hackathon submission"
git branch -M main
```

Create an **empty public repo** on GitHub named `blast-radius-autopilot` (no README, no
.gitignore, no licence — you already have them), then:

```bash
git remote add origin https://github.com/<YOU>/blast-radius-autopilot.git
git push -u origin main
```

**On the GitHub repo page:**
- Click the ⚙️ next to **About** → add the elevator pitch as the description.
- Confirm the sidebar shows **Apache-2.0** under About. If it doesn't, GitHub didn't detect the
  licence — check `LICENSE` is at a path it scans and the text is unmodified Apache-2.0.
- Add topics: `datahub` `mcp` `data-engineering` `dbt` `sqlglot` `ai-agent`

---

## Step 3 — judge simulation (5 min, catches the embarrassing stuff)

Do exactly what a judge does — clone your own repo somewhere clean:

```bash
cd /tmp && rm -rf judge && git clone https://github.com/<YOU>/blast-radius-autopilot.git judge
cd judge/blast-radius-autopilot        # adjust if repo root differs
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest                                  # expect 198 passed

autopilot --catalog examples/verified-migration/catalog.json \
          --change "drop analytics.fct_signups.referrer_code" --verify
# expect ✅ PASS, breaks 2 -> 0
```

If anything fails here, it fails for the judge too. Fix, commit, push again.

---

## Step 4 — the `datahub-skills` PR

```bash
# Fork https://github.com/datahub-project/datahub-skills on GitHub, then:
cd /tmp && git clone https://github.com/<YOU>/datahub-skills.git && cd datahub-skills
git checkout -b add-column-impact-from-queries
```

Look at how existing skills are laid out in that repo and match it (likely
`skills/<name>/SKILL.md`). Copy your skill in, then:

```bash
git add -A
git commit -m "Add column-impact-from-queries skill"
git push -u origin add-column-impact-from-queries
```

Open the PR with this description:

> ### `column-impact-from-queries`
>
> A reusable Skill that computes the **column-level** blast radius of a proposed schema change
> from a dataset's real query history and downstream SQL definitions.
>
> Given `{dataset, column, op}` it reads schema, downstream lineage and SQL, runs a `sqlglot`
> column-usage engine over each query, and returns structured JSON classifying every consumer as
> **BREAKS / DEGRADES / SAFE / UNKNOWN**, with counts, risk and per-query verdicts.
>
> **Why it may be useful here:** viewing downstream lineage is already shipped. This adds two
> things on top — it resolves impact down to the *column*, and it also catches columns referenced
> only in `WHERE` / `JOIN` / `GROUP BY`, which the SQL-parsing docs note are excluded from lineage.
> The output is structured, so it drops straight into a CI check or a PR comment.
>
> **Fail-closed by design:** a query that cannot be parsed is reported as `UNKNOWN`, never as
> safe, and coverage ("N of M analysed") is reported as its own dimension so an unreadable
> consumer is never silently counted as a clean one.
>
> Runs offline against a catalog JSON, or online against a live instance. Apache-2.0.
> Built during Build with DataHub: The Agent Hackathon —
> full project: https://github.com/<YOU>/blast-radius-autopilot

---

## Step 5 — Devpost form

| Field | Value |
|---|---|
| Project name | `Blast Radius Autopilot` |
| Elevator pitch | DataHub shows the blast radius of a schema change. Autopilot defuses it — impact, dbt fix, self-verification, gated write-back — one column, or a ranked ledger for the whole catalog. |
| About the project | paste everything below the `---` in `DEVPOST_ABOUT.md` |
| Built with | `datahub, mcp, mcp-server-datahub, python, sqlglot, graphql, dbt, docker, git, pytest, playwright, html, svg, claude` |
| Repo URL | your public GitHub URL |
| Video URL | your public YouTube URL |
| Try it / project URL | the repo URL (setup instructions are in the README) |
| Category | **Metadata-Aware Code Generation & Development** (add *Agents That Do Real Work* only if the form allows multiple) |
| DataHub technologies | ✅ DataHub OSS / Core Platform · ✅ DataHub MCP Server · ✅ DataHub Skills |
| Feedback survey | **Opt in** — $50 × 10 awards, near-free |

---

## Step 6 — last checks before you hit submit

- [ ] Video is **Public** on YouTube (not Unlisted) — open the link in a private window
- [ ] Repo is **public** — open it in a private window
- [ ] **Apache-2.0 visible in the repo About sidebar**
- [ ] Fresh-clone test passed (Step 3)
- [ ] Skill PR link included
- [ ] Feedback survey opted into
- [ ] Disclose AI-assisted development if the form asks — the rules permit it, they just want it stated

**Deadline: Aug 10, 5:00pm EDT.** Submit early; you can keep editing the submission until then.
