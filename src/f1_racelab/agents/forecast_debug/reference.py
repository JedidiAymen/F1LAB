"""Deterministic reference diagnoser that uses only the agent's read-only tools.

It is a solvability check for the benchmark, not a competitor: it was written knowing the label taxonomy, so a
perfect score shows that every planted root cause is identifiable from tool evidence alone. It is not evidence
that rules generalise to real incidents.
"""
from __future__ import annotations

from typing import Any

from f1_racelab.agents.forecast_debug.agent import Diagnosis
from f1_racelab.agents.forecast_debug.tools import ForecastTools


class _Recorder:
    def __init__(self, tools: ForecastTools) -> None:
        self.tools = tools
        self.trace: list[dict[str, Any]] = []

    def sql(self, query: str) -> tuple[str, list[dict[str, Any]]]:
        tool_id = f"t{len(self.trace) + 1}"
        result = self.tools.call("run_sql", {"query": query})
        if "error" in result:
            raise RuntimeError(result["error"])
        self.trace.append({"tool_id": tool_id, "action": "run_sql", "args": {"query": query}})
        return tool_id, result["rows"]

    def config(self) -> tuple[str, list[dict[str, Any]]]:
        tool_id = f"t{len(self.trace) + 1}"
        self.trace.append({"tool_id": tool_id, "action": "config_diff", "args": {}})
        return tool_id, self.tools.call("config_diff")["differences"]


def diagnose(tools: ForecastTools) -> Diagnosis:
    r = _Recorder(tools)

    def done(label: str, evidence: list[str], why: str) -> Diagnosis:
        return Diagnosis(root_cause=label, evidence=evidence, explanation=why, confidence=1.0,
                         steps=len(r.trace), trace=r.trace)

    cfg_id, diffs = r.config()
    if any(d["key"] == "green_laps_only" for d in diffs):
        return done("config_drift", [cfg_id], "green_laps_only differs between batch and live")

    cov_id, cov = r.sql("""SELECT COUNT(DISTINCT b.race_id) AS batch_races,
                                  COUNT(DISTINCT l.race_id) AS live_races
                           FROM (SELECT DISTINCT race_id FROM batch_forecasts) b
                           FULL OUTER JOIN (SELECT DISTINCT race_id FROM live_forecasts) l USING (race_id)""")
    if cov[0]["live_races"] < cov[0]["batch_races"]:
        return done("missing_live_data", [cov_id], "live forecasts cover fewer races than batch")

    unit_id, unit = r.sql("SELECT MAX(pred_seconds) AS max_live, MIN(pred_seconds) AS min_live FROM live_forecasts")
    if unit[0]["max_live"] > 1000:
        return done("unit_mismatch", [unit_id], "some live forecasts are ~1000x larger than a lap time")

    ver_id, versions = r.sql("""SELECT 'batch' AS pipeline, model_version, COUNT(*) AS n FROM batch_forecasts
                                GROUP BY 2 UNION ALL
                                SELECT 'live', model_version, COUNT(*) FROM live_forecasts GROUP BY 2""")
    if len({v["model_version"] for v in versions}) > 1:
        return done("stale_model_version", [ver_id], "live and batch use different model versions")

    feat_id, feat = r.sql("""SELECT AVG(ABS(l.tyre_age - b.tyre_age)) AS tyre_age_gap,
                                    SUM(CASE WHEN l.compound <> b.compound THEN 1 ELSE 0 END) AS compound_gaps
                             FROM features_batch b JOIN features_live l USING (race_id, driver, lap)""")
    if (feat[0]["tyre_age_gap"] or 0) > 0 or (feat[0]["compound_gaps"] or 0) > 0:
        return done("feature_skew", [feat_id], "live features differ from batch features for the same laps")

    lag_id, lag = r.sql("""SELECT b.race_id,
                                  AVG(CASE WHEN ABS(l.pred_seconds - b.pred_seconds) < 0.02 THEN 1.0 ELSE 0 END)
                                      AS same_lap_match,
                                  AVG(CASE WHEN ABS(l.pred_seconds - p.pred_seconds) < 0.02 THEN 1.0 ELSE 0 END)
                                      AS previous_lap_match
                           FROM live_forecasts l
                           JOIN batch_forecasts b USING (race_id, driver, lap)
                           JOIN batch_forecasts p ON p.race_id = l.race_id AND p.driver = l.driver
                                                 AND p.lap = l.lap - 1
                           GROUP BY 1 ORDER BY previous_lap_match DESC""")
    if lag and lag[0]["previous_lap_match"] > 0.8 > lag[0]["same_lap_match"]:
        return done("lap_misalignment", [lag_id], "live values match the batch forecast of the previous lap")

    bias_id, bias = r.sql("""SELECT a.year, AVG(b.pred_seconds - a.actual_seconds) AS bias, COUNT(*) AS n
                             FROM batch_forecasts b JOIN laps a USING (race_id, driver, lap)
                             WHERE a.eligible_green GROUP BY 1 ORDER BY 1""")
    if max(abs(row["bias"]) for row in bias) > 0.15:
        return done("regime_shift", [bias_id], "batch and live agree but one period is biased against actuals")

    return done("no_material_discrepancy", [cfg_id, cov_id, ver_id, feat_id, lag_id, bias_id],
                "all checks within tolerance")
