-- Forecast accuracy per season and model on green-eligible laps: MAE, MAPE (%) and bias (prediction - truth, s).
SELECT year, model,
       COUNT(*)                                                  AS n,
       AVG(ABS(pred_seconds - next_lap_seconds))                 AS mae_s,
       AVG(ABS(pred_seconds - next_lap_seconds) / next_lap_seconds) * 100 AS mape_pct,
       AVG(pred_seconds - next_lap_seconds)                      AS bias_s
FROM src
WHERE eligible_green_next AND next_lap_seconds > 0
GROUP BY year, model
ORDER BY year, model
