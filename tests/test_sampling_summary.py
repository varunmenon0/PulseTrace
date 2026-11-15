import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from summarize_sampling import summarize_reports


def report():
    return json.loads((Path(__file__).parents[1] /
                       'examples/equal-area-subject14/comparison.json').read_text())


def test_pooled_sampling_summary_preserves_failures_and_zero_accepted_gates():
    first = report()
    second = copy.deepcopy(first)
    second['input']['video_sha256'] = 'second-test-recording'
    result = summarize_reports([first, second])
    metrics = result['metrics']['fractional']['pos']['twelve_patches']
    assert metrics['ungated']['total_windows'] == 20
    assert metrics['ungated']['accepted_windows'] == 18
    assert metrics['global_gate']['accepted_windows'] == 0
    assert metrics['global_gate']['mae_against_device_bpm'] is None
    assert result['patch_observations_per_sampler'] == 2 * 1993 * 12
    coverage = result['coverage_changes']['pos']['twelve_patches']['ungated']
    assert coverage == dict(common=18, integer_only=2, fractional_only=0, neither=0)


def test_duplicate_recording_is_rejected():
    first = report()
    with pytest.raises(ValueError, match='Duplicate recording'):
        summarize_reports([first, first])


@pytest.mark.parametrize('mismatch', ['configuration', 'window_count', 'reference'])
def test_incompatible_sampling_reports_are_rejected(mismatch):
    first, second = report(), report()
    second['input']['video_sha256'] = 'second-test-recording'
    if mismatch == 'configuration':
        second['configuration']['subdivisions'] = 16
    elif mismatch == 'window_count':
        second['windows']['fractional'].pop()
    else:
        second['windows']['fractional'][0]['reference_bpm'] = 123
    with pytest.raises(ValueError):
        summarize_reports([first, second])
