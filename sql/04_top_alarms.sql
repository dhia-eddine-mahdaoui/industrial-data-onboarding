-- Assets and sensors with the most alarms (anomalous or spiking samples).
SELECT r.asset_id,
       a.asset_name,
       r.sensor,
       sum(CASE WHEN r.is_anomaly THEN 1 ELSE 0 END) AS anomalies,
       sum(CASE WHEN r.is_spike THEN 1 ELSE 0 END) AS spikes,
       round(max(abs(r.z_score)), 1) AS max_abs_z,
       max(CASE WHEN r.is_anomaly OR r.is_spike THEN r.ts_utc END) AS last_alarm_at
FROM readings r
JOIN assets a ON a.asset_id = r.asset_id
GROUP BY r.asset_id, a.asset_name, r.sensor
HAVING sum(CASE WHEN r.is_anomaly OR r.is_spike THEN 1 ELSE 0 END) > 0
ORDER BY anomalies DESC, spikes DESC, r.asset_id
LIMIT 10
