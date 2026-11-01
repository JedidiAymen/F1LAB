import json

from f1_racelab.agents.forecast_debug.evidence_gate import MAX_OBSERVATION_CHARS, assess


def trace(observation, *, final=None):
    steps = [{'tool_id': 't1', 'action': 'incident_checks', 'observation': json.dumps(observation)}]
    if final is not None:
        steps.append({'final': {'evidence': final}})
    return steps


def test_multiple_observations_flag_clean_claim_without_assigning_cause():
    checks = {'schema_version': 2, 'forecast_coverage': {'batch_only_keys': 2, 'live_only_keys': 0},
              'model_version_disagreements_on_matched': 1, 'model_version_coverage': {'known_pairs': 4},
              'feature_comparison': {'mismatched_values_on_matched': {'tyre_age': 3},
                                     'value_coverage_on_matched': {'tyre_age': {'known_pairs': 4}}}}
    result = assess('no_material_discrepancy', ['t1'], trace(checks, final=['t1']))
    assert result['decision'] == 'abstain' and result['status'] == 'signal_present'
    assert {x['code'] for x in result['signals']} == {'unmatched_forecast_keys', 'known_version_disagreement', 'known_feature_mismatch'}
    assert 'not causal' in result['warning']


def test_unknown_and_nonfinite_values_never_become_positive_mismatch():
    checks = {'schema_version': 2, 'forecast_coverage': {'batch_only_keys': None, 'live_only_keys': float('nan')},
              'model_version_disagreements_on_matched': 3, 'model_version_coverage': {'known_pairs': 0},
              'feature_comparison': {'mismatched_values_on_matched': {'tyre_age': 4},
                                     'value_coverage_on_matched': {'tyre_age': {'known_pairs': 0}}},
              'config_differences': [{'key': 'model_version', 'batch': 'unknown', 'live': 'v2'}],
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


def test_bundled_gate_study_and_fail_closed_api(monkeypatch):
    from fastapi.testclient import TestClient

    from f1_racelab.agents.forecast_debug import gate_service
    from f1_racelab.api import create_app

    client = TestClient(create_app())
    report = client.get('/api/v1/research/agent-evidence-gate')
    assert report.status_code == 200
    assert report.json()['summary']['true_clean_withheld'] == 2
    assert client.post('/api/v1/research/agent-evidence-gate').status_code == 405
    def missing():
        raise FileNotFoundError('missing')
    monkeypatch.setattr(gate_service, 'load', missing)
    assert client.get('/api/v1/research/agent-evidence-gate').status_code == 503


def test_opt_in_wrapper_preserves_proposed_diagnosis(monkeypatch):
    from types import SimpleNamespace

    from f1_racelab.agents.forecast_debug import agent, evidence_gate

    proposal = SimpleNamespace(root_cause='no_material_discrepancy', evidence=['t1'],
                               trace=trace({'schema_version': 2, 'forecast_coverage': {'batch_only_keys': 2}}))
    monkeypatch.setattr(agent, 'run_agent', lambda model, tools, max_steps: proposal)
    original, gate = evidence_gate.run_gated_agent(object(), object(), max_steps=2)
    assert original is proposal and gate['status'] == 'signal_present' and gate['decision'] == 'abstain'
