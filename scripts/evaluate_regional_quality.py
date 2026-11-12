"""Evaluate global versus experimental regional gates from saved extraction and reference reports."""
import argparse
import json
from pathlib import Path

import numpy as np

from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.patches import PATCHES
from pulsetrace.regional_quality import write_regional_comparison


def load_cache(path):
    with np.load(path,allow_pickle=False) as a:
        return Extraction(a['time'],{n:a['rgb_'+n] for n in REGIONS},
                          {n:a['pixels_'+n] for n in REGIONS},None,{}, {},
                          {n:a['geometry_'+n] for n in REGIONS},
                          {n:a['patch_rgb_'+n] for n in PATCHES},
                          {n:a['patch_pixels_'+n] for n in PATCHES})


def score(report, reference):
    references={(w["start_s"],w["end_s"]):w for w in reference["windows"]}
    if len(references)!=len(report["windows"]):
        raise ValueError("Reference and extraction windows differ")
    for row in report["windows"]:
        match=references.get((row["start_s"],row["end_s"]))
        if match is None:raise ValueError("Reference and extraction windows differ")
        row["reference_bpm"]=match["reference_bpm"]
        row["reference_warning"]=match.get("reference_warning")
        for layouts in row["methods"].values():
            for policies in layouts.values():
                for result in policies.values():
                    bpm=result["bpm_candidate"]
                    result["error_bpm"]=None if bpm is None or row["reference_bpm"] is None else bpm-row["reference_bpm"]
    report["metrics"]={}
    for method in ("pos","green"):
        report["metrics"][method]={}
        for layout in ("three_regions","twelve_patches"):
            detail={}
            for policy in ("global_gate","regional_gate"):
                rows=[w for w in report["windows"] if w["reference_bpm"] is not None]
                errors=[w["methods"][method][layout][policy]["error_bpm"] for w in rows
                        if w["methods"][method][layout][policy]["error_bpm"] is not None]
                detail[policy]={"reference_valid_windows":len(rows),"compared_windows":len(errors),
                                "mae_bpm":float(np.mean(np.abs(errors))) if errors else None}
            new=[w["methods"][method][layout]["regional_gate"]["error_bpm"] for w in report["windows"]
                 if w["methods"][method][layout]["global_gate"]["error_bpm"] is None and
                 w["methods"][method][layout]["regional_gate"]["error_bpm"] is not None]
            detail["newly_admitted"]={"windows":len(new),"mae_bpm":float(np.mean(np.abs(new))) if new else None,
                                      "errors_bpm":new}
            report["metrics"][method][layout]=detail
    report["reference_policy"]=reference.get("reference_quality_policy")
    report["input"]=reference["input"]
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache",type=Path,required=True)
    p.add_argument("--benchmark",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--area-policy",choices=["strict","corroborated"],default="strict")
    args=p.parse_args()
    reference=json.loads(args.benchmark.read_text())
    extraction=load_cache(args.cache)
    if len(extraction.time)!=reference["input"]["decoded_frames"] or not np.isclose(extraction.time[-1],reference["input"]["duration_s"]):
        raise ValueError("Cache dimensions/timing do not match reference benchmark")
    report=score(write_regional_comparison(extraction,args.output,area_policy=args.area_policy),reference)
    (args.output/"regional_comparison.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report["metrics"],indent=2))


if __name__=="__main__":main()
