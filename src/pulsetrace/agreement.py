"""Observational agreement checks independent of fixture/reference BPM labels."""
import math

METHOD_AGREEMENT_TOLERANCE_BPM = 5.

def method_agreement(green_bpm, pos_bpm, *, background_bpm=None, tolerance=METHOD_AGREEMENT_TOLERANCE_BPM):
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('tolerance must be finite and positive')
    for value in (green_bpm, pos_bpm, background_bpm):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError('Estimates must be finite positive BPM or None')
    if green_bpm is None or pos_bpm is None:
        return dict(status='insufficient_estimates', difference_bpm=None,
                    shared_lighting_cue=False, background_overlap=False)
    difference = abs(green_bpm-pos_bpm)
    match_green = background_bpm is not None and abs(green_bpm-background_bpm) <= tolerance
    match_pos = background_bpm is not None and abs(pos_bpm-background_bpm) <= tolerance
    return dict(status='agreement' if difference <= tolerance else 'method_disagreement',
                difference_bpm=difference,
                shared_lighting_cue=bool(difference > tolerance and match_green and not match_pos),
                background_overlap=bool(match_green or match_pos))
