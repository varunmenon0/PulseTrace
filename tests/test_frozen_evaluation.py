import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
from report_frozen_evaluation import report_cohort


def test_missing_subjects_are_explicit_not_silently_dropped(tmp_path):
    (tmp_path/"protocol.json").write_text(json.dumps({"subjects":["subject12","subject13"]}))
    r=report_cohort(tmp_path)
    assert r["planned_recordings"]==2
    assert r["completed_recordings"]==0
    assert set(r["failures"])=={"subject12","subject13"}
    assert r["aggregate"]["metrics"]["pos"]["twelve_patches"]["regional_gate"]["mae_bpm"] is None


def test_new_large_errors_and_reference_failures_are_accounted_separately(tmp_path):
    (tmp_path/"protocol.json").write_text(json.dumps({"subjects":["subject12"]}))
    directory=tmp_path/"subject12";directory.mkdir()
    windows=[]
    for ref,error in [(70.,15.),(None,None)]:
        windows.append({"reference_bpm":ref,"methods":{m:{l:{
            "global_gate":{"error_bpm":None},
            "regional_gate":{"error_bpm":error}} for l in ("three_regions","twelve_patches")}
                       for m in ("pos","green")}})
    (directory/"regional_comparison.json").write_text(json.dumps({"windows":windows,"metrics":{}}))
    r=report_cohort(tmp_path)
    metrics=r["aggregate"]["metrics"]["pos"]["twelve_patches"]
    assert r["per_subject"]["subject12"]["total_windows"]==2
    assert metrics["regional_gate"]["reference_valid_windows"]==1
    assert metrics["newly_admitted"]["absolute_errors_over_10_bpm"]==1
    assert metrics["regional_gate"]["mean_subject_mae_bpm"]==15.
