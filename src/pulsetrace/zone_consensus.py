"""Hierarchical consensus: establish patch support within zones, then one vote per zone."""
import math

import numpy as np


def _majority_group(values, tolerance, minimum=2):
    valid = sorted((value, name) for name, value in values.items() if value is not None)
    groups = [[name for value, name in valid[i:] if value <= low + tolerance]
              for i, (low, _) in enumerate(valid)]
    groups = [group for group in groups if len(group) >= minimum and len(group) > len(valid) / 2]
    groups.sort(key=len, reverse=True)
    if not groups or (len(groups) > 1 and len(groups[0]) == len(groups[1])):
        return []
    return groups[0]


def hierarchical_consensus(candidates, zones, tolerance=5.):
    """Require two supported patches per zone, then two agreeing zone votes.

    Each level requires a unique largest cluster spanning at most tolerance BPM
    and containing a strict majority of its available candidates. Missing or
    quality-excluded patches remain None. Each accepted zone contributes its
    supported-patch median exactly once to the final vote.
    """
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('tolerance must be finite and positive')
    if set(candidates) - set(zones):
        raise ValueError('Every candidate needs a parent-zone mapping')
    for value in candidates.values():
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError('Candidates must be positive finite BPM values or None')
    details = {}
    for zone in sorted(set(zones.values())):
        values = {name: candidates.get(name) for name in zones if zones[name] == zone}
        count = sum(value is not None for value in values.values())
        group = _majority_group(values, tolerance)
        bpm = float(np.median([values[name] for name in group])) if group else None
        details[zone] = dict(bpm_candidate=bpm, support=group, valid_patches=count,
                             status='accepted' if group else 'insufficient_patches' if count < 2 else 'no_unique_majority')
    zone_values = {zone: detail['bpm_candidate'] for zone, detail in details.items()}
    winning = _majority_group(zone_values, tolerance)
    count = sum(value is not None for value in zone_values.values())
    return dict(bpm_candidate=float(np.median([zone_values[z] for z in winning])) if winning else None,
                support=[name for zone in winning for name in details[zone]['support']],
                supporting_zones=winning, zone_candidates=details, accepted_zone_count=count,
                rejection_reason=None if winning else 'insufficient_zone_support' if count < 2 else 'zone_disagreement')
