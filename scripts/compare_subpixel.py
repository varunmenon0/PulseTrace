"""Offline paired sampling experiment with identical tracking and fixed baseline gates."""
import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from benchmark_ubfc import compare, load_reference
from pulsetrace.patches import PATCHES
from pulsetrace.pipeline import extract_video
from pulsetrace.regional_quality import regional_masks, gate_candidates
from pulsetrace.regions import REGIONS
from pulsetrace.subpixel import fractional_masks
from pulsetrace.tracking import FaceTracker


class PairedTracker:
    """Sample fractional masks before returning the same landmarks to the baseline."""

    def __init__(self, tracker, subdivisions):
        self.tracker, self.subdivisions = tracker, subdivisions
        self.rgb = {n: [] for n in REGIONS}
        self.areas = {n: [] for n in REGIONS}
        self.patch_rgb = {n: [] for n in PATCHES}

    def detect(self, bgr, time):
        landmarks = self.tracker.detect(bgr, time)
        for zone, indices in REGIONS.items():
            color, area = np.full(3, np.nan), 0.
            patches = {}
            if landmarks is not None:
                try:
                    parent, patches = fractional_masks(
                        bgr.shape, landmarks[list(indices)], subdivisions=self.subdivisions)
                    area = parent.area
                    color = parent.mean_rgb(bgr)
                except ValueError:
                    pass
            self.rgb[zone].append(color)
            self.areas[zone].append(area)
            for quadrant in ("tl", "tr", "bl", "br"):
                value = np.full(3, np.nan)
                if quadrant in patches:
                    try:
                        value = patches[quadrant].mean_rgb(bgr)
                    except ValueError:
                        pass
                self.patch_rgb[f"{zone}_{quadrant}"].append(value)
        return landmarks


def score_pair(baseline, weighted, rt, rb):
    """Use original pixels/geometry and baseline exclusions for both RGB streams."""
    if not np.array_equal(baseline.time, weighted.time):
        raise ValueError('Paired samplers must use identical timestamps')
    masks, _ = regional_masks(baseline)
    results = {}
    for name, extraction in (("integer", baseline), ("fractional", weighted)):
        # Reference scoring and ungated estimates use the existing benchmark.
        # Its motion_excluded field is overwritten below from baseline windows.
        results[name] = compare(extraction, rt, rb)
    for a, b in zip(results['integer']['windows'], results['fractional']['windows']):
        if (a['start_s'], a['end_s']) != (b['start_s'], b['end_s']):
            raise ValueError('Paired windows differ')
        chosen = (baseline.time >= a['start_s']) & (baseline.time < a['end_s'])
        usable = {n: not bool(mask[chosen].any()) for n, mask in masks.items()}
        for row in (a, b):
            row['motion_excluded'] = a['motion_excluded']
            row['exclusion_causes'] = a['exclusion_causes']
            for method, layouts in row['methods'].items():
                for layout, detail in layouts.items():
                    zones = PATCHES if layout == 'twelve_patches' else {n: n for n in REGIONS}
                    for gate, allowed in (('global_gate', {n: not a['motion_excluded'] for n in REGIONS}),
                                          ('regional_gate', usable)):
                        decision = gate_candidates(detail['individual_candidates'], zones, allowed)
                        bpm = decision['bpm_candidate']
                        decision['error_bpm'] = None if bpm is None or row['reference_bpm'] is None else bpm - row['reference_bpm']
                        detail[gate] = decision
                    # Avoid retaining benchmark fields calculated with weighted validity.
                    detail.pop('retained_after_motion_exclusion', None)
    return {n: r['windows'] for n, r in results.items()}


def summarize(rows):
    summary = {}
    for method in ('pos', 'green'):
        summary[method] = {}
        for layout in ('three_regions', 'twelve_patches'):
            summary[method][layout] = {}
            for gate in ('ungated', 'global_gate', 'regional_gate'):
                errors = []
                for row in rows:
                    detail = row['methods'][method][layout]
                    error = (detail if gate == 'ungated' else detail[gate])['error_bpm']
                    if error is not None:
                        errors.append(abs(error))
                summary[method][layout][gate] = dict(
                    total_windows=len(rows),
                    reference_valid_windows=sum(r['reference_bpm'] is not None for r in rows),
                    accepted_windows=len(errors),
                    mae_against_device_bpm=float(np.mean(errors)) if errors else None,
                    max_difference_bpm=float(max(errors)) if errors else None)
    return summary


def area_steps(areas):
    areas = np.asarray(areas)
    valid = (areas[:-1] > 0) & (areas[1:] > 0)
    changes = np.abs(np.diff(areas)[valid]) / areas[:-1][valid]
    return dict(events_over_10_percent=int(np.sum(changes > .1)),
                comparable_pairs=int(valid.sum()),
                maximum_relative_step=float(changes.max()) if len(changes) else None)


def paired_metrics(windows):
    """Compare errors only where both samplers return a scorable estimate."""
    result = {}
    for method in ('pos', 'green'):
        result[method] = {}
        for layout in ('three_regions', 'twelve_patches'):
            result[method][layout] = {}
            for gate in ('ungated', 'global_gate', 'regional_gate'):
                common = []
                for a, b in zip(windows['integer'], windows['fractional']):
                    values = []
                    for row in (a, b):
                        detail = row['methods'][method][layout]
                        values.append((detail if gate == 'ungated' else detail[gate])['error_bpm'])
                    if all(v is not None for v in values):
                        common.append([abs(v) for v in values])
                result[method][layout][gate] = dict(
                    common_windows=len(common),
                    integer_mae=float(np.mean(np.asarray(common)[:, 0])) if common else None,
                    fractional_mae=float(np.mean(np.asarray(common)[:, 1])) if common else None)
    return result


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as file:
        while chunk := file.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-seconds', type=float)
    parser.add_argument('--subdivisions', type=int, default=8, choices=range(1, 33))
    args = parser.parse_args()
    with FaceTracker(args.model) as tracker:
        paired = PairedTracker(tracker, args.subdivisions)
        baseline = extract_video(args.video, paired, patches=True, max_seconds=args.max_seconds)
    weighted = replace(baseline, rgb={n: np.asarray(v) for n, v in paired.rgb.items()},
                       patch_rgb={n: np.asarray(v) for n, v in paired.patch_rgb.items()})
    windows = score_pair(baseline, weighted, *load_reference(args.reference))
    report = dict(
        experiment='Exploratory sampling comparison on development video; not independent validation',
        configuration=dict(subdivisions=args.subdivisions, square_inset_pixels=1,
                           min_effective_area=30, gates='Fixed to integer baseline',
                           max_seconds=args.max_seconds),
        limitations=['Fractional coverage and continuous inset/quadrant boundaries change sampled support',
                     'Area-event reduction does not establish better pulse estimation',
                     'Device BPM discrepancies and unverified timestamp alignment remain unresolved',
                     'Overlapping windows and accepted-window errors are not full-cohort accuracy'],
        input=dict(video_sha256=sha256(args.video), reference_sha256=sha256(args.reference),
                   model_sha256=sha256(args.model), **baseline.metadata),
        versions={n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'opencv-contrib-python', 'mediapipe')},
        area_steps={zone: dict(integer=area_steps(baseline.pixels[zone]),
                               fractional=area_steps(paired.areas[zone])) for zone in REGIONS},
        missing_patch_frames={mode: {n: int((~np.isfinite(v).all(axis=1)).sum()) for n, v in e.patch_rgb.items()}
                              for mode, e in (('integer', baseline), ('fractional', weighted))},
        metrics={n: summarize(rows) for n, rows in windows.items()},
        paired_metrics=paired_metrics(windows), windows=windows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
