"""Landmark-anchored convex skin patches excluding eyes and mouth."""
import cv2
import numpy as np

REGIONS = {
    "forehead": (109, 10, 338, 337, 151, 108),
    "left_cheek": (50, 101, 205, 187, 147, 123),
    "right_cheek": (280, 330, 425, 411, 376, 352),
}


def region_mask(shape: tuple, landmarks: np.ndarray, indices: tuple,
                min_pixels: int = 30) -> np.ndarray:
    if min_pixels < 1:
        raise ValueError("min_pixels must be positive")
    points = np.asarray(landmarks)[list(indices)]
    if not np.isfinite(points).all():
        raise ValueError("Non-finite face landmarks")
    h, w = shape[:2]
    # Out-of-frame patches are rejected; clipping can change the sampled tissue.
    if (points[:, 0] < 0).any() or (points[:, 0] >= w).any() or (points[:, 1] < 0).any() or (points[:, 1] >= h).any():
        raise ValueError("Region extends outside frame")
    hull = cv2.convexHull(np.rint(points).astype(np.int32))
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(mask, hull, 255)
    # Inset boundary to reduce contamination at patch edges.
    mask = cv2.erode(mask, np.ones((3, 3), dtype=np.uint8))
    if np.count_nonzero(mask) < min_pixels:
        raise ValueError("Region too small")
    return mask


def mean_rgb(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if mask.shape != bgr.shape[:2] or not np.any(mask):
        raise ValueError("Mask must match image and contain pixels")
    return bgr[mask > 0].mean(axis=0)[::-1]  # OpenCV BGR -> RGB


def extract_regions(bgr, landmarks, min_pixels=30):
    values, counts, masks = {}, {}, {}
    for name, indices in REGIONS.items():
        try:
            mask = region_mask(bgr.shape, landmarks, indices, min_pixels)
        except ValueError:
            values[name], counts[name] = np.full(3, np.nan), 0
        else:
            values[name], counts[name], masks[name] = mean_rgb(bgr, mask), int(np.count_nonzero(mask)), mask
    return values, counts, masks
