import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from compare_subpixel import score_pair, paired_metrics
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.patches import PATCHES


def test_sampling_comparison_keeps_baseline_motion_exclusions():
    t = np.arange(0, 13, 1 / 30)
    rgb = np.column_stack([100 + .1 * np.sin(2 * np.pi * 1.2 * t),
                           100 + np.sin(2 * np.pi * 1.2 * t),
                           100 + .2 * np.sin(2 * np.pi * 1.2 * t)])
    baseline = Extraction(t, {n: rgb.copy() for n in REGIONS},
                          {n: np.full(len(t), 100.) for n in REGIONS}, None, {}, {},
                          {n: np.zeros((len(t), 5)) for n in REGIONS},
                          {n: rgb.copy() for n in PATCHES})
    baseline.pixels['forehead'][150:] = 150
    # Deliberately remove the weighted stream's area jump. Gates must still use
    # the original event. A weighted sampling change cannot admit this window.
    weighted = replace(baseline, pixels={n: np.full(len(t), 100.) for n in REGIONS})
    rows = score_pair(baseline, weighted, t, np.full(len(t), 72.))
    for mode in ('integer', 'fractional'):
        row = rows[mode][0]
        assert row['motion_excluded']
        detail = row['methods']['green']['twelve_patches']
        assert detail['bpm_candidate'] is not None
        assert detail['global_gate']['bpm_candidate'] is None
        assert all(v is None for n, v in detail['regional_gate']['individual_candidates'].items()
                   if n.startswith('forehead'))
    paired = paired_metrics(rows)['green']['twelve_patches']
    assert paired['ungated']['common_windows'] == 1
    assert paired['global_gate']['common_windows'] == 0
    assert paired['global_gate']['fractional_mae'] is None
    with pytest.raises(ValueError, match='identical timestamps'):
        score_pair(baseline, replace(weighted, time=t + .1), t, np.full(len(t), 72.))
