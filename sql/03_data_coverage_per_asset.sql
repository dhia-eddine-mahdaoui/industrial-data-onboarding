-- Data coverage per asset and sensor after cleaning: samples kept against the
-- samples a gap-free series would hold at the base sampling step, plus the
-- number of gaps. Assets without any sensor data still appear (coverage NULL).
WITH deltas AS (
  SELECT asset_id, sensor, ts_utc, gap_before,
         unix_timestamp(ts_utc)
           - unix_timestamp(lag(ts_utc) OVER (PARTITION BY asset_id, sensor ORDER BY ts_utc)) AS dt
  FROM readings
),
step AS (
  SELECT min(dt) AS step_s FROM deltas WHERE dt > 0
),
series AS (
  SELECT asset_id, sensor,
         count(*) AS samples,
         min(ts_utc) AS first_at,
         max(ts_utc) AS last_at,
         sum(CASE WHEN gap_before THEN 1 ELSE 0 END) AS gaps
  FROM deltas
  GROUP BY asset_id, sensor
)
SELECT a.asset_id,
       a.asset_name,
       s.sensor,
       s.samples,
       s.first_at,
       s.last_at,
       round(100.0 * s.samples
             / ((unix_timestamp(s.last_at) - unix_timestamp(s.first_at)) / st.step_s + 1), 1)
         AS coverage_pct,
       s.gaps
FROM assets a
CROSS JOIN step st
LEFT JOIN series s ON a.asset_id = s.asset_id
ORDER BY a.asset_id, s.sensor
