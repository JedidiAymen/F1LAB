import json

from f1_racelab.agents.forecast_debug.evidence_gate import MAX_OBSERVATION_CHARS, assess


def trace(observation, *, final=None):
    steps = [{'tool_id': 't1', 'action': 'incident_checks', 'observation': json.dumps(observation)}]
    if final is not None:
        steps.append({'final': {'evidence': final}})
    return steps


def test_multiple_observations_contradict_clean_claim_without_assigning_cause():
    checks = {'schema_version': 2, 'forecast_coverage': {'batch_only_keys': 2, 'live_only_keys': 0},
              'model_version_disagreements_on_matched': 1, 'model_version_coverage': {'known_pairs': 4},
              'feature_comparison': {'mismatched_values_on_matched': {'tyre_age': 3},
                                     'value_coverage_on_matched': {'tyre_age': {'known_pairs': 4}}}}
    result = assess('no_material_discrepancy', ['t1'], trace(checks, final=['t1']))
    assert result['decision'] == 'abstain' and result['status'] == 'contradicted'
    assert {x['code'] for x in result['signals']} == {'unmatched_forecast_keys', 'known_version_disagreement', 'known_feature_mismatch'}
    assert 'not causal' in result['warning']


def test_unknown_and_nonfinite_values_never_become_positive_mismatch():
    checks = {'schema_version': 2, 'forecast_coverage': {'batch_only_keys': None, 'live_only_keys': float('nan')},
              'model_version_disagreements_on_matched': 3, 'model_version_coverage': {'known_pairs': 0},
              'feature_comparison': {'mismatched_values_on_matched': {'tyre_age': 4},
                                     'value_coverage_on_matched': {'tyre_age': {'known_pairs': 0}}},
              'prediction_comparison_seconds': {'max_abs_batch_value': 90, 'max_abs_live_value': float('inf')}}
    result = assess('no_material_discrepancy', ['t1'], trace(checks))
    assert result['decision'] == 'abstain' and result['status'] == 'insufficient' and result['signals'] == []


def test_missing_duplicated_or_malformed_citations_abstain():
    checks = {'schema_version': 2, 'forecast_coverage': {'batch_only_keys': 1}}
    for evidence, steps in [([], trace(checks)), (['missing'], trace(checks)), (['t1', 't1'], trace(checks)),
                            (['t1'], trace(checks, final=['made_up'])),
                            (['t1'], [{'tool_id': 't1', 'action': 'incident_checks', 'observation': '{'}]),
                            (['t1'], [{'tool_id': 't1', 'action': 'incident_checks', 'observation': 'x' * (MAX_OBSERVATION_CHARS + 1)}]),
                            (['t1'], trace(checks) * 2)]:
        assert assess('no_material_discrepancy', evidence, steps)['status'] == 'insufficient'


def test_signals_require_review_and_do_not_confirm_causal_label():
    checks = {'schema_version': 2, 'prediction_comparison_seconds': {'max_abs_batch_value': 90, 'max_abs_live_value': 1000}}
    result = assess('unit_mismatch', ['t1'], trace(checks))
    assert result['decision'] == 'review_required' and result['status'] == 'observations_only'
    assert result['signals'][0]['code'] == 'large_prediction_scale_ratio'
    assert assess('no_material_discrepancy', ['t1'], trace({'schema_version': 2}))['decision'] == 'abstain'
