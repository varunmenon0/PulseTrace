import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from stress_artifact_gates import fixture
from compare_area_gates import compare_gates
from pulsetrace.regional_quality import regional_masks


def test_abrupt_color_step_is_rejected_without_an_area_or_motion_event():
    e = fixture('shared_exposure_step')
    original = {n: v.copy() for n, v in e.rgb.items()}
    baseline, _ = regional_masks(e)
    guarded, _ = regional_masks(e, photometric_threshold=.02)
    assert all(not m.any() for m in baseline.values())
    assert all(m[180] and m[165] for m in guarded.values())
    assert all(not m[100] for m in guarded.values())
    assert all(np.array_equal(v, original[n]) for n, v in e.rgb.items())


def test_local_attenuation_preserves_other_regions():
    masks, shared = regional_masks(fixture('abrupt_local_attenuation'), photometric_threshold=.02)
    assert masks['left_cheek'][180]
    assert not masks['forehead'].any() and not masks['right_cheek'].any()
    assert not shared.any()


@pytest.mark.parametrize('case', ['clean', 'gradual_color_drift', 'periodic_lighting'])
def test_small_step_cases_expose_guard_limits(case):
    masks, _ = regional_masks(fixture(case), photometric_threshold=.02)
    assert all(not m.any() for m in masks.values())


@pytest.mark.parametrize('threshold', [0, -1, np.nan, np.inf])
def test_invalid_photometric_threshold_is_rejected(threshold):
    with pytest.raises(ValueError, match='photometric_threshold'):
        regional_masks(fixture('clean'), photometric_threshold=threshold)


@pytest.mark.parametrize('case', ['shared_exposure_step', 'abrupt_local_attenuation'])
def test_guard_filters_votes_from_affected_parents(case):
    e = fixture(case)
    rows = compare_gates(e, e, e.time, np.full(len(e.time), 72.), photometric_threshold=.02)
    detail = rows[0]['sources']['fractional_area_photometric']['methods']['pos']['twelve_patches']
    assert all(value is None for name, value in detail['individual_candidates'].items()
               if name.startswith('left_cheek'))
    if case == 'shared_exposure_step':
        assert detail['bpm_candidate'] is None
    else:
        assert abs(detail['bpm_candidate'] - 72) < 2


def test_periodic_lighting_can_still_fool_green_consensus():
    e = fixture('periodic_lighting')
    rows = compare_gates(e, e, e.time, np.full(len(e.time), 72.), photometric_threshold=.02)
    methods = rows[0]['sources']['fractional_area_photometric']['methods']
    assert abs(methods['green']['twelve_patches']['bpm_candidate'] - 108) < 2
    assert abs(methods['pos']['twelve_patches']['bpm_candidate'] - 72) < 2
