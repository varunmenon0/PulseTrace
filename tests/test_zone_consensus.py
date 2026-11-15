import json

import numpy as np
import pytest

from pulsetrace.patches import PATCHES, consensus
from pulsetrace.zone_consensus import hierarchical_consensus
from pulsetrace.regional_quality import gate_candidates


def values(forehead, left, right):
    return {name: value for zone, group in zip(('forehead', 'left_cheek', 'right_cheek'),
                                             (forehead, left, right))
            for name, value in zip([n for n in PATCHES if PATCHES[n] == zone], group)}


def test_each_parent_has_one_vote_despite_unequal_patch_availability():
    candidates = values([72]*4, [72, 95, 95, None], [95, 95, None, None])
    assert consensus(candidates, PATCHES)['bpm_candidate'] == 72
    result = hierarchical_consensus(candidates, PATCHES)
    assert result['bpm_candidate'] == 95
    assert set(result['supporting_zones']) == {'left_cheek', 'right_cheek'}
    assert not any(n.startswith('forehead') for n in result['support'])


def test_single_supporting_patch_cannot_establish_a_zone_vote():
    candidates = values([72]*4, [72, None, None, None], [None]*4)
    assert consensus(candidates, PATCHES)['bpm_candidate'] == 72
    result = hierarchical_consensus(candidates, PATCHES)
    assert result['bpm_candidate'] is None
    assert result['zone_candidates']['left_cheek']['status'] == 'insufficient_patches'


def test_ambiguous_local_and_cross_zone_clusters_are_rejected():
    candidates = values([70, 70, 100, 100], [72]*4, [100]*4)
    result = hierarchical_consensus(candidates, PATCHES)
    assert result['zone_candidates']['forehead']['bpm_candidate'] is None
    assert result['rejection_reason'] == 'zone_disagreement'
    candidates = values([70]*4, [74]*4, [78]*4)
    assert hierarchical_consensus(candidates, PATCHES)['bpm_candidate'] is None


def test_quality_excluded_zones_cannot_vote_or_be_resurrected():
    candidates = values([72]*4, [72]*4, [72]*4)
    result = gate_candidates(candidates, PATCHES,
                             dict(forehead=True, left_cheek=False, right_cheek=False),
                             consensus_policy='zone')
    assert result['bpm_candidate'] is None
    assert result['accepted_zone_count'] == 1


def test_order_invariance_and_empty_input():
    candidates = values([72, 73, 74, 100], [73]*4, [None]*4)
    a = hierarchical_consensus(candidates, PATCHES)
    b = hierarchical_consensus(dict(reversed(list(candidates.items()))), PATCHES)
    assert a == b and a['bpm_candidate'] == 73
    assert hierarchical_consensus({}, PATCHES)['bpm_candidate'] is None


@pytest.mark.parametrize('bad', [np.nan, np.inf, -1])
def test_invalid_candidates_are_rejected(bad):
    with pytest.raises(ValueError):
        hierarchical_consensus({'forehead_tl': bad}, PATCHES)


def test_unknown_mapping_and_invalid_tolerance():
    with pytest.raises(ValueError):
        hierarchical_consensus({'unknown': 72}, PATCHES)
    with pytest.raises(ValueError):
        hierarchical_consensus({}, PATCHES, tolerance=0)


def test_cli_zone_option_requires_patches():
    from pulsetrace.cli import main
    with pytest.raises(SystemExit):
        main(['demo', '--consensus', 'zone'])


def test_common_lighting_can_still_agree_across_all_zones():
    from pathlib import Path
    source = json.loads((Path(__file__).parents[1]/'examples/photometric-guard/synthetic.json').read_text())
    methods = source['cases']['periodic_lighting']['windows'][0]['sources']['fractional_area_photometric']['methods']
    for method, expected in (('green', 108), ('pos', 72)):
        result = hierarchical_consensus(methods[method]['twelve_patches']['individual_candidates'], PATCHES)
        assert len(result['supporting_zones']) == 3
        assert abs(result['bpm_candidate'] - expected) < 2


def test_cli_zone_policy_reaches_patch_and_regional_reports(tmp_path, monkeypatch):
    from pulsetrace.cli import main
    from pulsetrace.synthetic import make_video, SyntheticTracker
    import pulsetrace.tracking
    class Tracker(SyntheticTracker):
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(pulsetrace.tracking, 'FaceTracker', Tracker)
    video = tmp_path/'input.avi'
    make_video(video, seconds=12)
    output = tmp_path/'reports'
    assert main(['analyze', str(video), '--model', 'fixture.task', '--patches',
                 '--regional-quality', '--consensus', 'zone', '--output', str(output)]) == 0
    patch = json.loads((output/'patch_comparison.json').read_text())
    regional = json.loads((output/'regional_comparison.json').read_text())
    assert patch['consensus_policy'] == 'zone'
    assert regional['configuration']['consensus_policy'] == 'zone'
    detail = regional['windows'][0]['methods']['pos']['twelve_patches']['regional_gate']
    assert len(detail['supporting_zones']) == 3
    assert abs(detail['bpm_candidate'] - 72) < 2
