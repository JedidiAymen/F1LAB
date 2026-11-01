"""Bounded observational gate; it never validates or assigns a causal root cause."""
from __future__ import annotations

import json
import math
from typing import Any

MAX_TRACE = 24
MAX_OBSERVATION_CHARS = 32_000
WARNING = ('Observations are not causal diagnoses. No clean bill or root cause is approved; '
           'unknown or uncited evidence requires further investigation.')


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _positive(value: Any) -> bool:
    n = _number(value)
    return n is not None and n > 0


def _known_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().casefold() not in {'unknown', 'none', 'null', 'nan', 'n/a'}


def _known_mismatch(count: Any, info: Any) -> bool:
    n = _number(count)
    known = _number(info.get('known_pairs')) if isinstance(info, dict) else None
    return n is not None and known is not None and n > 0 and known >= n


def _signals(check: dict) -> list[dict[str, str]]:
    """Emit observations only when the source fields support each indication."""
    signals = []
    coverage = check.get('forecast_coverage')
    if isinstance(coverage, dict) and (_positive(coverage.get('batch_only_keys')) or _positive(coverage.get('live_only_keys'))):
        signals.append({'code': 'unmatched_forecast_keys', 'description': 'Forecast keys differ between pipelines.'})
    versions = check.get('model_version_coverage')
    if _known_mismatch(check.get('model_version_disagreements_on_matched'), versions):
        signals.append({'code': 'known_version_disagreement', 'description': 'Known model versions differ on matched keys.'})
    configs = check.get('config_differences')
    if isinstance(configs, list) and any(isinstance(row, dict) and all(_known_text(row.get(key)) for key in ('key', 'batch', 'live'))
                                         and row['batch'] != row['live'] for row in configs):
        signals.append({'code': 'known_config_difference', 'description': 'Known configuration values differ.'})
    features = check.get('feature_comparison')
    if isinstance(features, dict):
        mismatches, quality = features.get('mismatched_values_on_matched'), features.get('value_coverage_on_matched')
        if isinstance(mismatches, dict) and isinstance(quality, dict) and any(_known_mismatch(count, quality.get(name)) for name, count in mismatches.items()):
            signals.append({'code': 'known_feature_mismatch', 'description': 'Known feature values differ on matched keys.'})
    alignment = check.get('possible_previous_lap_alignment_races')
    if isinstance(alignment, list) and any(isinstance(item, str) and item.strip() for item in alignment):
        signals.append({'code': 'possible_alignment_shift', 'description': 'Previous-lap alignment is a heuristic clue.'})
    compare = check.get('prediction_comparison_seconds')
    if isinstance(compare, dict):
        batch, live = _number(compare.get('max_abs_batch_value')), _number(compare.get('max_abs_live_value'))
        if batch is not None and live is not None and batch >= 1 and live >= batch * 10:
            signals.append({'code': 'large_prediction_scale_ratio', 'description': 'Maximum live magnitude is at least ten times batch; cause is unknown.'})
    return signals


def assess(proposed: str, citations: list[str], trace: list[dict[str, Any]]) -> dict[str, Any]:
    """Withhold clean claims; inspect cited observations without executing tools."""
    result: dict[str, Any] = {'proposed': proposed, 'decision': 'abstain', 'status': 'insufficient',
                              'signals': [], 'warning': WARNING}
    if len(trace) > MAX_TRACE or not citations or any(not isinstance(item, str) for item in citations):
        return result
    if len(set(citations)) != len(citations):
        return result
    tool_steps = [step for step in trace if isinstance(step, dict) and 'tool_id' in step]
    ids = [step['tool_id'] for step in tool_steps]
    if any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        return result
    by_id = {step['tool_id']: step for step in tool_steps}
    if any(item not in by_id for item in citations):
        return result
    # The original agent filters invalid citations; retain the raw final claim too.
    finals = [step.get('final') for step in trace if isinstance(step, dict) and isinstance(step.get('final'), dict)]
    if finals:
        final = finals[-1]
        if not isinstance(final, dict):
            return result
        claimed = final.get('evidence')
        if (not isinstance(claimed, list) or any(not isinstance(item, str) for item in claimed)
                or set(claimed) != set(citations) or any(item not in by_id for item in claimed)):
            return result
    observed = []
    for citation in citations:
        step = by_id[citation]
        if step.get('action') != 'incident_checks':
            continue
        raw = step.get('observation')
        if not isinstance(raw, str) or len(raw) > MAX_OBSERVATION_CHARS:
            return result
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return result
        if not isinstance(data, dict) or data.get('schema_version') != 2:
            return result
        observed.extend([{**item, 'citation': citation} for item in _signals(data)])
    if not observed:
        return result
    result['signals'] = observed
    if proposed == 'no_material_discrepancy':
        result['status'] = 'contradicted'
    else:
        result['decision'] = 'review_required'
        result['status'] = 'observations_only'
    return result


def run_gated_agent(model: Any, tools: Any, *, max_steps: int = 12) -> tuple[Any, dict[str, Any]]:
    """Opt-in wrapper retains the original diagnosis and appends a separate gate result."""
    from f1_racelab.agents.forecast_debug.agent import run_agent

    diagnosis = run_agent(model, tools, max_steps=max_steps)
    return diagnosis, assess(diagnosis.root_cause, diagnosis.evidence, diagnosis.trace)
