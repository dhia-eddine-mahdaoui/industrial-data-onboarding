-- Anomalous sensor readings in the 72 hours before each failure event.
SELECT f.asset_id,
       f.wo_number,
       f.opened_at_utc AS failure_at,
       count(*) AS anomalous_readings_72h,
       min(a.ts_utc) AS first_anomaly_at,
       round(max(abs(a.z_score)), 2) AS max_abs_z
FROM maintenance_events f
JOIN readings a
  ON a.asset_id = f.asset_id
 AND a.is_anomaly
 AND a.ts_utc BETWEEN f.opened_at_utc - INTERVAL 72 HOURS AND f.opened_at_utc
WHERE f.is_failure
GROUP BY f.asset_id, f.wo_number, f.opened_at_utc
ORDER BY failure_at
