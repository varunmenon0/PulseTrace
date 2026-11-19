"""Camera acquisition and sampling on a worker, with a bounded handoff queue."""
import queue
import threading
import time

import cv2


class CameraSession:
    def __init__(self, tracker, sampler, *, device=0, queue_size=120,
                 capture_factory=None, clock=time.monotonic):
        if not isinstance(queue_size, int) or isinstance(queue_size, bool) or queue_size < 1:
            raise ValueError('Camera queue_size must be a positive integer')
        if not isinstance(device, int) or device < 0:
            raise ValueError('Camera index must be a nonnegative integer')
        self.tracker, self.sampler, self.device = tracker, sampler, device
        self.capture_factory = capture_factory or cv2.VideoCapture
        self.clock = clock
        self.queue = queue.Queue(maxsize=queue_size)
        self.stop = threading.Event()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.preview = None
        self.error = None
        self.frames = self.dropped_samples = 0

    def __enter__(self):
        self.started = self.clock()
        self.thread = threading.Thread(target=self._capture, name='pulsetrace-camera', daemon=True)
        self.thread.start()
        return self

    def _capture(self):
        camera = None
        try:
            camera = self.capture_factory(self.device)
            if not camera.isOpened():
                raise OSError("Cannot open camera; check its index and camera permission")
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Best effort; not supported by every backend.
            while not self.stop.is_set():
                ok, frame = camera.read()
                if not ok:
                    raise OSError("Camera stopped delivering frames")
                timestamp = self.clock()-self.started
                points = self.tracker.detect(frame, timestamp)
                sample = self.sampler.sample(frame, points, timestamp)
                with self.lock:
                    self.preview = (frame, points, timestamp)
                self.frames += 1
                try:
                    self.queue.put_nowait(sample)
                except queue.Full:
                    try:
                        self.queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.dropped_samples += 1
                    self.queue.put_nowait(sample)
        except Exception as exc:
            self.error = str(exc)
        finally:
            if camera is not None:
                camera.release()
            self.done.set()

    def latest_preview(self):
        with self.lock:
            return self.preview

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise OSError("Camera capture did not stop; close the camera session before restarting")
