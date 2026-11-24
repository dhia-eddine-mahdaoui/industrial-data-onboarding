-- Hours since the last logged maintenance event for each asset, as of the
-- latest sensor reading in the dataset.
WITH ref AS (
  SELECT max(ts_utc) AS as_of FROM readings
),
last_maint AS (
  SELECT m.asset_id, max(m.opened_at_utc) AS last_maintenance_at
  FROM maintenance_events m
  CROSS JOIN ref r
  WHERE m.opened_at_utc <= r.as_of
  GROUP BY m.asset_id
)
SELECT a.asset_id,
       a.asset_name,
       lm.last_maintenance_at,
       round((unix_timestamp(r.as_of) - unix_timestamp(lm.last_maintenance_at)) / 3600, 1)
         AS hours_since_last_maintenance
FROM assets a
CROSS JOIN ref r
LEFT JOIN last_maint lm ON a.asset_id = lm.asset_id
ORDER BY hours_since_last_maintenance DESC NULLS LAST
