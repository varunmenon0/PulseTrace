"""Observations of existing quality decisions; never used to select estimates."""
from itertools import combinations

import numpy as np


def longest_interval(time, good, max_gap):
    indices = np.flatnonzero(good)
    if not len(indices):
        return dict(start_s=None, end_s=None, duration_s=0., samples=0)
    chunks = np.split(indices, np.flatnonzero((np.diff(indices) > 1) |
                                            (np.diff(time[indices]) > max_gap))+1)
    best = max(chunks, key=lambda c: (float(time[c[-1]]-time[c[0]]), -float(time[c[0]])))
    return dict(start_s=float(time[best[0]]), end_s=float(time[best[-1]]),
                duration_s=float(time[best[-1]]-time[best[0]]), samples=len(best))


def finite_max(values):
    finite = values[np.isfinite(values)]
    return float(finite.max()) if len(finite) else None


def window_quality(extraction, nominal, masks, shared, details, *, min_seconds, max_gap):
    t = extraction.time
    count = int(nominal.sum())
    times = t[nominal]
    regions = {}
    for name, mask in masks.items():
        raw = details['raw'][name]
        raw_counts = {cause: int(raw[cause][nominal].sum()) for cause in details['buffered'][name]}
        buffered_counts = {cause: int(flags[nominal].sum())
                           for cause, flags in details['buffered'][name].items()}
        causes = [cause for cause, n in buffered_counts.items() if n]
        if shared[nominal].any():
            causes.append('shared_motion_or_loss')
        regions[name] = dict(raw_flagged_samples=raw_counts, buffered_excluded_samples=buffered_counts,
            excluded_samples=int(mask[nominal].sum()),
            excluded_fraction=float(mask[nominal].mean()) if count else None,
            exclusion_causes=causes,
            peak_displacement_face_units=finite_max(raw['displacement'][nominal]),
            peak_area_step_fraction=finite_max(raw['area_change_fraction'][nominal]),
            longest_clean_interval=longest_interval(t, nominal & ~mask, max_gap))
    pairs = []
    for a, b in combinations(sorted(masks), 2):
        pairs.append(dict(regions=[a, b], **longest_interval(t, nominal & ~masks[a] & ~masks[b], max_gap)))
    best = max(pairs, key=lambda p: p['duration_s'])
    return dict(threshold_status='Unvalidated engineering heuristics', thresholds=details['thresholds'],
        nominal_samples=count, largest_sample_gap_s=float(np.max(np.diff(times))) if len(times) > 1 else None,
        sample_gaps_over_limit=int(np.sum(np.diff(times) > max_gap)),
        shared_raw_flagged_samples=int(details['shared_raw'][nominal].sum()),
        shared_buffered_excluded_samples=int(shared[nominal].sum()),
        minimum_continuous_seconds=min_seconds,
        clean_pair_requirement_met=bool(best['samples'] and best['duration_s']+1e-9 >= min_seconds),
        longest_clean_pair=best, clean_pairs=pairs, regions=regions,
        note='Raw counts cover the nominal window; buffered counts include effects from surrounding samples. '
             'Causes overlap and must not be summed. Missing samples do not uniquely identify face-detection loss.')
