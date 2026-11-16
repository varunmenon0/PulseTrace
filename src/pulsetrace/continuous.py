"""Select a clean continuous interval using quality masks, never pulse values."""
from itertools import combinations

import numpy as np


def select_interval(time, masks, chosen, *, min_seconds=10., max_gap=.25):
    """Longest contiguous support shared by at least two complete parent zones.

    Never join separated frames, interpolate excluded samples, or choose support
    based on estimated pulse. Ties favor more usable parents, then earlier time.
    """
    t = np.asarray(time)
    if not np.isfinite([min_seconds, max_gap]).all() or min_seconds <= 0 or max_gap <= 0:
        raise ValueError('Need positive finite duration and gap limits')
    if t.ndim != 1 or len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Need finite increasing timestamps')
    if np.shape(chosen) != t.shape or any(np.shape(m) != t.shape for m in masks.values()):
        raise ValueError('Quality masks and window must match timestamps')
    candidates = []
    for a, b in combinations(sorted(masks), 2):
        good = np.flatnonzero(chosen & ~masks[a] & ~masks[b])
        if not len(good):
            continue
        chunks = np.split(good, np.flatnonzero((np.diff(good) > 1) | (np.diff(t[good]) > max_gap)) + 1)
        for indices in chunks:
            duration = float(t[indices[-1]]-t[indices[0]])
            if duration + 1e-9 < min_seconds:
                continue
            usable = {n: not bool(mask[indices].any()) for n, mask in masks.items()}
            candidates.append((duration, sum(usable.values()), -float(t[indices[0]]), indices, usable))
    if not candidates:
        return np.array([], dtype=int), {n: False for n in masks}
    best = max(candidates, key=lambda c: c[:3])
    return best[3], best[4]
