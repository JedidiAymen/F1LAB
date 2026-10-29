-- Per-race summary of next-lap targets. Portable SQL: runs unchanged on DuckDB and Spark (view name: src).
SELECT race_id,
       COUNT(*)                                                    AS rows_total,
       SUM(CASE WHEN eligible_green_next THEN 1 ELSE 0 END)        AS rows_green,
       AVG(CASE WHEN eligible_green_next THEN ABS(delta_seconds) END) AS mean_abs_delta_green,
       SUM(CASE WHEN eligible_green_next AND ABS(delta_seconds) > 8 THEN 1 ELSE 0 END) AS outliers_gt_8s
FROM src
GROUP BY race_id
ORDER BY race_id
