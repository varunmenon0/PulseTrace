import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from compare_area_gates import compare_gates, summarize
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.patches import PATCHES


def fixture():
    t = np.arange(0, 13, 1 / 30)
    pulse = np.sin(2 * np.pi * 1.2 * t)
    rgb = np.column_stack([100 + a * pulse for a in (1, 2, .5)])
    e = Extraction(t, {n: rgb.copy() for n in REGIONS},
                   {n: np.full(len(t), 100.) for n in REGIONS}, None, {}, {},
                   {n: np.zeros((len(t), 5)) for n in REGIONS},
                   {n: rgb.copy() for n in PATCHES})
    return e


def test_fractional_area_can_remove_raster_only_exclusion_on_identical_signals():
    e = fixture()
    fractional = replace(e, pixels={n: np.full(len(e.time), 100.) for n in REGIONS})
    for n in REGIONS:
        e.pixels[n][180:] = 120
    rows = compare_gates(e, fractional, e.time, np.full(len(e.time), 72.))
    first = rows[0]['sources']
    assert first['integer_area']['methods']['pos']['twelve_patches']['rejection_reason'] == 'quality_exclusions'
    assert abs(first['fractional_area']['methods']['pos']['twelve_patches']['bpm_candidate'] - 72) < 2
    metrics = summarize(rows)['pos']['twelve_patches']
    assert metrics['comparison']['newly_scorable_windows'] == 1


def test_fractional_gate_still_rejects_shared_motion():
    e = fixture()
    for n in ('forehead', 'left_cheek'):
        e.geometry[n][180, 2] = .1
    rows = compare_gates(e, replace(e), e.time, np.full(len(e.time), 72.))
    assert all(source['methods']['pos']['twelve_patches']['bpm_candidate'] is None
               for source in rows[0]['sources'].values())
