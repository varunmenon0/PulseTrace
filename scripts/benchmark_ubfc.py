"""Compare 3-region and 12-patch pulse estimates against UBFC-rPPG Dataset 2.

Usage: python scripts/benchmark_ubfc.py --video vid.avi --reference ground_truth.txt
       --model models/face_landmarker.task --output outputs/ubfc
Source acquisition is deliberately separate; downloaded recordings are not committed.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from pulsetrace.pipeline import extract_video
from pulsetrace.tracking import FaceTracker
from pulsetrace.quality import analyze_segments
from pulsetrace.patches import PATCHES, consensus
from pulsetrace.regions import REGIONS
from pulsetrace.signal import analyze


def load_reference(path):
    a = np.loadtxt(path)
    if a.ndim != 2 or a.shape[0] != 3 or not np.isfinite(a).all():
        raise ValueError("Expected UBFC2 rows: waveform, device BPM, elapsed seconds")
    time, bpm = a[2], a[1]
    if np.any(np.diff(time) < 0) or np.any(bpm <= 0):
        raise ValueError("Invalid reference timing or BPM")
    # Reference may repeat timestamps. Average simultaneous device observations.
    unique, inverse = np.unique(time, return_inverse=True)
    means = np.bincount(inverse, weights=bpm)/np.bincount(inverse)
    return unique, means


def compare(extraction, rt, rb):
    quality = analyze_segments(extraction)
    rows = []
    t = extraction.time
    for start in np.arange(t[0], t[-1]-12+float(np.median(np.diff(t)))*1.1+1e-9, 6):
        end = start+12
        chosen = (t >= start) & (t < end)
        row = {"start_s":float(start), "end_s":float(end), "methods":{}}
        covered = start >= rt[0] and end <= rt[-1]
        raw_reference = float(np.median(np.interp(np.linspace(start,end,361), rt, rb))) if covered else None
        warning = None if covered else "Reference does not cover complete window"
        left=max(0,np.searchsorted(rt,start,side="right")-1)
        right=min(len(rt),np.searchsorted(rt,end,side="left")+1)
        if covered and (np.any(rb[left:right]<40) or np.any(rb[left:right]>200)):
            warning = "Reference outside supported 40-200 BPM band; no bridging invalid labels"
        if covered and np.any(np.diff(rt[left:right])>2.5):
            warning = "Reference gap exceeds 2.5 seconds"
        reference = raw_reference if warning is None else None
        motion = any(start < i["end_s"] and end > i["start_s"] for i in quality["excluded_intervals"])
        causes = [name for name,detail in quality["exclusion_causes"].items()
                  if any(start < i["end_s"] and end > i["start_s"] for i in detail["excluded_intervals"])]
        row.update(reference_bpm=reference, raw_reference_median_bpm=raw_reference, reference_warning=warning, motion_excluded=motion, exclusion_causes=causes)
        for method in ("pos", "green"):
            record = {}
            for label, traces, zones in (("three_regions",extraction.rgb,{n:n for n in REGIONS}),
                                         ("twelve_patches",extraction.patch_rgb,PATCHES)):
                estimates = {}
                for name, rgb in traces.items():
                    samples = rgb[chosen]
                    bpm = None
                    if len(samples) and np.isfinite(samples).all() and np.all(samples>0):
                        try:
                            bpm = analyze(t[chosen], samples, method=method, min_seconds=11.9).bpm
                        except ValueError:
                            pass
                    estimates[name] = bpm
                result = consensus(estimates,zones)
                value = result["bpm_candidate"]
                record[label] = {"individual_candidates":estimates, **result,
                    "error_bpm":value-reference if value is not None and reference is not None else None,
                    "retained_after_motion_exclusion":not motion and covered and value is not None}
            row["methods"][method] = record
        rows.append(row)
    metrics = {}
    for method in ("pos","green"):
        metrics[method] = {}
        for layout in ("three_regions","twelve_patches"):
            for policy in ("all_windows","motion_excluded"):
                eligible = [r for r in rows if r["reference_bpm"] is not None and (policy=="all_windows" or not r["motion_excluded"])]
                errors = [r["methods"][method][layout]["error_bpm"] for r in eligible
                          if r["methods"][method][layout]["error_bpm"] is not None]
                metrics[method][layout+"_"+policy] = {
                    "total_windows":len(rows),"eligible_windows":len(eligible),"compared_windows":len(errors),
                    "coverage_of_all_windows":len(errors)/len(rows) if rows else 0.,
                    "mae_bpm":float(np.mean(np.abs(errors))) if errors else None}
    paired = {}
    for method in ("pos","green"):
        common = [r for r in rows if all(r["methods"][method][layout]["error_bpm"] is not None
                                        for layout in ("three_regions","twelve_patches"))]
        paired[method] = {"common_windows":len(common),
                          **{layout:float(np.mean([abs(r["methods"][method][layout]["error_bpm"]) for r in common]))
                             if common else None for layout in ("three_regions","twelve_patches")}}
    return {"alignment":"Assumed shared elapsed-time origin (offset=0); hardware sync not independently verified",
            "reference":"Device-reported BPM, not a waveform correlation benchmark",
            "reference_quality_policy":"Reject entire windows touching device BPM outside 40-200 or gaps over 2.5 s; no bridging",
            "limitations":["Per-recording results; overlapping windows are not independent", "Mirror identity not independently checksum-matched to official source",
                           "Same filters and thresholds for both layouts; no tuning to reference"],
            "metrics":metrics,"paired_mae_bpm":paired,"windows":rows,"motion_quality":quality}


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(4*1024*1024):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("video","reference","model","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    args = parser.parse_args()
    rt,rb = load_reference(args.reference)
    with FaceTracker(args.model) as tracker:
        extraction = extract_video(args.video,tracker,patches=True)
    args.output.mkdir(parents=True,exist_ok=True)
    # Preserve extraction locally so later diagnostics need not rerun native inference.
    np.savez_compressed(args.output/"extraction.npz", time=extraction.time,
                        **{f"rgb_{k}":v for k,v in extraction.rgb.items()},
                        **{f"pixels_{k}":v for k,v in extraction.pixels.items()},
                        **{f"geometry_{k}":v for k,v in extraction.geometry.items()},
                        **{f"patch_rgb_{k}":v for k,v in extraction.patch_rgb.items()},
                        **{f"patch_pixels_{k}":v for k,v in extraction.patch_pixels.items()})
    report = compare(extraction,rt,rb)
    report["input"] = {"video_sha256":sha256_file(args.video),
                       "reference_sha256":sha256_file(args.reference),
                       "decoded_frames":len(extraction.time),"duration_s":float(extraction.time[-1]),
                       "reference_duration_s":float(rt[-1])}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"benchmark.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report["metrics"],indent=2))


if __name__ == "__main__":
    main()
