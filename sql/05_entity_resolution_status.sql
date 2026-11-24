-- How many distinct raw asset names ended up matched, under review or unmatched.
SELECT source,
       status,
       count(*) AS distinct_names,
       round(avg(confidence), 3) AS avg_confidence
FROM entity_map
GROUP BY source, status
ORDER BY source, status
