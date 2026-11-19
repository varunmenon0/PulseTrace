import copy
import json

import numpy as np

from pulsetrace.regional_quality import build_regional_comparison, regional_masks
from pulsetrace.sampling import samples_to_extraction
from pulsetrace.stream_diagnostics import longest_interval
from pulsetrace.streaming import PulseStream
from test_streaming import samples


def report(data, policy='continuous'):
    return build_regional_comparison(samples_to_extraction(data), window_starts=[0.],
                                    window_policy=policy, include_diagnostics=True)['windows'][0]


def test_local_area_change_is_attributed_without_rejecting_clean_pair():
    data = list(samples(13))
    for s in data:
        if s.time >= 6:
            s.pixels['left_cheek'] = 150.
    row = report(data)
    quality = row['quality']
    left = quality['regions']['left_cheek']
    assert left['raw_flagged_samples']['area_change'] == 1
    assert left['buffered_excluded_samples']['area_change'] > 1
    assert left['peak_area_step_fraction'] == .5
    assert left['peak_displacement_face_units'] == 0
    assert left['exclusion_causes'] == ['area_change']
    assert not quality['regions']['forehead']['exclusion_causes']
    assert quality['clean_pair_requirement_met']
    assert row['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate'] is not None


def test_shared_missing_samples_explain_failure_and_other_region_inheritance():
    data = list(samples(13))
    for s in data:
        if 2 <= s.time < 3:
            for name in ('left_cheek', 'right_cheek'):
                s.pixels[name] = 0
                s.rgb[name][:] = np.nan
    row = report(data)
    q = row['quality']
    assert row['analysis_start_s'] is None
    assert not q['clean_pair_requirement_met']
    assert q['longest_clean_pair']['duration_s'] < 10
    assert q['shared_raw_flagged_samples'] == 30
    assert q['regions']['left_cheek']['raw_flagged_samples']['missing_samples'] == 30
    forehead = q['regions']['forehead']
    assert forehead['raw_flagged_samples']['missing_samples'] == 0
    assert forehead['buffered_excluded_samples']['missing_samples'] == 0
    assert forehead['excluded_samples'] > 0
    assert forehead['exclusion_causes'] == ['shared_motion_or_loss']


def test_lookahead_motion_is_logged_as_buffered_effect_not_an_in_window_event():
    data = list(samples(13))
    for s in data:
        if 12.09 < s.time < 12.12:
            for n in ('left_cheek', 'right_cheek'):
                s.geometry[n][2] = .1
    row = report(data, 'full')
    q = row['quality']
    assert q['shared_raw_flagged_samples'] == 0
    assert q['shared_buffered_excluded_samples'] > 0
    assert q['regions']['left_cheek']['raw_flagged_samples']['motion'] == 0
    assert q['regions']['left_cheek']['buffered_excluded_samples']['motion'] > 0
    assert 'shared_motion_or_loss' in q['regions']['forehead']['exclusion_causes']
    assert row['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate'] is None


def test_observation_does_not_change_masks_estimates_support_or_intervals():
    data = list(samples(25))
    for s in data:
        if 6 <= s.time < 6.1:
            s.geometry['left_cheek'][2] = .1
    extraction = samples_to_extraction(data)
    masks, shared = regional_masks(extraction)
    observed_masks, observed_shared, _ = regional_masks(extraction, return_details=True)
    for n in masks:
        np.testing.assert_array_equal(masks[n], observed_masks[n])
    np.testing.assert_array_equal(shared, observed_shared)
    baseline = build_regional_comparison(extraction, window_policy='continuous')
    observed = build_regional_comparison(extraction, window_policy='continuous', include_diagnostics=True)
    for row in observed['windows']:
        row.pop('quality')
    assert observed == baseline


def test_missing_geometry_is_json_safe_and_clean_but_flat_signal_is_not_quality_failure():
    data = list(samples(13))
    for s in data:
        for n in s.geometry:
            s.geometry[n][:] = np.nan
            s.rgb[n][:] = 100.
        for rgb in s.patch_rgb.values():
            rgb[:] = 100.
    engine = PulseStream()
    readings = [r for s in data for r in engine.push(s)]
    row = readings[0].to_dict()
    assert row['unavailable_reason'] == 'insufficient_pulse_support'
    assert row['quality']['clean_pair_requirement_met']
    assert row['quality']['regions']['forehead']['peak_displacement_face_units'] is None
    json.dumps(row, allow_nan=False)
    original = copy.deepcopy(row)
    row['quality']['regions']['forehead']['excluded_samples'] = 999
    assert readings[0].to_dict() == original


def test_all_missing_support_and_timestamp_gaps_are_reported_honestly():
    data = list(samples(13))
    for s in data:
        for n in s.pixels:
            s.pixels[n] = 0
            s.rgb[n][:] = np.nan
            s.geometry[n][:] = np.nan
    q = report(data)['quality']
    assert q['longest_clean_pair']['start_s'] is None
    assert q['longest_clean_pair']['duration_s'] == 0
    assert q['regions']['forehead']['excluded_fraction'] == 1
    json.dumps(q, allow_nan=False)
    t = np.array([0., 1., 2., 10., 11.])
    best = longest_interval(t, np.ones(5, bool), max_gap=1.1)
    assert best == dict(start_s=0., end_s=2., duration_s=2., samples=3)
