import threading

import numpy as np

from pulsetrace.capture import CameraSession
from pulsetrace.sampling import FrameSampler


def test_tracker_failure_stops_both_workers_and_releases_capture():
    sampled=threading.Event()
    class Capture:
        released=False
        first=True
        def isOpened(self): return True
        def set(self,*args): return False
        def get(self,*args): return float('nan')
        def read(self):
            if not self.first:
                assert sampled.wait(timeout=5)
            self.first=False
            return True,np.zeros((24,32,3),np.uint8)
        def release(self): self.released=True
    class Tracker:
        def detect(self,*args):
            sampled.set()
            raise ValueError('fixture tracker failed')
    capture=Capture()
    with CameraSession(Tracker(),FrameSampler(),capture_factory=lambda device:capture) as camera:
        assert camera.done.wait(timeout=5)
        assert camera.error=='fixture tracker failed'
    assert capture.released
    assert not camera.thread.is_alive() and not camera.capture_thread.is_alive()
    assert camera.statistics()['reported_camera_fps'] is None


def test_user_stop_releases_camera_and_keeps_frame_queues_bounded():
    ready=threading.Event()
    allow_read=threading.Event()
    class Capture:
        released=False
        def isOpened(self): return True
        def set(self,*args): return False
        def read(self):
            ready.set()
            assert allow_read.wait(timeout=5)
            return False,None
        def release(self): self.released=True
    capture=Capture()
    with CameraSession(None,None,capture_factory=lambda device:capture) as camera:
        assert ready.wait(timeout=5)
        camera.stop.set()
        allow_read.set()
    assert capture.released and camera.error is None
    assert camera.frame_queue.qsize()<=1 and camera.queue.qsize()<=120
    assert not camera.thread.is_alive() and not camera.capture_thread.is_alive()


def test_failed_release_still_signals_capture_completion():
    class Capture:
        def isOpened(self): return False
        def release(self): raise RuntimeError('fixture release failed')
    with CameraSession(None,None,capture_factory=lambda device:Capture()) as camera:
        assert camera.done.wait(timeout=5)
        assert camera.capture_done.is_set()
        assert 'Cannot open camera' in camera.error
    assert not camera.thread.is_alive() and not camera.capture_thread.is_alive()
