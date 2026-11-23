"""Stateful, frame-at-a-time sampling shared by files and camera sessions."""
from dataclasses import dataclass

import numpy as np

from .regions import REGIONS, extract_regions
from .patches import PATCHES, sample_patches
from .stabilization import TemplateStabilizer


@dataclass
class Sample:
    time: float
    rgb: dict
    pixels: dict
    geometry: dict
    patch_rgb: dict
    patch_pixels: dict
    reset_reason: str | None = None
    background: dict | None = None


class FrameSampler:
    def __init__(self, *, sampling="fractional", min_pixels=30, patches=True, background_roi=None):
        if sampling not in ("landmarks", "template", "fractional"):
            raise ValueError("Unknown sampling mode")
        if min_pixels < 1:
            raise ValueError("min_pixels must be positive")
        self.sampling, self.min_pixels, self.patches = sampling, min_pixels, patches
        from .background import validate_roi
        self.background_roi=None if background_roi is None else validate_roi(background_roi)
        self.stabilizer = TemplateStabilizer()
        self.previous = {name: None for name in REGIONS}
        self.previous_time = None
        self.masks = {}
        self.landmarks = None
        self.shape = None

    def sample(self, bgr, landmarks, time):
        from .diagnostics import geometry_sample

        if not np.isfinite(time) or (self.previous_time is not None and time <= self.previous_time):
            raise ValueError("Need strictly increasing finite sample timestamps")
        changed = self.shape is not None and self.shape != bgr.shape
        from .background import sample_background
        background=None if self.background_roi is None else sample_background(
            bgr,landmarks,self.background_roi,self.min_pixels)
        if changed:
            self.previous = {name: None for name in REGIONS}
            self.stabilizer.reset()
        self.shape = bgr.shape
        if landmarks is None or (self.previous_time is not None and time-self.previous_time > .25):
            self.stabilizer.reset()
        if self.sampling == "template" and landmarks is not None:
            landmarks = self.stabilizer.apply(landmarks)
        fractional = {}
        if landmarks is None:
            values = {n: np.full(3, np.nan) for n in REGIONS}
            counts = {n: 0 for n in REGIONS}
            masks = {}
        elif self.sampling == "fractional":
            from .subpixel import extract_fractional
            values, counts, masks, fractional = extract_fractional(bgr, landmarks, self.min_pixels)
        else:
            values, counts, masks = extract_regions(bgr, landmarks, self.min_pixels)
        patch_rgb, patch_pixels = {}, {}
        if self.patches:
            samples = fractional if self.sampling == "fractional" else sample_patches(bgr, masks, self.min_pixels)
            for n in PATCHES:
                patch_rgb[n], patch_pixels[n] = samples.get(n, (np.full(3, np.nan), 0))
        scale = np.nan
        if landmarks is not None:
            scale = float(np.linalg.norm(landmarks[33]-landmarks[263]))
            if scale <= 0:
                points = landmarks[list({i for indices in REGIONS.values() for i in indices})]
                scale = float(np.linalg.norm(np.ptp(points, axis=0)))
        geometry = {}
        for name, indices in REGIONS.items():
            if name in masks:
                old = self.previous[name] if self.previous_time is not None and time-self.previous_time <= .25 else None
                geometry[name] = geometry_sample(landmarks, indices, old, scale)
                self.previous[name] = landmarks[list(indices)].copy()
            else:
                geometry[name] = np.full(5, np.nan)
                self.previous[name] = None
        self.previous_time, self.masks, self.landmarks = time, masks, landmarks
        return Sample(float(time), values, counts, geometry, patch_rgb, patch_pixels,
                      'camera_format_change' if changed else None,background)


def samples_to_extraction(samples, metadata=None):
    """Copy sampled measurements; never retain camera frames in the signal buffer."""
    from .pipeline import Extraction

    samples = list(samples)
    if not samples:
        raise ValueError("No samples")
    def stack(field):
        return {n: np.asarray([getattr(s, field)[n] for s in samples])
                for n in getattr(samples[0], field)}
    return Extraction(np.array([s.time for s in samples]), stack('rgb'), stack('pixels'),
                      None, {}, metadata or {}, stack('geometry'), stack('patch_rgb'), stack('patch_pixels'))
