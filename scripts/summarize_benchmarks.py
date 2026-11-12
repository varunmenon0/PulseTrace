"""Aggregate saved UBFC benchmark reports without treating windows as independent subjects."""
import argparse
import json
from pathlib import Path
import numpy as np


def summarize(reports):
    summary = {"subjects":len(reports),"recordings":list(reports),"metrics":{}}
    for method in ("pos","green"):
        summary["metrics"][method]={}
        for layout in ("three_regions","twelve_patches"):
            for policy in ("all_windows","motion_excluded"):
                errors=[]; macro=[]; total=0; eligible=0
                for report in reports.values():
                    subject_errors=[]
                    for row in report["windows"]:
                        total+=1
                        if row["reference_bpm"] is None or (policy=="motion_excluded" and row["motion_excluded"]):
                            continue
                        eligible+=1
                        error=row["methods"][method][layout]["error_bpm"]
                        if error is not None:subject_errors.append(error)
                    errors.extend(subject_errors)
                    if subject_errors:macro.append(float(np.mean(np.abs(subject_errors))))
                summary["metrics"][method][layout+"_"+policy]={
                    "total_windows":total,"eligible_windows":eligible,"compared_windows":len(errors),
                    "coverage_of_all_windows":len(errors)/total if total else 0.,
                    "pooled_window_mae_bpm":float(np.mean(np.abs(errors))) if errors else None,
                    "mean_subject_mae_bpm":float(np.mean(macro)) if macro else None,
                    "subjects_with_estimates":len(macro)}
        paired={l:[] for l in ("three_regions","twelve_patches")}
        count=0
        for report in reports.values():
            for row in report["windows"]:
                if all(row["methods"][method][l]["error_bpm"] is not None for l in paired):
                    count+=1
                    for l in paired:paired[l].append(abs(row["methods"][method][l]["error_bpm"]))
        summary["metrics"][method]["paired_all_windows"]={
            "common_windows":count,**{l:float(np.mean(errors)) if errors else None for l,errors in paired.items()}}
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("reports",nargs="+",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    reports={str(path):json.loads(path.read_text()) for path in args.reports}
    result=summarize(reports)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
