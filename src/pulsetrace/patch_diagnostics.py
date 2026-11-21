"""Describe existing patch estimates without changing the estimator or vote."""
import numpy as np


def signal_detail(result):
    status = 'candidate'
    if result.bpm is None:
        status = 'no_candidate'
        for prefix, code in (('Flat/near-flat', 'flat_signal'), ('Diffuse spectrum', 'diffuse_spectrum'),
                             ('Spectral peak touches', 'band_edge')):
            if any(w.startswith(prefix) for w in result.warnings):
                status = code
                break
    band = (result.frequencies >= 40/60) & (result.frequencies <= 200/60)
    f, power = result.frequencies[band], result.power[band]
    total = float(power.sum())
    peak = float(f[np.argmax(power)]*60) if len(power) and total > 1e-16 else None
    return dict(signal_status=status, candidate_bpm=result.bpm, spectral_peak_bpm=peak,
                peak_fraction=result.peak_fraction, band_power=total,
                filtered_signal_std=float(np.std(result.pulse)), sample_rate_hz=result.sample_rate,
                analyzed_duration_s=result.duration, warnings=list(result.warnings))


def consensus_detail(decision, zones, usable, policy):
    valid = {n:v for n,v in decision['individual_candidates'].items() if v is not None}
    parents = sorted({zones[n] for n in valid})
    if decision['bpm_candidate'] is not None:
        reason = None
    elif sum(usable.values()) < 2:
        reason = 'quality_exclusion'
    elif len(valid) < 2:
        reason = 'insufficient_valid_patch_candidates'
    elif len(parents) < 2:
        reason = 'candidates_from_only_one_region'
    elif policy == 'zone':
        reason = decision.get('rejection_reason', 'no_unique_zone_majority')
    else:
        reason = 'no_unique_cross_region_majority'
    return dict(policy=policy, status='accepted' if reason is None else 'unavailable',
                rejection_reason=reason, eligible_patch_count=len(valid), eligible_regions=parents,
                eligible_candidates=valid, bpm_candidate=decision['bpm_candidate'], support=decision['support'],
                zone_candidates=decision.get('zone_candidates'),
                note='Spectral candidates and agreement are not synchronized pulse-reference measurements')
