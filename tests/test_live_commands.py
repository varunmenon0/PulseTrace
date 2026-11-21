import json
import threading

import numpy as np
import pytest

from pulsetrace.capture import CameraSession
from pulsetrace.cli import main
from pulsetrace.controlled import ControlledTracker, make_controlled_video
from pulsetrace.live import replay
from pulsetrace.pipeline import extract_video
from pulsetrace.sampling import FrameSampler, samples_to_extraction
from pulsetrace.video import VideoReader


@pytest.mark.parametrize('sampling', ['landmarks', 'fractional', 'template'])
def test_frame_sampler_and_batch_extraction_keep_identical_measurements(tmp_path, sampling):
    video = tmp_path/'fixture.avi'
    make_controlled_video(video, seconds=13, fps=15)
    batch = extract_video(video, ControlledTracker(), patches=True, sampling=sampling)
    tracker = ControlledTracker()
    sampler = FrameSampler(sampling=sampling)
    with VideoReader(video) as reader:
        streamed = samples_to_extraction([sampler.sample(f.bgr, tracker.detect(f.bgr, f.time), f.time) for f in reader])
    np.testing.assert_array_equal(streamed.time, batch.time)
    for field in ('rgb', 'pixels', 'geometry', 'patch_rgb', 'patch_pixels'):
        for name, values in getattr(batch, field).items():
            np.testing.assert_array_equal(getattr(streamed, field)[name], values)


def test_replay_cli_audits_completed_windows_and_keeps_incomplete_tail(tmp_path, capsys):
    video = tmp_path/'fixture.avi'
    make_controlled_video(video, seconds=25, fps=15)
    output = tmp_path/'replay'
    assert main(['replay', str(video), '--fixture-profile', 'clean', '--verify-batch',
                 '--sampling', 'landmarks', '--output', str(output)]) == 0
    report = json.loads((output/'stream-summary.json').read_text())
    assert report['batch_parity']['compared_windows'] == 3
    assert report['batch_parity']['passed']
    assert report['synthetic']
    events = [json.loads(line) for line in (output/'stream.jsonl').read_text().splitlines()]
    windows = [e for e in events if e['type'] == 'window']
    assert len(windows) == 3
    assert all(abs(e['bpm']-72) < 1 for e in windows)
    assert all(e['observed_at_s'] >= e['end_s']+.5-1e-9 for e in windows)
    assert {p.suffix for p in output.iterdir()} == {'.json', '.jsonl'}
    assert 'recorded_streaming_replay' in capsys.readouterr().out


def test_replay_does_not_flush_a_window_without_future_support(tmp_path):
    video = tmp_path/'fixture.avi'
    make_controlled_video(video, seconds=12.3, fps=30)
    report = replay(video, ControlledTracker(), tmp_path/'result', sampling='landmarks', verify=True, synthetic=True)
    assert report['finalized_windows'] == 0
    assert report['batch_parity']['unfinalized_batch_windows'] == 1


def test_camera_worker_queue_is_bounded_and_releases_capture():
    class Capture:
        def __init__(self):
            self.frames = 0
            self.released = False
        def isOpened(self): return True
        def set(self, *args): return False
        def read(self):
            self.frames += 1
            return (True, np.zeros((32, 32, 3), np.uint8)) if self.frames <= 8 else (False, None)
        def release(self): self.released = True
    class Tracker:
        def detect(self, frame, time): return None
    capture = Capture()
    ticks = iter(np.arange(20)/30)
    with CameraSession(Tracker(), FrameSampler(sampling='landmarks'), queue_size=2,
                       capture_factory=lambda device: capture, clock=lambda: next(ticks)) as camera:
        assert camera.done.wait(timeout=5)
        assert camera.queue.qsize() == 2
        assert camera.dropped_samples == 6
        assert camera.frames == 8
        assert 'stopped delivering' in camera.error
    assert capture.released
    with pytest.raises(ValueError):
        CameraSession(Tracker(), FrameSampler(), queue_size=0)


def test_camera_open_failure_is_reported_and_capture_released():
    class Capture:
        released = False
        def isOpened(self): return False
        def release(self): self.released = True
    capture = Capture()
    with CameraSession(None, None, capture_factory=lambda device: capture) as camera:
        assert camera.done.wait(timeout=5)
        assert 'permission' in camera.error
    assert capture.released


def test_webcam_headless_runner_uses_mock_capture_without_opening_a_camera(tmp_path, monkeypatch, capsys):
    import queue
    import pulsetrace.capture
    import pulsetrace.tracking
    import pulsetrace.live as live
    from test_streaming import samples
    class Tracker:
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Camera:
        def __init__(self, *args, **kwargs):
            self.queue = queue.Queue()
            data = list(samples(14))
            for s in data: self.queue.put(s)
            self.frames = len(data)
            self.dropped_samples = 0
            self.started = live.time.monotonic()-data[-1].time
            self.done = threading.Event()
            self.done.set()
            self.error = None
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(pulsetrace.capture, 'CameraSession', Camera)
    monkeypatch.setattr(pulsetrace.tracking, 'FaceTracker', Tracker)
    output = tmp_path/'camera'
    assert main(['webcam', '--model', 'fixture.task', '--no-preview', '--output', str(output)]) == 0
    report = json.loads((output/'stream-summary.json').read_text())
    assert report['estimated_windows'] == 1 and not report['frames_saved']
    assert sorted(p.name for p in output.iterdir()) == ['samples.jsonl', 'stream-summary.json', 'stream.jsonl']
    assert report['saved_samples'] == report['sampled_frames']
    capsys.readouterr()


def test_format_change_resets_sampling_geometry():
    sampler = FrameSampler(sampling='landmarks')
    frame = np.full((240, 320, 3), 100, np.uint8)
    tracker = ControlledTracker()
    sampler.sample(frame, tracker.detect(frame, 0), 0)
    resized = np.full((480, 640, 3), 100, np.uint8)
    sample = sampler.sample(resized, tracker.detect(resized, .1), .1)
    assert sample.reset_reason == 'camera_format_change'
    assert all(np.isnan(g[2]) for g in sample.geometry.values())


def test_webcam_failure_emits_unavailable_and_closes_session(tmp_path, monkeypatch):
    import queue
    import pulsetrace.capture
    from pulsetrace.live import webcam
    class Camera:
        closed = False
        def __init__(self, *args, **kwargs):
            self.queue = queue.Queue()
            self.done = threading.Event()
            self.done.set()
            self.error = 'Camera permission denied'
            self.started = 0
        def __enter__(self): return self
        def __exit__(self, *args): Camera.closed = True
    monkeypatch.setattr(pulsetrace.capture, 'CameraSession', Camera)
    with pytest.raises(OSError, match='permission'):
        webcam(None, tmp_path, preview=False)
    events = [json.loads(line) for line in (tmp_path/'stream.jsonl').read_text().splitlines()]
    assert Camera.closed
    assert events[-1]['type'] == 'error' and events[-1]['bpm'] is None
