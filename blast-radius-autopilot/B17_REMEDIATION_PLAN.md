# B17 Remediation Plan: Proof-Carrying Migration Hardening

## Objective

Close the remaining false-PASS paths, make write-back reporting truthful, and update the demo so it accurately presents the Proof-Carrying Migration feature.

> **Safety principle:** A migration may PASS only when every known consumer is confidently assessed and no unresolved impact remains.

---

## Priority summary

| ID | Fix | Priority | Why |
|---|---|---:|---|
| B17.1 | Ambiguous references must block PASS | P0 | Confirmed false-PASS path |
| B17.2 | Remaining `DEGRADES` must block PASS | P0 | Confirmed false-PASS path |
| B17.3 | Unmapped patched SQL must block PASS | P0 | Patch effect was not recomputed |
| B17.4 | Correct write-back result accounting | P0 | Dry-run and failed writes can be reported as written |
| B17.5 | Update the three-minute demo | P1 | Current demo does not show B16 |
| B17.6 | Fix stale claims and PR wording | P1 | Documentation contradicts current evidence |
| B17.7 | Improve verification screenshots | P1 | PASS and REVIEW are not immediately visible |
| B17.8 | Add PR-native CI only if time remains | P2 | Valuable, but not required before correctness |

---

# B17.1: Ambiguous references must block PASS

## Problem

An unqualified column may exist on multiple joined tables:

```sql
SELECT o.order_id
FROM analytics.orders o
JOIN analytics.bonus b ON o.order_id = b.id
WHERE customer_zip IS NOT NULL
```

The analyser correctly marks this as:

```text
confidence = low
ambiguous = true
```

However, ambiguity does not currently force review.

A verified scenario produced:

```text
Before:
breaks = 1
ambiguous = 1

After:
breaks = 0
ambiguous = 1

Current status:
PASS
```

This is unsafe because the remaining reference cannot be confidently attributed.

## Required behaviour

```text
ambiguous_after > 0
-> REVIEW_REQUIRED
-> auto_applicable = false
-> all write-back mutations queued
```

Ambiguous consumers should remain separate from `UNKNOWN` because the SQL parsed successfully. They should still block automatic approval.

## Suggested reason code

```python
R_AMBIGUOUS_PRESENT = "ambiguous_consumers_present"
```

Suggested human-readable reason:

```text
At least one column reference could not be confidently attributed to a source table.
```

## Likely files

- `src/autopilot/schema.py`
- `src/autopilot/verify.py`
- `src/autopilot/writeback.py`
- `src/autopilot/report_pr.py`
- `src/autopilot/report_html.py`
- `src/autopilot/assessment.py`
- `tests/test_safety.py`
- `tests/test_verify.py`

## Required tests

```python
def test_ambiguous_reference_forces_impact_review():
    assert report.ambiguous
    assert report.review_required() is True
    assert report.auto_applicable() is False
```

```python
def test_ambiguous_reference_blocks_verification_pass():
    assert result.after["breaks"] == 0
    assert result.after["ambiguous"] == 1
    assert result.status == "REVIEW_REQUIRED"
    assert "ambiguous_consumers_present" in result.reasons
    assert result.auto_applicable is False
```

```python
def test_ambiguous_verification_queues_all_writeback():
    assert mutations
    assert all(not mutation.auto for mutation in mutations)
```

---

# B17.2: Remaining DEGRADES must block PASS

## Problem

The verifier currently blocks only **new** degradations. It can PASS while an existing `DEGRADES` consumer remains.

Confirmed scenario:

```text
Before:
breaks = 1
degrades = 1

After:
breaks = 0
degrades = 1

Current status:
PASS
```

Example degraded consumer:

```sql
SELECT *
FROM analytics.orders
```

Dropping a column may not stop this query from executing, but it changes the output schema. That can still break downstream contracts.

## Required behaviour

Strict PASS should require:

```text
breaks_after == 0
degrades_after == 0
unknown_after == 0
ambiguous_after == 0
coverage complete
```

A remaining degradation should produce:

```text
REVIEW_REQUIRED
```

A newly introduced degradation or a previously safe consumer becoming degraded should continue to produce:

```text
FAIL
```

## Suggested reason code

```python
R_DEGRADES_REMAINING = "degrades_remaining"
```

Suggested human-readable reason:

```text
One or more consumers still execute with changed output or behaviour.
```

## Required tests

```python
def test_existing_degrade_blocks_pass():
    assert result.after["breaks"] == 0
    assert result.after["degrades"] == 1
    assert result.status == "REVIEW_REQUIRED"
    assert "degrades_remaining" in result.reasons
```

```python
def test_new_degrade_is_failure():
    assert result.status == "FAIL"
    assert "new_degrades" in result.reasons
```

```python
def test_zero_residual_impact_can_pass():
    assert result.after["breaks"] == 0
    assert result.after["degrades"] == 0
    assert result.after["unknown"] == 0
    assert result.after["ambiguous"] == 0
    assert result.status == "PASS"
```

---

# B17.3: Unmapped patched SQL must block PASS

## Problem

The verifier maps patched files through:

```text
Asset.dbt_path
-> Asset.defining_query_id
-> Query
```

If a patched SQL file cannot be mapped, the verifier currently adds only a note:

```text
patched SQL file maps to no catalog consumer
its effect on impact could not be recomputed
```

The result may still PASS even though part of the patch was excluded from recomputed impact.

## Required behaviour

```text
patched SQL file cannot be mapped
-> REVIEW_REQUIRED
```

The result should explicitly expose all unmapped files.

## Suggested additions

```python
VerificationResult.unmapped_files: list[str]
```

```python
R_PATCHED_FILE_UNMAPPED = "patched_file_unmapped"
```

Suggested reason:

```text
At least one patched SQL file could not be connected to a catalog consumer, so its impact was not recomputed.
```

## Required tests

```python
def test_unmapped_patched_sql_blocks_pass():
    assert result.unmapped_files
    assert result.status == "REVIEW_REQUIRED"
    assert "patched_file_unmapped" in result.reasons
    assert result.auto_applicable is False
```

```python
def test_unmapped_files_appear_in_json_and_markdown():
    assert "unmapped_files" in verification_json(result)
    assert "could not be mapped" in render_verification_md(result)
```

---

# B17.4: Correct write-back result accounting

## Problem

Dry-run output currently says:

```text
WRITE-BACK (dry-run):
[dry-run] would apply: ...
Summary: 6 written
```

No mutation was actually written.

The current logic adds a mutation to `written` before checking `dry_run`:

```python
res.written.append(...)
if not self.dry_run:
    self._emit(m)
```

There is a second problem: `_emit()` catches exceptions internally. A failed live mutation may still be counted as written.

## Required result states

`WriteBackResult` should distinguish:

```text
planned
queued_for_review
written
failed
skipped
```

## Required dry-run behaviour

```text
6 planned
0 written
0 queued
0 failed
```

Suggested output:

```text
Summary: 6 planned, 0 written, 0 queued, 0 failed.
```

## Required successful live behaviour

```text
0 planned
6 written
0 queued
0 failed
```

## Required partial-failure behaviour

```text
0 planned
4 written
0 queued
2 failed
```

Each failed mutation should include:

- mutation tool;
- target URN;
- error message.

## Implementation rule

Only append to `written` after successful emission:

```python
if self.dry_run:
    res.planned.append(mutation_id)
else:
    try:
        self._emit(m)
        res.written.append(mutation_id)
    except Exception as error:
        res.failed.append({
            "mutation": mutation_id,
            "error": str(error),
        })
```

Do not swallow the error inside `_emit()` without returning failure information.

The system may continue processing later mutations, but the final result must show partial failure honestly.

## Required tests

```python
def test_dry_run_reports_planned_not_written():
    assert len(result.planned) > 0
    assert result.written == []
    assert result.failed == []
```

```python
def test_successful_live_emit_counts_written():
    assert len(result.written) == expected
    assert result.failed == []
```

```python
def test_failed_emit_is_not_counted_as_written():
    assert failed_mutation not in result.written
    assert failed_mutation in result.failed
```

```python
def test_partial_write_failure_is_reported():
    assert len(result.written) == successful_count
    assert len(result.failed) == failed_count
```

---

# B17.5: Rewrite the three-minute demo

## Current problems

`demo/demo_script.md` still contains old information:

- no `--verify`;
- `4 BREAKS / 2 DEGRADES`;
- filter-only references described as `DEGRADES`;
- `38 tests`;
- overlapping timestamps;
- no Proof-Carrying Migration demonstration.

Current verified status is:

```text
98 tests passing
Filter/JOIN/GROUP references -> BREAKS
Proof-Carrying Migration -> PASS / REVIEW_REQUIRED / FAIL
```

## Recommended golden-path demo

### Shot 1: Proposed change, 0:00-0:20

Show:

```text
drop analytics.fct_signups.referrer_code
```

Say:

> “A developer wants to remove one column. Before it merges, Autopilot asks DataHub who depends on it.”

### Shot 2: Original blast radius, 0:20-0:45

Show:

```text
2 BREAKS
1 SAFE
3 of 3 analysed
Risk: HIGH
```

### Shot 3: Generated migration, 0:45-1:10

Show the two minimal dbt patches:

```text
rpt_referrals.sql
rpt_signups_by_plan.sql
```

Say:

> “Generating a patch is easy. Trusting it blindly is not.”

### Shot 4: Verification, 1:10-1:40

Run:

```bash
autopilot \
  --catalog examples/verified-migration/catalog.json \
  --change "drop analytics.fct_signups.referrer_code" \
  --verify \
  --html out/b16_pass_report.html \
  --json out/b16_pass.json
```

Show:

```text
breaks: 2 -> 0
safe: 1 -> 3
coverage: 3 of 3
status: PASS
```

Say:

> “The patch was applied in isolation, the SQL was parsed again, and the blast radius was recomputed.”

### Shot 5: Fail-closed contrast, 1:40-2:05

Show the flagship result:

```text
breaks: 6 -> 5
status: REVIEW REQUIRED
manual work: 5 consumers
write-back: 0 written / 8 queued
```

Say:

> “It fixed the dbt model, but five dashboards and queries remain. The agent refuses to approve the migration.”

### Shot 6: DataHub contribution, 2:05-2:35

Show:

- verification status;
- coverage;
- before/after counts;
- structured properties;
- impact assessment;
- queued or written mutations.

### Shot 7: Close, 2:35-3:00

> “DataHub provides the organizational context. Blast Radius Autopilot turns that context into a migration, checks its own work, and produces a defensible merge decision.”

## Rehearsal checklist

```markdown
- [ ] Full suite shows 98 or more tests passing.
- [ ] PASS command rehearsed.
- [ ] REVIEW_REQUIRED command rehearsed.
- [ ] Verification card visible without excessive scrolling.
- [ ] Static-verification disclaimer visible.
- [ ] No obsolete 4 BREAKS / 2 DEGRADES numbers.
- [ ] No claim that static verification executed queries.
- [ ] No dry-run result described as written.
- [ ] Video remains under three minutes.
```

---

# B17.6: Correct stale claims

## Files requiring review

- `DESIGN.md`
- `datahub-skill/SKILL.md`
- `datahub-skill/README.md`
- `pyproject.toml`
- `demo/demo_script.md`
- older generated files under `out/`

## Remove or qualify

Avoid:

```text
exact column-level fallout
from your real query history
opens the PR
all downstream consumers analysed
verified migration
```

unless the supporting evidence exists for that specific run.

## Preferred product wording

```text
Blast Radius Autopilot computes evidence-backed column-level impact from available query history and downstream SQL definitions, while explicitly reporting unparseable, ambiguous, and non-SQL consumers.
```

## Preferred verification wording

```text
Static migration verification applies the generated patch in an isolated copy, re-parses the patched SQL, and recomputes the known blast radius. It does not execute queries, contact a warehouse, validate row-level results, or replace human approval.
```

## Preferred PR wording

The CLI does not currently open a real GitHub PR.

Replace:

```text
opens the PR
```

with:

```text
generates an applicable patch and a CI-ready PR comment
```

The tested `open_local_pr()` helper may be mentioned separately:

```text
A tested local-PR helper can create a branch, apply the patch, commit it, and generate the review comment without requiring GitHub credentials.
```

---

# B17.7: Improve screenshots and verification UI

## PASS screenshot

Current issue:

- screenshot mostly shows the original blast radius;
- actual PASS result is below the visible area.

Required screenshot content:

```text
STATIC VERIFICATION
PASS
Breaks 2 -> 0
Safe 1 -> 3
Coverage 3 of 3
```

## REVIEW_REQUIRED screenshot

Current issue:

- the visible screenshot shows `CRITICAL`;
- it does not visibly show `REVIEW REQUIRED`.

Required screenshot content:

```text
REVIEW REQUIRED
Breaks 6 -> 5
5 consumers need manual work
0 written
8 queued
```

## Verification-card improvements

Current card visually shows:

```text
PASS PASS
```

Use one badge:

```text
STATIC CHECK: PASS
```

Move the limitation closer to the verdict:

```text
Static evidence only. No queries were executed.
```

Suggested hierarchy:

```text
STATIC MIGRATION CHECK: PASS

Breaks:       2 -> 0
Degrades:     0 -> 0
Unassessed:   0 -> 0
Ambiguous:    0 -> 0
Coverage:     3 of 3

No queries were executed.
```

---

# B17.8: Optional PR-native CI

Only do this after B17.1 through B17.7 are complete.

A minimal GitHub Action could:

```text
PR opened or updated
-> detect supplied schema change
-> run Autopilot
-> generate verification JSON
-> post PR comment
-> set check status
```

Suggested mapping:

| Verification | GitHub Check |
|---|---|
| `PASS` | Success |
| `REVIEW_REQUIRED` | Neutral or action required |
| `FAIL` | Failure |

Do not build a full GitHub App unless time comfortably allows it.

---

# Final PASS definition

A migration may receive `PASS` only when all conditions are true:

```text
✓ Patch applied successfully
✓ Every patched SQL file parsed
✓ Every patched SQL file remained in scope
✓ Every patched SQL file mapped to a catalog consumer
✓ Breaks after = 0
✓ Degrades after = 0
✓ Unknown after = 0
✓ Ambiguous after = 0
✓ Coverage is complete
✓ No previously safe consumer regressed
✓ No residual dropped-column references remain
✓ No manual work remains
```

Otherwise:

```text
Broken, invalid, out-of-scope, or regressive patch
-> FAIL
```

```text
Improved but incomplete, ambiguous, degraded, unmapped, or partially assessed
-> REVIEW_REQUIRED
```

---

# Definition of done

```markdown
- [ ] Ambiguous references force REVIEW_REQUIRED.
- [ ] Remaining DEGRADES force REVIEW_REQUIRED.
- [ ] Unmapped patched SQL forces REVIEW_REQUIRED.
- [ ] Dry-run mutations are reported as planned, not written.
- [ ] Failed live mutations are reported as failed, not written.
- [ ] Full test suite passes.
- [ ] New regression tests reproduce all previously confirmed false-PASS paths.
- [ ] Demo script uses current semantics and current test count.
- [ ] PASS screenshot visibly shows the verification result.
- [ ] REVIEW_REQUIRED screenshot visibly shows the verification result.
- [ ] “Exact” and unsupported “real query history” claims are removed.
- [ ] “Opens the PR” is qualified unless actually wired into the CLI.
- [ ] Static limitations remain visible in every verification artifact.
- [ ] Canonical and Desktop project copies match.
```

## Final verification command

```bash
cd ~/bra/blast-radius-autopilot

PYTHONDONTWRITEBYTECODE=1 \
../venv/bin/python -m pytest -q -p no:cacheprovider
```

Expected:

```text
All tests pass, including the new B17 regression tests.
```
