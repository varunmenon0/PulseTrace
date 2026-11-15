"""Compare integer-area and fractional-area regional gates on identical RGB."""
import argparse
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from benchmark_ubfc import load_reference
from compare_subpixel import PairedTracker, score_pair, sha256
from pulsetrace.patches import PATCHES
from pulsetrace.pipeline import extract_video
from pulsetrace.regional_quality import regional_masks, gate_candidates
from pulsetrace.regions import REGIONS
from pulsetrace.tracking import FaceTracker


def compare_gates(baseline, fractional, rt, rb):
    # Both gate variants vote on the same fractional RGB and spectral candidates.
    rows = score_pair(baseline, fractional, rt, rb)['fractional']
    sources = {'integer_area': baseline, 'fractional_area': fractional}
    masks = {name: regional_masks(extraction)[0] for name, extraction in sources.items()}
    result = []
    for row in rows:
        chosen = (baseline.time >= row['start_s']) & (baseline.time < row['end_s'])
        record = {k: row[k] for k in ('start_s', 'end_s', 'reference_bpm', 'reference_warning')}
        record['sources'] = {}
        for source, region_masks in masks.items():
            usable = {n: not bool(mask[chosen].any()) for n, mask in region_masks.items()}
            detail = dict(usable_regions=usable,
                          rejected_frames_by_region={n: int(m[chosen].sum()) for n, m in region_masks.items()},
                          methods={})
            for method, layouts in row['methods'].items():
                detail['methods'][method] = {}
                for layout, estimates in layouts.items():
                    zones = PATCHES if layout == 'twelve_patches' else {n: n for n in REGIONS}
                    decision = gate_candidates(estimates['individual_candidates'], zones, usable)
                    valid = [n for n, v in decision['individual_candidates'].items() if v is not None]
                    valid_zones = len({zones[n] for n in valid})
                    bpm = decision['bpm_candidate']
                    reason = None
                    if bpm is None:
                        reason = ('quality_exclusions' if sum(usable.values()) < 2 else
                                  'insufficient_spectral_support' if valid_zones < 2 else
                                  'no_unique_majority_consensus')
                    decision.update(valid_candidates=len(valid), valid_parent_zones=valid_zones,
                                    rejection_reason=reason,
                                    error_bpm=None if bpm is None or row['reference_bpm'] is None else bpm-row['reference_bpm'])
                    detail['methods'][method][layout] = decision
            record['sources'][source] = detail
        result.append(record)
    return result


def summarize(rows):
    result = {}
    for method in ('pos', 'green'):
        result[method] = {}
        for layout in ('three_regions', 'twelve_patches'):
            metrics = {}
            for source in ('integer_area', 'fractional_area'):
                details = [r['sources'][source]['methods'][method][layout] for r in rows]
                errors = [d['error_bpm'] for d in details if d['error_bpm'] is not None]
                metrics[source] = dict(total_windows=len(rows),
                    reference_valid_windows=sum(r['reference_bpm'] is not None for r in rows),
                    scorable_windows=len(errors),
                    mae_against_device_bpm=float(np.mean(np.abs(errors))) if errors else None,
                    max_difference_bpm=float(np.max(np.abs(errors))) if errors else None,
                    rejections={reason: sum(d['rejection_reason'] == reason for d in details)
                                for reason in ('quality_exclusions', 'insufficient_spectral_support', 'no_unique_majority_consensus')})
            changes = {'common': [], 'newly_scorable': [], 'lost': []}
            for r in rows:
                a, b = [r['sources'][s]['methods'][method][layout]['error_bpm']
                        for s in ('integer_area', 'fractional_area')]
                if a is not None and b is not None:
                    changes['common'].append([a, b])
                elif b is not None:
                    changes['newly_scorable'].append(b)
                elif a is not None:
                    changes['lost'].append(a)
            metrics['comparison'] = dict(common_windows=len(changes['common']),
                common_integer_mae=float(np.mean(np.abs(np.array(changes['common'])[:, 0]))) if changes['common'] else None,
                common_fractional_mae=float(np.mean(np.abs(np.array(changes['common'])[:, 1]))) if changes['common'] else None,
                newly_scorable_windows=len(changes['newly_scorable']), lost_windows=len(changes['lost']),
                newly_scorable_mae=float(np.mean(np.abs(changes['newly_scorable']))) if changes['newly_scorable'] else None,
                newly_scorable_max_difference=float(np.max(np.abs(changes['newly_scorable']))) if changes['newly_scorable'] else None)
            result[method][layout] = metrics
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'reference', 'model', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with FaceTracker(args.model) as tracker:
        paired = PairedTracker(tracker, 8, 'equal_area')
        baseline = extract_video(args.video, paired, patches=True)
    fractional = replace(baseline, rgb={n: np.asarray(v) for n, v in paired.rgb.items()},
                         patch_rgb={n: np.asarray(v) for n, v in paired.patch_rgb.items()},
                         pixels={n: np.asarray(v) for n, v in paired.areas.items()})
    rows = compare_gates(baseline, fractional, *load_reference(args.reference))
    report = dict(experiment='Exploratory area-source gate comparison on development data',
        configuration=dict(sampling='equal-area fractional RGB for both gates', subdivisions=8,
                           area_threshold=.10, motion_threshold=.05, buffer_seconds=.5,
                           window_seconds=12, step_seconds=6, max_gap_seconds=.25),
        input=dict(video_sha256=sha256(args.video), reference_sha256=sha256(args.reference),
                   model_sha256=sha256(args.model), **baseline.metadata),
        versions={n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'opencv-contrib-python', 'mediapipe')},
        limitations=['Only area source and resulting sample validity change; thresholds are unvalidated',
                     'Displacement, shared motion/loss, buffers, spectra, and consensus stay unchanged',
                     'Stored device BPM and assumed shared time origin are not independently validated',
                     'No device labels, time offsets, or expected BPM select candidates',
                     'No default or previously frozen evaluation changes'],
        metrics=summarize(rows), windows=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
