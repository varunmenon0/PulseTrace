"""Experimental fractional polygon coverage; independent of the default sampler."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class WeightedMask:
    """Pixel coverage in a cropped image rectangle, with full-frame origin."""

    x: int
    y: int
    weights: np.ndarray

    @property
    def area(self):
        return float(self.weights.sum())

    def mean_rgb(self, bgr, min_area=30):
        if not np.isfinite(min_area) or min_area <= 0:
            raise ValueError("min_area must be positive")
        if self.area < min_area:
            raise ValueError("Region too small")
        h, w = self.weights.shape
        image = bgr[self.y:self.y + h, self.x:self.x + w]
        if image.shape != (h, w, 3):
            raise ValueError("Mask must fit a three-channel image")
        return np.einsum("ij,ijc->c", self.weights, image)[::-1] / self.area


def fractional_masks(shape, points, *, subdivisions=8, inset=1.):
    """Sample a float convex hull on a fixed subpixel lattice.

    Integer image coordinates are pixel centers. Each pixel's square footprint
    is sampled at subdivisions**2 evenly spaced centers. The hull is inset by
    an axis-aligned square (radius inset), the continuous analogue of a 3x3
    square erosion at inset=1. Quadrants partition those same subpixel samples,
    using the float hull's bounding-box midpoint, without overlap.
    """
    if isinstance(subdivisions, bool) or not isinstance(subdivisions, (int, np.integer)) or not 1 <= subdivisions <= 32:
        raise ValueError("subdivisions must be an integer between 1 and 32")
    if not np.isfinite(inset) or inset < 0:
        raise ValueError("inset must be finite and nonnegative")
    p = np.asarray(points, dtype=np.float32)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3 or not np.isfinite(p).all():
        raise ValueError("Need at least three finite 2D points")
    h, w = shape[:2]
    if (p < 0).any() or (p[:, 0] >= w).any() or (p[:, 1] >= h).any():
        raise ValueError("Region extends outside frame")
    hull = cv2.convexHull(p, clockwise=False).reshape(-1, 2).astype(float)
    if len(hull) < 3 or cv2.contourArea(hull.astype(np.float32)) <= 0:
        raise ValueError("Degenerate polygon")
    lo, hi = hull.min(axis=0), hull.max(axis=0)
    x0, y0 = np.maximum(0, np.floor(lo - .5).astype(int))
    x1, y1 = np.minimum([w, h], np.ceil(hi + .5).astype(int) + 1)
    s = subdivisions
    xs = x0 + (np.arange((x1 - x0) * s) + .5) / s - .5
    ys = y0 + (np.arange((y1 - y0) * s) + .5) / s - .5
    xx, yy = np.meshgrid(xs, ys)
    inside = np.ones(xx.shape, dtype=bool)
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        dx, dy = b - a
        inside &= dx * (yy - a[1]) - dy * (xx - a[0]) >= inset * (abs(dx) + abs(dy))
    left, top = xx < (lo[0] + hi[0]) / 2, yy < (lo[1] + hi[1]) / 2

    def mask(selected):
        weights = selected.reshape(y1 - y0, s, x1 - x0, s).mean(axis=(1, 3))
        return WeightedMask(int(x0), int(y0), weights)

    parent = mask(inside)
    patches = {name: mask(inside & selection) for name, selection in zip(
        ("tl", "tr", "bl", "br"),
        (left & top, ~left & top, left & ~top, ~left & ~top))}
    return parent, patches
