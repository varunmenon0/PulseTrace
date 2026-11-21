import numpy as np

from pulsetrace.patches import PATCHES
from pulsetrace.regional_quality import build_regional_comparison
from pulsetrace.sampling import samples_to_extraction
from test_streaming import samples


def describe(data):
    row = build_regional_comparison(samples_to_extraction(data), window_starts=[0],
                                   window_policy='continuous', include_diagnostics=True)['windows'][0]
    return row, row['quality']['pulse_methods']['pos']


def test_good_patch_spectra_are_distinguished_from_cross_region_disagreement():
    data = list(samples(13))
    rates = {'forehead':72., 'left_cheek':100., 'right_cheek':140.}
    for s in data:
        for patch,zone in PATCHES.items():
            pulse = np.sin(2*np.pi*rates[zone]/60*s.time)
            s.patch_rgb[patch] = np.array([100+pulse,100+2*pulse,100+.5*pulse])
    row, detail = describe(data)
    assert row['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate'] is None
    assert detail['consensus']['rejection_reason'] == 'no_unique_cross_region_majority'
    assert detail['consensus']['eligible_patch_count'] == 12
    for patch,d in detail['patches'].items():
        assert d['signal_status'] == 'candidate'
        assert abs(d['candidate_bpm']-rates[PATCHES[patch]]) < 1
        assert d['peak_fraction'] >= .35 and d['band_power'] > 0


def test_flat_signals_missing_patches_and_quality_exclusions_are_distinct():
    data = list(samples(13))
    for s in data:
        for patch in s.patch_rgb:
            s.patch_rgb[patch][:] = 100
    _, detail = describe(data)
    assert detail['consensus']['rejection_reason'] == 'insufficient_valid_patch_candidates'
    assert all(d['signal_status'] == 'flat_signal' for d in detail['patches'].values())
    data = list(samples(13))
    data[150].patch_rgb['forehead_tl'][:] = np.nan
    for s in data:
        if s.time >= 6:
            s.pixels['left_cheek'] = 150
    _, detail = describe(data)
    missing = detail['patches']['forehead_tl']
    assert missing['signal_status'] == 'missing_samples' and missing['valid_sample_fraction'] < 1
    excluded = detail['patches']['left_cheek_tl']
    assert excluded['signal_status'] == 'candidate' and excluded['candidate_bpm'] is not None
    assert not excluded['region_usable'] and excluded['eligible_bpm'] is None


def test_enabling_patch_observation_preserves_all_existing_decisions():
    e = samples_to_extraction(list(samples(20)))
    original = build_regional_comparison(e, window_policy='continuous')
    observed = build_regional_comparison(e, window_policy='continuous', include_diagnostics=True)
    for row in observed['windows']:
        assert set(row['quality']['pulse_methods']) == {'pos','green'}
        row.pop('quality')
    assert original == observed
