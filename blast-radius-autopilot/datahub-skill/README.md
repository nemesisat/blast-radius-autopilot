# DataHub Skill — column-impact-from-queries

Packaged from [Blast Radius Autopilot](../README.md) as a standalone, reusable DataHub Skill:
**evidence-backed column-level impact from available query history and downstream SQL
definitions**, with unparseable, ambiguous, and non-SQL consumers reported explicitly
rather than assumed unaffected.

See [`SKILL.md`](./SKILL.md) for the manifest, inputs, and output schema.

```bash
pip install -e ..           # or: pip install blast-radius-autopilot
python skill.py --catalog ../examples/showcase-ecommerce/catalog.json \
                --dataset analytics.fct_orders --column customer_zip --op drop
```

## Contributing this to `datahub-skills`

This folder is PR-ready. Opening the upstream PR requires the maintainer's GitHub
auth, so it is listed under **Human-only remaining** in the project `PROGRESS.md`.
The suggested steps (for the human):

1. Fork `acryldata/datahub-skills` (or the repo named on the hackathon rules page).
2. Copy this `datahub-skill/` folder in following that repo's contribution layout.
3. Confirm Apache-2.0 (already declared in `SKILL.md`) and that examples use only
   public/synthetic data.
4. Open the PR referencing the Blast Radius Autopilot project.

Apache-2.0. Public/synthetic data only.
