-- rpt_diagnoses: encounter-level diagnosis + cost (SYNTHETIC data only).
-- Owned by team:clinical-data. Downstream of clinical.encounters.
SELECT
    encounter_id,
    diagnosis_code,
    cost
FROM clinical.encounters
WHERE encounter_date >= '2026-01-01'
