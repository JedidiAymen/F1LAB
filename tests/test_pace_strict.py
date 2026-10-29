import pandas as pd

from f1_racelab.ml.pace import strict


def _frame():
    # One driver. Row `lap` = decision lap L; *_next columns describe lap L+1.
    # Lap 3 is the in-lap, lap 4 the out-lap on a new HARD stint (age 1).
    base = {"race_id": "r", "driver_number": 1, "neutral_in_last3": 0, "yellow_in_last1": 0, "regime_next": "green",
            "next_is_in_lap": False, "next_is_out_lap": False, "eligible_green_next": True, "year": 2025}
    laps = [
        {"lap": 1, "compound_next": "MEDIUM", "stint_number_next": 1, "tyre_age_next": 2},
        {"lap": 2, "compound_next": "MEDIUM", "stint_number_next": 1, "tyre_age_next": 3, "next_is_in_lap": True},
        {"lap": 3, "compound_next": "HARD", "stint_number_next": 2, "tyre_age_next": 1, "next_is_out_lap": True,
             "eligible_green_next": False},
        {"lap": 4, "compound_next": "HARD", "stint_number_next": 2, "tyre_age_next": 2},
        {"lap": 5, "compound_next": "HARD", "stint_number_next": 2, "tyre_age_next": 3},
    ]
    return pd.DataFrame([{**base, **row} for row in laps])


def test_tyre_inputs_come_from_lap_l_not_lap_l_plus_one():
    out = strict.decision_frame(_frame()).set_index("lap")
    # Row lap=3 forecasts the out-lap: the new HARD tyre of lap 4 must NOT be visible.
    # Lap 3 itself ran on MEDIUM, stint 1, age 3, so the as-if-stay-out input is age 3 + 1.
    assert out.loc[3, "compound_next"] == "MEDIUM" and out.loc[3, "stint_number_next"] == 1
    assert out.loc[3, "tyre_age_next"] == 4
    # Row lap=4 runs lap 4 on HARD age 1, so the as-if-stay-out age is 2.
    assert out.loc[4, "compound_next"] == "HARD" and out.loc[4, "tyre_age_next"] == 2


def test_population_not_selected_on_next_lap_outcome_and_pit_flag_is_causal():
    out = strict.decision_frame(_frame()).set_index("lap")
    assert 2 in out.index and 3 in out.index          # in-lap and out-lap targets are kept
    assert out.loc[3, "outcome"] == "out_lap" and out.loc[2, "outcome"] == "in_lap"
    assert bool(out.loc[3, "just_pitted"]) and not bool(out.loc[2, "just_pitted"])
    assert 1 not in out.index                          # first row has no lap L-1 stint info


def test_neutralised_decision_state_is_excluded():
    frame = _frame()
    frame.loc[frame.lap == 5, "neutral_in_last3"] = 1
    assert 5 not in strict.decision_frame(frame).lap.tolist()
