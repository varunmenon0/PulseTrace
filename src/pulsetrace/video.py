"""Streaming OpenCV decoding with monotonic presentation timestamps."""
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np


@dataclass
class Frame:
    index: int
    time: float
    bgr: np.ndarray


class VideoReader:
    def __init__(self, path: str | Path):
        if not Path(path).is_file():
            raise ValueError(f"Video does not exist: {path}")
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            self.capture.release()
            raise ValueError(f"Cannot decode video: {path}")
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(self.fps) or self.fps <= 0:
            self.capture.release()
            raise ValueError("Video has no usable FPS metadata")
        self.timestamp_fallbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.capture.release()

    def __iter__(self):
        previous = -1.0
        index = 0
        while True:
            ok, bgr = self.capture.read()
            if not ok:
                break
            timestamp = float(self.capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not np.isfinite(timestamp) or timestamp < 0 or timestamp <= previous:
                timestamp = max(index / self.fps, previous + 1 / self.fps)
                self.timestamp_fallbacks += 1
            yield Frame(index, timestamp, bgr)
            previous = timestamp
            index += 1
