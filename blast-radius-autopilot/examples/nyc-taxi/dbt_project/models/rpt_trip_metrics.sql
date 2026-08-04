-- rpt_trip_metrics: per-trip distance + fare for operational reporting.
-- Owned by team:mobility-data. Downstream of nyc.trips.
SELECT
    trip_id,
    trip_distance,
    fare_amount
FROM nyc.trips
WHERE passenger_count > 0
