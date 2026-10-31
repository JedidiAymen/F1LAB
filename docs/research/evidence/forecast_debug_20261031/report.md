# Forecast-debugging agent evaluation: ollama:qwen3:8b

8 synthetic scenarios with planted root causes (seeds vary magnitude and affected races).

| Metric | Value |
|---|---:|
| Root-cause accuracy | 25.0% |
| Correct with existing citation IDs (support not adjudicated) | 25.0% |
| Answers with existing citation IDs | 100.0% |
| Undetermined or invalid | 0.0% |
| Mean steps | 4.0 |
| Tool errors | 0 |
| Mean latency (s) | 17.43 |
| Tool calls | 24 |
| False citation IDs | 0 |

| Root cause | Accuracy |
|---|---:|
| regime_shift | 0% |
| stale_model_version | 0% |
| feature_skew | 0% |
| missing_live_data | 0% |
| unit_mismatch | 0% |
| config_drift | 100% |
| lap_misalignment | 0% |
| no_material_discrepancy | 100% |

Confusions (expected -> predicted):

- feature_skew -> no_material_discrepancy: 1
- lap_misalignment -> no_material_discrepancy: 1
- missing_live_data -> no_material_discrepancy: 1
- regime_shift -> no_material_discrepancy: 1
- stale_model_version -> no_material_discrepancy: 1
- unit_mismatch -> no_material_discrepancy: 1
