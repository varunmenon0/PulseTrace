"""Experimental four-way subdivision of each of the three parent masks."""
import csv
import json

import cv2
import numpy as np

from .regions import REGIONS
from .signal import analyze

PATCHES = {f"{zone}_{quadrant}": zone for zone in REGIONS
           for quadrant in ("tl", "tr", "bl", "br")}


def sample_patches(bgr, masks, min_pixels):
    """Partition the actual sampled pixels with no overlap."""
    result = {}
    for zone, mask in masks.items():
        points = cv2.findNonZero(mask).reshape(-1, 2)
        x, y, w, h = cv2.boundingRect(mask)
        px, py = points.T
        left, top = px < x + w / 2, py < y + h / 2
        for quadrant, select in zip(("tl", "tr", "bl", "br"),
                                    (left & top, ~left & top, left & ~top, ~left & ~top)):
            n = int(select.sum())
            if n >= min_pixels:
                result[f"{zone}_{quadrant}"] = (bgr[py[select], px[select]].mean(axis=0)[::-1], n)
    return result


def consensus(candidates, zones, tolerance=5.):
    """Require a strict majority of accepted candidates across two parent zones."""
    valid = sorted((v, k) for k, v in candidates.items() if v is not None)
    groups = [[k for v, k in valid[i:] if v <= low+tolerance]
              for i, (low, _) in enumerate(valid)]
    groups = [g for g in groups if len(g) >= 2 and len(g) > len(valid)/2
              and len({zones[k] for k in g}) >= 2]
    groups.sort(key=len, reverse=True)
    if not groups or (len(groups)>1 and len(groups[0])==len(groups[1])):
        return {"bpm_candidate": None, "support": []}
    group = groups[0]
    medians = [np.median([candidates[k] for k in group if zones[k]==z])
               for z in sorted({zones[k] for k in group})]
    return {"bpm_candidate": float(np.median(medians)), "support": group}


def write_patch_comparison(extraction, segments, output):
    t = extraction.time
    config = segments["configuration"]
    patch_rgb = extraction.patch_rgb
    with (output/"patch_rgb.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s"] + [f"{n}_{c}" for n in PATCHES for c in ("r","g","b","pixels")])
        for i, ts in enumerate(t):
            writer.writerow([ts] + [v for n in PATCHES for v in
                             (*patch_rgb[n][i], extraction.patch_pixels[n][i])])
    report = {"status": segments["status"], "consensus_tolerance_bpm": 5,
              "note": "Experimental spectral candidates; agreement is not a pulse reference.",
              "segments": []}
    for segment in segments["segments"]:
        if segment["status"] != "eligible":
            continue
        select = (t >= segment["start_s"]) & (t <= segment["end_s"])
        row = {k: segment[k] for k in ("start_s","end_s","duration_s")}
        for method in ("green","pos"):
            base = {n: segment["regions"][n][method]["bpm_candidate"] for n in REGIONS}
            patches = {}
            for name, rgb in patch_rgb.items():
                samples = rgb[select]
                valid = np.isfinite(samples).all(axis=1) & (samples > 0).all(axis=1)
                detail = {"bpm_candidate": None, "valid_frame_fraction": float(valid.mean())}
                if not valid.all():
                    detail["warnings"] = ["Patch missing or too small within this interval"]
                else:
                    try:
                        pulse = analyze(t[select], samples, method=method,
                                        min_seconds=config["min_seconds"], max_gap=config["max_gap"])
                        detail.update(bpm_candidate=pulse.bpm, peak_fraction=pulse.peak_fraction,
                                      warnings=pulse.warnings)
                    except ValueError as exc:
                        detail["warnings"] = [str(exc)]
                patches[name] = detail
            row[method] = {
                "baseline_regions": base,
                "baseline_consensus": consensus(base, {n:n for n in REGIONS}),
                "patches": patches,
                "patch_consensus": consensus({n:d["bpm_candidate"] for n,d in patches.items()}, PATCHES),
            }
        report["segments"].append(row)
    (output/"patch_comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return report
