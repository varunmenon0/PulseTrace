"""Bounded rolling-window pulse engine with explicit motion look-ahead.

Final readings describe complete recorded support, not instantaneous pulse.
The engine owns its samples and keeps no recording or growing result history.
"""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass

import numpy as np

from .regional_quality import build_regional_comparison
from .regions import REGIONS
from .sampling import samples_to_extraction


@dataclass(frozen=True)
class Reading:
    session: int
    start_s: float
    end_s: float
    available_at_s: float
    observed_at_s: float
    analysis_start_s: float | None
    analysis_end_s: float | None
    bpm: float | None
    status: str
    unavailable_reason: str | None
    support: tuple

    def to_dict(self):
        return {"type": "window", **asdict(self)}


class PulseStream:
    window_seconds = 12.
    step_seconds = 6.
    lookahead_seconds = .5
    max_gap = .25

    def __init__(self, *, method="pos", consensus="patch", window_policy="continuous", max_samples=10000):
        if method not in ('pos', 'green') or consensus not in ('patch', 'zone') or window_policy not in ('full', 'continuous'):
            raise ValueError("Unknown stream configuration")
        if not isinstance(max_samples, int) or isinstance(max_samples, bool) or max_samples < 2:
            raise ValueError("max_samples must be an integer >=2")
        self.method, self.consensus, self.window_policy = method, consensus, window_policy
        self.max_samples = max_samples
        self.samples = deque()
        self.latest = None
        self.last_time = None
        self.origin = None
        self.effective_step = self.step_seconds
        self.window_index = 0
        self.session = 0
        self.resets = 0
        self.last_reset_reason = None
        self.finalized_windows = 0
        self.estimated_windows = 0
        self.face_available = False

    def reset(self, reason="session_reset"):
        self.samples.clear()
        self.latest, self.origin = None, None
        self.window_index = 0
        self.session += 1
        self.resets += 1
        self.last_reset_reason = reason
        self.face_available = False

    @property
    def next_start(self):
        return None if self.origin is None else self.origin+self.window_index*self.effective_step

    def push(self, sample):
        t = sample.time
        if not np.isfinite(t) or (self.last_time is not None and t <= self.last_time):
            raise ValueError("Stream timestamps must be finite and strictly increasing")
        # Validate the schema before changing state; missing samples use NaNs/zero counts.
        for n in REGIONS:
            if np.shape(sample.rgb[n]) != (3,) or np.shape(sample.geometry[n]) != (5,):
                raise ValueError("Invalid regional sample shape")
            if not np.isfinite(sample.pixels[n]) or sample.pixels[n] < 0:
                raise ValueError("Invalid sampled area")
        from .patches import PATCHES
        for n in PATCHES:
            if np.shape(sample.patch_rgb[n]) != (3,):
                raise ValueError("Streaming requires twelve-patch samples")
        if sample.reset_reason is not None:
            self.reset(sample.reset_reason)
        elif self.last_time is not None and t-self.last_time > self.max_gap:
            self.reset('timestamp_gap')
        if len(self.samples) >= self.max_samples:
            self.reset('buffer_capacity')
        if self.origin is None:
            self.origin = t
            # Match NumPy arange's effective step in the historical batch schedule.
            self.effective_step = (t+self.step_seconds)-t
        self.last_time = t
        self.samples.append(deepcopy(sample))
        self.face_available = sum(sample.pixels[n] > 0 and np.isfinite(sample.rgb[n]).all()
                                  and (sample.rgb[n] > 0).all() for n in REGIONS) >= 2
        if not self.face_available:
            self.latest = None
        readings = []
        while t+1e-9 >= self.next_start+self.window_seconds+self.lookahead_seconds:
            start = self.next_start
            report = build_regional_comparison(samples_to_extraction(self.samples),
                consensus_policy=self.consensus, window_policy=self.window_policy, window_starts=[start])
            row = report['windows'][0]
            decision = row['methods'][self.method]['twelve_patches']['regional_gate']
            bpm = decision['bpm_candidate']
            reason = None if bpm is not None else ('quality_exclusion' if sum(row['usable_regions'].values()) < 2
                                                  else 'insufficient_pulse_support')
            chosen = [s.time for s in self.samples if start <= s.time < start+self.window_seconds]
            analysis_start = row.get('analysis_start_s', chosen[0] if chosen else None)
            analysis_end = row.get('analysis_end_s', chosen[-1] if chosen else None)
            reading = Reading(self.session, start, start+self.window_seconds,
                start+self.window_seconds+self.lookahead_seconds, t, analysis_start, analysis_end,
                bpm, 'estimate' if bpm is not None else 'unavailable', reason, tuple(decision['support']))
            self.latest = reading
            readings.append(reading)
            self.finalized_windows += 1
            self.estimated_windows += bpm is not None
            self.window_index += 1
        if not self.face_available:
            self.latest = None
        # Keep pre-window motion context AND a predecessor for area-step detection.
        cutoff = self.next_start-self.lookahead_seconds-self.max_gap
        while len(self.samples) > 1 and self.samples[1].time < cutoff:
            self.samples.popleft()
        return readings

    def state(self, now=None):
        """Clear stale or face-lost readings, including when capture stops delivering."""
        if self.last_time is None:
            status = 'measuring'
        elif now is not None and now-self.last_time > self.max_gap:
            status = 'capture_stalled'
        elif not self.face_available:
            status = 'waiting_for_face'
        elif self.latest is None:
            status = 'measuring'
        else:
            status = self.latest.status
        return dict(status=status, bpm=self.latest.bpm if status == 'estimate' else None,
                    session=self.session, buffered_samples=len(self.samples), resets=self.resets,
                    reset_reason=self.last_reset_reason,
                    next_available_at_s=None if self.next_start is None else self.next_start+12.5,
                    latest_window=None if self.latest is None else self.latest.to_dict())
