"""Window rates from externally supplied beat times, with explicit clock mapping."""
import json
from pathlib import Path

import numpy as np


def load_peak_reference(csv_path, provenance_path, *, video_sha256):
    provenance = json.loads(Path(provenance_path).read_text())
    if provenance.get('video_sha256') != video_sha256:
        raise ValueError('Peak annotations do not identify this video hash')
    if provenance.get('time_unit') != 'seconds' or not provenance.get('source'):
        raise ValueError('Provenance must declare source and time_unit=seconds')
    data = np.genfromtxt(csv_path, delimiter=',', names=True, ndmin=1)
    if not data.dtype.names or 'time_s' not in data.dtype.names:
        raise ValueError('Peak CSV requires a time_s column')
    peaks = np.asarray(data['time_s'], dtype=float)
    if len(peaks) < 2 or not np.isfinite(peaks).all() or np.any(np.diff(peaks) <= 0):
        raise ValueError('Need finite, strictly increasing beat times')
    return peaks, provenance


def window_rate(peaks, start_s, end_s, *, reference_offset):
    """Integrate 60/RR over the full window; never extrapolate or bridge bad RR.

    Reference time = video time + reference_offset. Beats must bracket both
    window edges. Beat intervals touching the window must lie in 0.3–1.5 s,
    matching the estimator's existing 40–200 BPM range. This aggregation is not
    spectral peak picking and never consults the video's estimated pulse.
    """
    peaks = np.asarray(peaks, dtype=float)
    if peaks.ndim != 1 or len(peaks) < 2 or not np.isfinite(peaks).all() or np.any(np.diff(peaks) <= 0):
        raise ValueError('Need finite, strictly increasing beat times')
    if not np.isfinite([start_s, end_s, reference_offset]).all() or end_s <= start_s:
        raise ValueError('Invalid window or reference offset')
    start, end = start_s + reference_offset, end_s + reference_offset
    first = np.searchsorted(peaks, start, side='right') - 1
    last = np.searchsorted(peaks, end, side='left')
    if first < 0 or last >= len(peaks):
        return dict(bpm=None, warning='Beats do not bracket the complete reference window')
    left, right = peaks[first:last], peaks[first + 1:last + 1]
    rr = right - left
    if np.any(rr < .3 - 1e-10) or np.any(rr > 1.5 + 1e-10):
        return dict(bpm=None, warning='Beat interval outside 40–200 BPM; no gap bridging')
    overlap = np.maximum(0, np.minimum(right, end) - np.maximum(left, start))
    return dict(bpm=float(60 * np.sum(overlap / rr) / (end - start)), warning=None)
