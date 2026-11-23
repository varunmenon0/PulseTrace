"""Experimental independent-reference ambiguity screen; not pulse validation.

The caller must supply RGB from a separate non-skin region on exactly the same
selected timestamps as the face. A lack of overlap never establishes a pulse.
This module is deliberately not connected to live display decisions.
"""
from dataclasses import dataclass

import numpy as np

from .signal import analyze


@dataclass(frozen=True)
class LightingReference:
    status: str
    spectra: tuple = ()
    reason: str | None = None


def build_reference(time, rgb):
    """Preserve the shared final filtering/PSD path; do not bridge lost support."""
    if rgb is None:
        return LightingReference('unavailable',reason='No independent background RGB supplied')
    try:
        t,values=np.asarray(time,float),np.asarray(rgb,float)
    except (ValueError,TypeError):
        return LightingReference('unavailable',reason='Reference must contain numeric timestamps and RGB')
    if (t.ndim!=1 or values.shape!=(len(t),3) or len(t)<2 or
        not np.isfinite(t).all() or not np.isfinite(values).all() or
        not (values>0).all() or not (np.diff(t)>0).all() or np.max(np.diff(t))>.25):
        return LightingReference('unavailable',reason='Invalid or discontinuous paired reference support')
    spectra=[]
    for channel in range(3):
        try:
            result=analyze(t,values[:,[channel,channel,channel]],method='green')
        except ValueError as exc:
            return LightingReference('unavailable',reason=str(exc))
        power=result.power.copy()
        # The same absolute flat-signal limits used by signal.analyze.
        band=(result.frequencies>=40/60)&(result.frequencies<=200/60)
        if np.std(result.pulse)<1e-7 or power[band].sum()<1e-16:
            power[:]=0
        frequency=result.frequencies.copy()
        frequency.flags.writeable=False;power.flags.writeable=False
        spectra.append((frequency,power))
    return LightingReference('available',tuple(spectra))


def screen_candidate(candidate_bpm, reference):
    """Withhold overlap or unavailable reference; never move a frequency."""
    if candidate_bpm is not None and (not np.isfinite(candidate_bpm) or not 40<=candidate_bpm<=200):
        raise ValueError('Candidate must lie in the finite 40–200 BPM analysis band or be None')
    if candidate_bpm is None:
        return dict(status='no_candidate',raw_bpm=None,bpm=None,channel_power_fractions=[])
    if reference.status!='available':
        return dict(status='reference_unavailable',raw_bpm=candidate_bpm,bpm=None,
                    channel_power_fractions=[],reason=reference.reason)
    fractions=[]
    for f,power in reference.spectra:
        band=(f>=40/60)&(f<=200/60)
        near=band&(np.abs(f-candidate_bpm/60)<=.15)
        fractions.append(float(power[near].sum()/max(power[band].sum(),1e-30)))
    overlap=any(value>=.35 for value in fractions)
    return dict(status='lighting_overlap' if overlap else 'no_overlap_observed',
                raw_bpm=candidate_bpm,bpm=None if overlap else candidate_bpm,
                channel_power_fractions=fractions)
