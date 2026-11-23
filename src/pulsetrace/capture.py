"""Independent camera acquisition and sampling with bounded, latest-frame handoff."""
import queue
import threading
import time

import cv2
import numpy as np


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
        self.frame_queue = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.done = threading.Event()
        self.capture_done = threading.Event()
        self.lock = threading.Lock()
        self.preview = None
        self.error = None
        self.frames = self.dropped_samples = 0
        self.captured_frames = self.replaced_frames = 0
        self.reported_fps = self.backend = self.frame_shape = None
        self.first_capture_time = self.last_capture_time = None
        self.read_interval_total = self.read_interval_max = 0.
        self.queue_wait_total = self.queue_wait_max = 0.
        self.sampling_total = self.sampling_max = 0.
        self.age_total = self.age_max = 0.

    def __enter__(self):
        self.started = self.clock()
        self.thread = threading.Thread(target=self._sample, name='pulsetrace-sampling', daemon=True)
        self.capture_thread = threading.Thread(target=self._capture, name='pulsetrace-acquisition', daemon=True)
        self.thread.start()
        self.capture_thread.start()
        return self

    def _fail(self, exc):
        with self.lock:
            if self.error is None:
                self.error = str(exc)

    def _capture(self):
        camera = None
        try:
            camera = self.capture_factory(self.device)
            if not camera.isOpened():
                raise OSError('Cannot open camera; check its index and camera permission')
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Best effort; backend may ignore it.
            try:
                fps = float(camera.get(cv2.CAP_PROP_FPS))
                with self.lock:
                    self.reported_fps = fps if np.isfinite(fps) and fps > 0 else None
            except Exception:
                pass  # Metadata must not prevent capture.
            try:
                backend = camera.getBackendName()
                with self.lock:
                    self.backend = str(backend)
            except Exception:
                pass
            while not self.stop.is_set():
                ok, frame = camera.read()
                completed = time.perf_counter()
                timestamp = self.clock()-self.started
                if not ok:
                    if not self.stop.is_set():
                        raise OSError('Camera stopped delivering frames')
                    break
                with self.lock:
                    if self.last_capture_time is not None:
                        interval = timestamp-self.last_capture_time
                        self.read_interval_total += interval
                        self.read_interval_max = max(self.read_interval_max, interval)
                    else:
                        self.first_capture_time = timestamp
                    self.last_capture_time = timestamp
                    self.frame_shape = list(frame.shape)
                    self.captured_frames += 1
                packet = (frame, timestamp, completed)
                try:
                    self.frame_queue.put_nowait(packet)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        with self.lock:
                            self.replaced_frames += 1
                    self.frame_queue.put_nowait(packet)
        except Exception as exc:
            self._fail(exc)
        finally:
            try:
                if camera is not None:
                    camera.release()
            except Exception as exc:
                self._fail(exc)
            finally:
                self.capture_done.set()

    def _sample(self):
        try:
            while not self.stop.is_set():
                try:
                    frame, timestamp, completed = self.frame_queue.get(timeout=.05)
                except queue.Empty:
                    if self.capture_done.is_set():
                        break
                    continue
                began = time.perf_counter()
                points = self.tracker.detect(frame, timestamp)
                sample = self.sampler.sample(frame, points, timestamp)
                finished = time.perf_counter()
                with self.lock:
                    self.preview = (frame, points, timestamp, sample.background)
                    self.frames += 1
                    wait, work, age = began-completed, finished-began, finished-completed
                    self.queue_wait_total += wait
                    self.queue_wait_max = max(self.queue_wait_max, wait)
                    self.sampling_total += work
                    self.sampling_max = max(self.sampling_max, work)
                    self.age_total += age
                    self.age_max = max(self.age_max, age)
                try:
                    self.queue.put_nowait(sample)
                except queue.Full:
                    try:
                        self.queue.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        with self.lock:
                            self.dropped_samples += 1
                    self.queue.put_nowait(sample)
        except Exception as exc:
            self._fail(exc)
        finally:
            self.stop.set()
            self.done.set()

    def statistics(self):
        """Observed host timings; neither sensor exposure times nor a throughput guarantee."""
        with self.lock:
            span = None if self.first_capture_time is None else self.last_capture_time-self.first_capture_time
            def mean(total, count): return total/count if count > 0 else None
            return dict(acquired_frames=self.captured_frames, sampled_frames=self.frames,
                replaced_unsampled_frames=self.replaced_frames, dropped_sample_queue_entries=self.dropped_samples,
                pending_unsampled_frames=self.frame_queue.qsize(), reported_camera_fps=self.reported_fps,
                observed_read_fps=(self.captured_frames-1)/span if span is not None and span > 0 else None,
                backend=self.backend, latest_frame_shape=self.frame_shape,
                mean_read_interval_s=mean(self.read_interval_total,self.captured_frames-1),
                max_read_interval_s=self.read_interval_max,
                mean_sampling_queue_wait_s=mean(self.queue_wait_total,self.frames),
                max_sampling_queue_wait_s=self.queue_wait_max,
                mean_tracking_and_sampling_s=mean(self.sampling_total,self.frames),
                max_tracking_and_sampling_s=self.sampling_max,
                mean_read_to_sample_s=mean(self.age_total,self.frames), max_read_to_sample_s=self.age_max,
                timestamp_basis='Host monotonic read-completion times; sensor exposure timing unverified')

    def latest_preview(self, *, include_background=False):
        with self.lock:
            return self.preview if include_background or self.preview is None else self.preview[:3]

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=3)
        self.capture_thread.join(timeout=3)
        if self.thread.is_alive() or self.capture_thread.is_alive():
            raise OSError('Camera capture did not stop; close the camera session before restarting')
