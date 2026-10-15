import httpx
import pandas as pd

from f1_racelab.data.openf1_qualifying import (
    OpenF1Client,
    conventional_weekends,
    normalize_weekend,
)


def test_client_reuses_exact_cached_response(tmp_path, monkeypatch):
    calls = []

    def reply(url, params):
        calls.append((url, params))
        return httpx.Response(200, json=[{"meeting_key": 7}], request=httpx.Request("GET", url))

    with OpenF1Client(tmp_path, interval=0) as client:
        monkeypatch.setattr(client._http, "get", reply)
        assert client.get("meetings", year=2025) == [{"meeting_key": 7}]
        assert client.get("meetings", year=2025) == [{"meeting_key": 7}]
        assert len(client.hashes["meetings?year=2025"]) == 64
    assert len(calls) == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_conventional_schedule_preserves_round_after_sprint():
    meetings = [
        {"meeting_key": 1, "year": 2025, "date_start": "2025-01-01", "meeting_name": "A"},
        {"meeting_key": 2, "year": 2025, "date_start": "2025-01-08", "meeting_name": "B"},
        {"meeting_key": 3, "year": 2025, "date_start": "2025-01-15", "meeting_name": "C"},
    ]
    sessions = [
        {"meeting_key": key, "session_name": name, "session_key": key * 10 + index}
        for key in (1, 2, 3)
        for index, name in enumerate((*("Practice 1", "Practice 2", "Practice 3", "Qualifying"), "Race"))
    ]
    sessions.append({"meeting_key": 2, "session_name": "Sprint", "session_key": 99})
    weekends = conventional_weekends(meetings, sessions)
    assert [(w["round"], w["event"]) for w in weekends] == [(1, "A"), (3, "C")]


def test_normalization_uses_q1_phase_and_event_scoped_practice_reference():
    item = {"year": 2025, "round": 1, "event": "Example GP", "meeting_key": 7,
            "sessions": {"Qualifying": {"date_start": "2025-03-01T12:00:00+00:00", "session_key": 99}}}
    drivers = [{"driver_number": i, "name_acronym": f"D{i:02}", "team_name": f"T{i // 2}"}
               for i in range(1, 11)]
    results = {
        "Qualifying": [{"driver_number": i, "position": i,
                        "duration": [90.0 + i, 89.0 + i, 88.0 + i]}
                       for i in range(1, 11)],
    }
    for number, name in enumerate(("Practice 1", "Practice 2", "Practice 3"), start=1):
        results[name] = [{"driver_number": i, "position": i,
                          "duration": 92.0 + i + number} for i in range(1, 11)]
    frame = normalize_weekend(item, drivers, results)
    assert len(frame) == 10
    assert frame.loc[0, "q1_gap_pct"] == 0
    assert frame.loc[0, "fp3_gap_pct"] == 0
    assert frame.loc[0, "q1_seconds"] == 91
    assert frame.loc[0, "q3_seconds"] == 89
    assert frame.loc[0, "source_session_key"] == 99
    assert frame.loc[0, "available_at"] == "2025-03-01T12:00:00+00:00"
    assert pd.notna(frame.loc[9, "fp3_gap_pct"])
