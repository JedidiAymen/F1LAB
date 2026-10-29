-- Mean pace delta by season, next-lap compound and 5-lap tyre-age bucket on green laps.
SELECT year,
       compound_next,
       CAST(FLOOR(tyre_age_next / 5) AS INT) * 5 AS tyre_age_bucket,
       COUNT(*)                                  AS n,
       AVG(delta_seconds)                        AS mean_delta_seconds,
       STDDEV_SAMP(delta_seconds)                AS std_delta_seconds
FROM src
WHERE eligible_green_next AND tyre_age_next IS NOT NULL
GROUP BY year, compound_next, CAST(FLOOR(tyre_age_next / 5) AS INT) * 5
ORDER BY year, compound_next, tyre_age_bucket
