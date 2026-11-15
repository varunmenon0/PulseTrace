import csv
import json

import cv2
import numpy as np
import pytest

from pulsetrace.cli import main
from pulsetrace.controlled import ControlledTracker, face_visible, make_controlled_video


@pytest.mark.parametrize('profile', ['face_loss', 'face_loss_tail'])
def test_cli_retains_loss_gaps_and_never_reuses_old_rate(tmp_path, profile):
    output = tmp_path/profile
    assert main(['demo', '--profile', profile, '--bpm', '72', '--end-bpm', '108',
                 '--seconds', '36', '--track', '--patches', '--consensus', 'zone', '--output', str(output)]) == 0
    trend = json.loads((output/'pulse_trend.json').read_text())
    assert len(trend['windows']) == 5
    for row in trend['windows']:
        rejected = row['start_s'] in (12, 18) or (profile == 'face_loss_tail' and row['start_s'] >= 24)
        assert row['shared_motion_or_loss'] == rejected
        assert len(row['sample_loss_regions']) == (3 if rejected else 0)
        for method in ('green', 'pos'):
            detail = row['methods'][method]
            if rejected:
                assert detail['bpm_candidate'] is None
                assert detail['unavailable_reason'] == 'quality_exclusion'
            else:
                assert abs(detail['bpm_candidate']-(72+row['center_s'])) < 1
                assert detail['unavailable_reason'] is None
    with (output/'pulse_trend.csv').open() as file:
        rows = list(csv.DictReader(file))
    assert rows[2]['pos_bpm'] == ''
    assert rows[2]['pos_unavailable_reason'] == 'quality_exclusion'
    assert rows[2]['sample_loss_regions'] == 'forehead;left_cheek;right_cheek'
    # Video absence and missing RGB samples agree at the event, rather than just
    # masking estimates afterward. The background still has one sample per frame.
    capture = cv2.VideoCapture(str(output/'synthetic.avi'))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, 600)
        ok, frame = capture.read()
        assert ok and np.all(frame == [60, 45, 35])
        tracker = ControlledTracker(profile)
        assert tracker.detect(frame, 20) is None
        assert len(tracker.background_rgb) == 1
    finally:
        capture.release()
    with (output/'rgb.csv').open() as file:
        samples = list(csv.DictReader(file))
    assert float(samples[600]['forehead_pixels']) == 0
    assert np.isnan(float(samples[600]['forehead_g']))


def test_visibility_boundaries_and_short_fixture_rejection(tmp_path):
    assert face_visible('face_loss', 19.99)
    assert not face_visible('face_loss', 20)
    assert not face_visible('face_loss', 21.99)
    assert face_visible('face_loss', 22)
    assert not face_visible('face_loss_tail', 40)
    for profile in ('face_loss', 'face_loss_tail'):
        with pytest.raises(ValueError, match='>=36 seconds'):
            make_controlled_video(tmp_path/'short.avi', profile=profile, seconds=20)
