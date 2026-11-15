import json

import cv2
import numpy as np
import pytest

from pulsetrace.agreement import method_agreement
from pulsetrace.controlled import make_controlled_video, ControlledTracker, scene
from pulsetrace.pipeline import extract_video


def test_lossless_fixture_localizes_pulse_and_preserves_background(tmp_path):
    path = tmp_path/'clean.avi'
    metadata = make_controlled_video(path, seconds=10)
    capture = cv2.VideoCapture(str(path))
    try:
        ok, first = capture.read()
        assert ok
        capture.set(cv2.CAP_PROP_POS_FRAMES, 6)
        ok, peak = capture.read()
        assert ok
        base, skin = scene()
        assert np.array_equal(first, base.astype(np.uint8))
        assert np.array_equal(first[~skin], peak[~skin])
        assert peak[skin, 1].mean()-first[skin, 1].mean() == 3
        assert capture.get(cv2.CAP_PROP_FRAME_COUNT) == 300
        assert metadata['codec'] == 'FFV1'
    finally:
        capture.release()


def test_clean_cli_runs_decoding_sampling_and_both_methods(tmp_path):
    from pulsetrace.cli import main
    output = tmp_path/'demo'
    assert main(['demo', '--profile', 'clean', '--patches', '--consensus', 'zone',
                 '--seconds', '12', '--output', str(output)]) == 0
    report = json.loads((output/'controlled_check.json').read_text())
    assert report['method_agreement']['status'] == 'agreement'
    assert report['background']['bpm_candidate'] is None
    for method in ('green', 'pos'):
        assert len(report['methods'][method]['patches']) == 12
        assert abs(report['methods'][method]['patch_consensus']['bpm_candidate']-72) < 2
    summary = json.loads((output/'summary.json').read_text())
    assert summary['metadata']['profile'] == 'clean'
    assert summary['metadata']['decoded_frames'] == 360


def test_lighting_cue_uses_estimates_not_expected_rate():
    result = method_agreement(108, 72, background_bpm=108)
    assert result['shared_lighting_cue'] and result['status'] == 'method_disagreement'
    assert method_agreement(72, 72)['status'] == 'agreement'
    assert method_agreement(None, 72)['status'] == 'insufficient_estimates'
    assert not method_agreement(72, 72, background_bpm=72)['shared_lighting_cue']


@pytest.mark.parametrize('kwargs', [dict(bpm=np.nan), dict(fps=0), dict(seconds=1), dict(profile='unknown')])
def test_invalid_fixture_configuration_is_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        make_controlled_video(tmp_path/'bad.avi', **kwargs)
