"""Deterministic engineering fixture, NOT a real physiological recording."""
import cv2
import numpy as np
from .regions import REGIONS


class SyntheticTracker:
    """Known fixture geometry. Never used for the real-video analyze command."""
    def detect(self, bgr, time):
        h,w = bgr.shape[:2]
        points = np.zeros((478,2))
        polygons = [((.35,.12),(.5,.1),(.65,.12),(.65,.27),(.5,.3),(.35,.27)),
                    ((.2,.42),(.3,.38),(.4,.42),(.4,.6),(.3,.64),(.2,.6)),
                    ((.6,.42),(.7,.38),(.8,.42),(.8,.6),(.7,.64),(.6,.6))]
        for indices, polygon in zip(REGIONS.values(), polygons):
            for index, point in zip(indices, polygon):
                points[index] = (point[0]*w, point[1]*h)
        return points


def make_video(path, *, bpm=72.0, seconds=20.0, fps=30.0, seed=7):
    if not 40 < bpm < 200 or seconds < 10 or fps < 10:
        raise ValueError("Fixture requires 40<BPM<200, >=10 seconds and >=10 FPS")
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320,240))
    if not writer.isOpened():
        raise ValueError("MJPG video encoder unavailable")
    rng = np.random.default_rng(seed)
    try:
        for index in range(round(seconds*fps)):
            t = index/fps
            pulse = np.sin(2*np.pi*bpm/60*t)
            illumination = 4*np.sin(2*np.pi*.15*t)
            rgb = np.array([160.,110.,80.]) + illumination + pulse*np.array([.6,3.,.2])
            noise = rng.normal(0, 2, (240,320,3))
            bgr = np.clip(rgb[::-1] + noise, 0,255).astype(np.uint8)
            writer.write(bgr)
    finally:
        writer.release()
