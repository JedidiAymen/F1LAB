import json

import pandas as pd
import pytest
from test_data_quality import weekend

from f1_racelab.data import pipeline


def _stub(monkeypatch, frame):
    frame = frame.assign(provider="OpenF1")
    report = pd.DataFrame([{"year": 2025, "round": 1, "event": "Test GP", "status": "BUILT",
                            "rows": len(frame), "detail": ""}])
    monkeypatch.setattr(pipeline.openf1_qualifying, "build_dataset",
                        lambda years, **kw: (frame, report))


def _write(root, frame, years="2025"):
    frame.assign(provider="OpenF1").to_parquet(root / f"qualifying_openf1_{years}.parquet", index=False)


def test_pipeline_writes_manifest_with_hash_and_passes(tmp_path, monkeypatch):
    frame = weekend()
    _stub(monkeypatch, frame)
    _write(tmp_path, frame)
    manifest = pipeline.run([2025], output_root=tmp_path, merge=False)
    assert manifest["passed"] and manifest["quality"]["errors"] == 0
    on_disk = json.loads((tmp_path / "pipeline_manifest_2025.json").read_text())
    assert len(on_disk["dataset_sha256"]) == 64
    assert [s["step"] for s in on_disk["steps"]] == ["openf1_sync", "quality_gate"]
    assert (tmp_path / "data_quality" / "2025" / "findings.csv").exists()


def test_quality_gate_fails_the_run_on_error_findings(tmp_path, monkeypatch):
    frame = weekend()
    frame.loc[5, "final_position"] = 3  # classification no longer a permutation
    _stub(monkeypatch, frame)
    _write(tmp_path, frame)
    with pytest.raises(SystemExit, match="Quality gate failed"):
        pipeline.run([2025], output_root=tmp_path, merge=False)
    # The manifest is still written so the failure is inspectable.
    assert json.loads((tmp_path / "pipeline_manifest_2025.json").read_text())["passed"] is False
