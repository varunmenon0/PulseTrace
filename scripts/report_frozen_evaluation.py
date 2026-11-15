"""Summarize a fixed cohort without silently dropping failed subjects."""
import argparse
import json
from pathlib import Path
import numpy as np

from summarize_regional_quality import summarize


def report_cohort(root):
    protocol=json.loads((root/"protocol.json").read_text())
    reports=[];subjects={};failures={}
    for subject in protocol["subjects"]:
        path=root/subject/"regional_comparison.json"
        if not path.exists():
            failure=root/subject/"failure.json"
            failures[subject]=json.loads(failure.read_text()) if failure.exists() else {"error":"Evaluation not completed"}
            continue
        report=json.loads(path.read_text());reports.append(report)
        subjects[subject]={"total_windows":len(report["windows"]),
                           "reference_valid_windows":sum(w["reference_bpm"] is not None for w in report["windows"]),
                           "metrics":report["metrics"]}
    combined=summarize(reports)
    for method in ("pos","green"):
        for layout in ("three_regions","twelve_patches"):
            detail=combined["metrics"][method][layout]
            for gate in ("global_gate","regional_gate"):
                subject_mae=[]
                for report in reports:
                    errors=[w["methods"][method][layout][gate]["error_bpm"] for w in report["windows"]
                            if w["methods"][method][layout][gate]["error_bpm"] is not None]
                    if errors:subject_mae.append(float(np.mean(np.abs(errors))))
                detail[gate]["mean_subject_mae_bpm"]=float(np.mean(subject_mae)) if subject_mae else None
                detail[gate]["subjects_with_estimates"]=len(subject_mae)
            errors=[w["methods"][method][layout]["regional_gate"]["error_bpm"]
                    for report in reports for w in report["windows"]
                    if w["methods"][method][layout]["global_gate"]["error_bpm"] is None
                    and w["methods"][method][layout]["regional_gate"]["error_bpm"] is not None]
            detail["newly_admitted"]["absolute_errors_over_10_bpm"]=sum(abs(e)>10 for e in errors)
    return {"protocol":protocol,"planned_recordings":len(protocol["subjects"]),
            "completed_recordings":len(reports),"failures":failures,
            "per_subject":subjects,"aggregate":combined}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("root",type=Path);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    report=report_cohort(args.root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report["aggregate"],indent=2))


if __name__=="__main__":main()
