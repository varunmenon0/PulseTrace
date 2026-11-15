"""Deterministic RGB/geometry stress cases, separate from natural-video evidence."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from compare_area_gates import compare_gates, summarize
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.patches import PATCHES
from pulsetrace.regional_quality import regional_masks


CASES = ('clean', 'shared_motion', 'single_region_loss', 'abrupt_local_attenuation',
         'shared_exposure_step', 'gradual_color_drift', 'periodic_lighting')


def fixture(case):
    if case not in CASES:
        raise ValueError('Unknown stress case')
    t = np.arange(0, 25, 1 / 30)
    rgb = np.array([160., 110., 80.]) + np.sin(2 * np.pi * 1.2 * t)[:, None] * [.6, 2., .2]
    colors = {n: rgb.copy() for n in REGIONS}
    pixels = {n: np.full(len(t), 240.) for n in REGIONS}
    geometry = {n: np.zeros((len(t), 5)) for n in REGIONS}
    event = (t >= 6) & (t < 7)
    if case == 'shared_motion':
        for n in ('forehead', 'left_cheek'):
            geometry[n][180, 2] = .15
            geometry[n][210, 2] = .15
    elif case == 'single_region_loss':
        colors['left_cheek'][event] = np.nan
        pixels['left_cheek'][event] = 0
    elif case == 'abrupt_local_attenuation':
        colors['left_cheek'][event] *= .55
    elif case == 'shared_exposure_step':
        for values in colors.values():
            values[event] *= 1.12
    elif case == 'gradual_color_drift':
        gain = 1 - .4 * np.maximum(0, 1 - abs(t - 9) / 3)
        for values in colors.values():
            values *= gain[:, None]
    elif case == 'periodic_lighting':
        gain = 1 + .03 * np.sin(2 * np.pi * 1.8 * t)
        for values in colors.values():
            values *= gain[:, None]
    return Extraction(t, colors, pixels, None, {},
                      dict(synthetic=True, tracking='Injected geometry, no MediaPipe', case=case),
                      geometry, {n: colors[zone].copy() for n, zone in PATCHES.items()},
                      {n: pixels[zone] / 4 for n, zone in PATCHES.items()})


def run():
    results = {}
    for case in CASES:
        e = fixture(case)
        fractional = replace(e, pixels={n: v.copy() for n, v in e.pixels.items()})
        rows = compare_gates(e, fractional, e.time, np.full(len(e.time), 72.),
                             photometric_threshold=.02)
        masks = {label: regional_masks(e, photometric_threshold=threshold)[0]
                 for label, threshold in (('area_only', None), ('photometric', .02))}
        results[case] = dict(
            buffered_rejected_frame_counts={label: {n: int(m.sum()) for n, m in zones.items()}
                                            for label, zones in masks.items()},
            metrics=summarize(rows), windows=rows)
    return dict(fixture='Synthetic RGB traces and geometry, no decoder or face model',
                configuration=dict(seconds=25, sample_rate_hz=30, injected_pulse_bpm=72,
                                   periodic_lighting_bpm=108, photometric_threshold=.02),
                limitations=['Not a natural video, human pulse, or occlusion-detector validation',
                             'Abrupt attenuation approximates an RGB consequence of occlusion, not a physical occluder',
                             'Clean trace has no camera noise; it is an engineering control',
                             'Gradual drift and low-step periodic lighting expose known blind spots',
                             'No thresholds or expected-rate-based selection change between cases'],
                cases=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run(), indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
