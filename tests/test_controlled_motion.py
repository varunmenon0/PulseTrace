import cv2
import numpy as np
import pytest

from pulsetrace.controlled import ControlledTracker, make_controlled_video, motion_offset, scene
from pulsetrace.pipeline import extract_video
from pulsetrace.regional_quality import write_regional_comparison
from pulsetrace.trends import write_trend


def test_translated_video_and_known_landmarks_move_together(tmp_path):
    path = tmp_path/'moving.avi'
    make_controlled_video(path, seconds=10, profile='steady_motion')
    capture = cv2.VideoCapture(str(path))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, 15)
        ok, frame = capture.read()
        assert ok
        # At 0.5 seconds, the 72 BPM pulse rounds to [-0, -2, -0] in BGR.
        base, skin = scene()
        base[skin] += np.sin(2*np.pi*72/60*.5)*np.array([.2, 3., .6])
        dx, dy = motion_offset('steady_motion', .5)
        expected = cv2.warpAffine(np.rint(base).astype(np.uint8), np.float32([[1, 0, dx], [0, 1, dy]]),
            (320, 240), flags=cv2.INTER_NEAREST, borderValue=(60, 45, 35))
        assert np.array_equal(frame, expected)
        assert np.array_equal(ControlledTracker('steady_motion').detect(frame, .5)-ControlledTracker().detect(frame, .5),
                              np.tile([dx, dy], (478, 1)))
    finally:
        capture.release()


def test_burst_is_excluded_and_clean_windows_recover(tmp_path):
    path = tmp_path/'burst.avi'
    make_controlled_video(path, seconds=36, profile='motion_burst')
    extraction = extract_video(path, ControlledTracker('motion_burst'), patches=True)
    trend = write_trend(write_regional_comparison(extraction, tmp_path, consensus_policy='zone'), tmp_path)
    assert len(trend['windows']) == 5
    for row in trend['windows']:
        rejected = row['start_s'] in (12, 18)
        assert row['shared_motion_or_loss'] == rejected
        assert len(row['excluded_regions']) == (3 if rejected else 0)
        for method in ('green', 'pos'):
            bpm = row['methods'][method]['bpm_candidate']
            if rejected:
                assert bpm is None
            else:
                assert abs(bpm-72) < 1
    assert trend['windows'][-1]['available_at_s'] == 36


def test_short_burst_clip_cannot_silently_omit_recovery(tmp_path):
    with pytest.raises(ValueError, match='>=36 seconds'):
        make_controlled_video(tmp_path/'bad.avi', seconds=20, profile='motion_burst')
