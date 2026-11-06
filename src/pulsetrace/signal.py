"""Gap-aware resampling, green/POS extraction, bandpass and Welch HR."""
from dataclasses import dataclass
import numpy as np
from scipy import signal


@dataclass
class PulseResult:
    time: np.ndarray
    pulse: np.ndarray
    frequencies: np.ndarray
    power: np.ndarray
    bpm: float | None
    peak_fraction: float
    sample_rate: float
    duration: float
    interpolated_fraction: float
    warnings: list[str]


def prepare_series(time, rgb, *, min_seconds=10.0, max_gap=0.25):
    time, rgb = np.asarray(time, float), np.asarray(rgb, float)
    if time.ndim != 1 or rgb.shape != (len(time), 3) or len(time) < 2:
        raise ValueError("Expected timestamps (N,) and RGB (N,3)")
    if not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError("Timestamps must be finite and strictly increasing")
    if not np.isfinite([min_seconds, max_gap]).all() or min_seconds <= 0 or max_gap <= 0:
        raise ValueError("Duration and gap limits must be positive")
    valid = np.flatnonzero(np.isfinite(rgb).all(axis=1) & (rgb > 0).all(axis=1))
    if len(valid) < 2:
        raise ValueError("No usable RGB segment")
    # Break at long timestamp gaps, including missing detections.
    splits = np.flatnonzero(np.diff(time[valid]) > max_gap) + 1
    chunks = np.split(valid, splits)
    segment = max(chunks, key=lambda c: time[c[-1]] - time[c[0]])
    duration = time[segment[-1]] - time[segment[0]]
    if duration < min_seconds:
        raise ValueError(f"Longest usable segment is {duration:.2f}s; need {min_seconds:g}s")
    dt = float(np.median(np.diff(time)))
    fs = 1 / dt
    grid = time[segment[0]] + np.arange(int(np.floor(duration * fs)) + 1) / fs
    uniform = np.column_stack([np.interp(grid, time[segment], rgb[segment, i]) for i in range(3)])
    index_span = segment[-1] - segment[0] + 1
    missing = 1 - len(segment) / index_span
    warnings = []
    if len(chunks) > 1 or segment[0] > 0 or segment[-1] < len(time) - 1:
        warnings.append("Analysis uses only the longest usable tracking segment")
    if missing > 0:
        warnings.append(f"Interpolated {missing:.1%} missing RGB frames within segment")
    if np.std(np.diff(time)) / dt > 0.05:
        warnings.append("Irregular timestamps resampled onto a uniform grid")
    return grid, uniform, fs, missing, warnings


def pulse_source(rgb, fs, method="pos"):
    if method == "green":
        return rgb[:, 1] / np.mean(rgb[:, 1]) - 1
    if method != "pos":
        raise ValueError("method must be green or pos")
    window = max(3, int(round(1.6 * fs)))
    if len(rgb) < window:
        raise ValueError("Too few samples for POS window")
    output, weight = np.zeros(len(rgb)), np.zeros(len(rgb))
    for start in range(len(rgb) - window + 1):
        patch = rgb[start:start + window]
        normalized = patch / patch.mean(axis=0) - 1
        x = normalized[:, 1] - normalized[:, 2]
        y = normalized[:, 1] + normalized[:, 2] - 2 * normalized[:, 0]
        s = x + (np.std(x) / max(np.std(y), 1e-12)) * y
        output[start:start + window] += s - s.mean()
        weight[start:start + window] += 1
    return output / np.maximum(weight, 1)


def analyze(time, rgb, *, method="pos", low_bpm=40.0, high_bpm=200.0,
            min_seconds=10.0, max_gap=0.25):
    grid, uniform, fs, missing, warnings = prepare_series(
        time, rgb, min_seconds=min_seconds, max_gap=max_gap)
    if not 0 < low_bpm < high_bpm < fs * 30:
        raise ValueError("Heart-rate band must be positive, ordered and below Nyquist")
    raw = signal.detrend(pulse_source(uniform, fs, method))
    sos = signal.butter(4, [low_bpm / 60, high_bpm / 60], btype="bandpass", fs=fs, output="sos")
    try:
        pulse = signal.sosfiltfilt(sos, raw)
    except ValueError as exc:
        raise ValueError("Segment too short for zero-phase bandpass") from exc
    # Remove edge transients from HR analysis; keep complete waveform for inspection.
    trim = int(fs)
    central = pulse[trim:-trim]
    if len(central) < 8:
        raise ValueError("Too few samples after trimming filter edges")
    nperseg = min(len(central), max(8, int(10 * fs)))
    frequencies, power = signal.welch(central, fs=fs, nperseg=nperseg,
                                      nfft=max(nperseg, 4 * nperseg))
    band = (frequencies >= low_bpm / 60) & (frequencies <= high_bpm / 60)
    f, p = frequencies[band], power[band]
    peak = int(np.argmax(p))
    # Interpolate log PSD peak without implying resolution beyond window length.
    peak_hz = f[peak]
    if 0 < peak < len(p) - 1 and np.all(p[peak-1:peak+2] > 0):
        a, b, c = np.log(p[peak-1:peak+2])
        denominator = a - 2*b + c
        if abs(denominator) > 1e-12:
            peak_hz += np.clip(0.5 * (a-c) / denominator, -0.5, 0.5) * (f[1]-f[0])
    fraction = float(p[np.abs(f - peak_hz) <= 0.15].sum() / max(p.sum(), 1e-30))
    bpm = float(60 * peak_hz)
    if np.std(pulse) < 1e-7 or p.sum() < 1e-16:
        bpm = None
        warnings.append("Flat/near-flat signal: no usable pulse estimate")
    elif fraction < 0.35:
        bpm = None
        warnings.append("Diffuse spectrum: no usable pulse estimate")
    elif peak == 0 or peak == len(p) - 1:
        bpm = None
        warnings.append("Spectral peak touches band boundary: no usable pulse estimate")
    if bpm is not None:
        warnings.append("Spectral HR candidate only; motion or lighting may mimic a pulse")
    return PulseResult(grid, pulse, frequencies, power, bpm, fraction, fs,
                       float(grid[-1]-grid[0]), missing, warnings)
