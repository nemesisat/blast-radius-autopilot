# Demo script (< 3 minutes)

Judges watch at most 3 minutes and score "Submission Quality" equally with
everything else. Show the loop: **read lineage → detect skew → write back**, and
end on the payoff — the diagnosis living in DataHub.

## Shot list (~2:45)

**0:00–0:20 — The problem.**
One line: "AI models fail silently when their input data drifts. Nothing errors —
the model just gets worse. The Skew Sentinel catches that from DataHub's ML
lineage." Show the model page in DataHub, healthy.

**0:20–0:45 — The graph.**
Show the lineage: training data → feature table → NYC Taxi Fare Predictor.
"The model was trained on a snapshot. We captured that baseline at seed time."

**0:45–1:30 — Run the Sentinel.**
Terminal: `python -m sentinel.run --online --serving-data data/nyc_taxi_live.csv`
Narrate as it prints: it traverses lineage, finds `trip_distance` shifted
(PSI 1.32), `pickup_zone` dropped from the schema, and the table is 72h stale.
Verdict: AT RISK, drift score 1.9.

**1:30–2:15 — The write-back (the money shot).**
Re-run with `--write`. Then refresh the model page in DataHub: the `at-risk` tag,
the `skew_drift_score` structured property, and the root-cause knowledge doc are
now attached. "The next engineer inherits the diagnosis — the agent contributed
back to the graph."

**2:15–2:45 — Why it matters + OSS.**
"Training/serving skew is a top ML failure mode. This runs entirely on
open-source DataHub over MCP." Flash the PR to `datahub-skills` packaging the
check as a reusable Skill. End on the tagged model.

## Recording tips
- 1080p, terminal font size up, hide secrets (use a throwaway token).
- Pre-seed everything; only record the run + the DataHub refresh.
- Put the one-sentence value prop as the video title/first caption.
- Upload to YouTube/Vimeo, **public**, link on the Devpost submission.
