# PulseTrace

Phase 1 of a deepfake research project: a functioning facial remote
photoplethysmography (rPPG) extraction pipeline. **There is no classifier and no
real/fake verdict.** MediaPipe provides the pretrained AI face landmark model;
pulse extraction and estimation use classical signal processing.

## Diagnostics update (0.2.0)

See [DIAGNOSTICS.md](DIAGNOSTICS.md) for patch movement/shape measurements,
area and RGB artifact flags, window estimates, a video-free `diagnose` command,
and synchronized-reference evaluation. Signal extraction and thresholds remain
unchanged; diagnostics do not certify a heartbeat.

## Quick start

Use Python **3.10–3.12**, preferably 3.12, in a fresh environment:

```bash
cd pulsetrace
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
pulsetrace demo --output outputs/demo
```

Windows: use `py -3.12 -m venv .venv` and `.venv\Scripts\activate`.
The demo needs no downloaded model. It encodes a noisy synthetic 72 BPM video,
decodes it through OpenCV, samples known fixture patches, extracts POS signals,
and exports the same report format as real analysis. It is an engineering test,
not evidence of physiological accuracy or face detection performance.

On minimal Ubuntu/Debian systems, MediaPipe may require:

```bash
sudo apt-get update
sudo apt-get install libgles2 libegl1 libgl1 libglib2.0-0
```

Use only one OpenCV wheel provider in the environment. The project uses
`opencv-contrib-python` because MediaPipe declares it as a dependency; adding
`opencv-python` or `opencv-python-headless` can overwrite the shared `cv2` module.
No GUI/display is needed; plots use Matplotlib's Agg backend.

## Real-video CLI

Download the official versioned Face Landmarker model (SHA256 checked):

```bash
python scripts/download_model.py
pulsetrace analyze recording.mp4 --model models/face_landmarker.task \
  --output outputs/recording --method pos
pulsetrace analyze recording.mp4 --model models/face_landmarker.task \
  --output outputs/green --method green --max-seconds 30
```

Record one consenting person for 20–30 seconds at about 30 FPS. Keep the face
large, unobstructed, and nearly still, with stable diffuse light. Avoid filters,
heavy compression, moving shadows, screen flicker, and automatic exposure
changes. At least 10 seconds of a usable continuous region is required by default.
`--min-seconds` and `--max-gap` configure segment selection; default maximum
bridged detection gap is 0.25 seconds. Region size must be at least 30 inset pixels.
A face leaving the frame produces missing samples, not reused landmarks.

Exit code 0 means at least one region has a spectral HR candidate. Code 2 means
invalid input, no sufficient segment, or no usable HR candidate; reports are
still written when decoding succeeded and per-region analysis was attempted.
CLI estimates are **candidates**, not calibrated confidence values. The metadata
`synthetic` flag records whether the built-in fixture demo was used; it does not
classify an input video as real or synthetic.

## Outputs

| File | Contents |
| --- | --- |
| `rgb.csv` | Every decoded timestamp; per-region R/G/B means and pixel counts; missing detections are NaN with 0 pixels |
| `forehead_pulse.csv`, `left_cheek_pulse.csv`, `right_cheek_pulse.csv` | Uniform timestamps and filtered relative-amplitude waveforms for each analyzed segment |
| `*_spectrum.csv` | Welch power spectral density |
| `waveforms.png` | Regional waveforms and spectra, with candidate HR markers |
| `regions.png` | First frame with all three valid ROI masks overlaid |
| `summary.json` | Method, input timing, valid frame fractions, segments, HR candidates, warnings and failures |

Independent regions can use different longest valid segments. Compare segment
timestamps before any future spatial-coherence analysis. The plotted first and
last second can contain filter/window edge artifacts; those seconds are excluded
from spectral HR estimation.

## Modules and algorithm

| Module | Responsibility |
| --- | --- |
| `video.py` | Stream OpenCV frames; presentation timestamps with monotonic FPS fallback |
| `tracking.py` | MediaPipe Tasks VIDEO inference, millisecond timestamps, single-face acceptance |
| `regions.py` | Landmark-based forehead and cheek polygons, convex masks, boundary erosion, RGB averages |
| `pipeline.py` | Coordinate stages with injectable tracker for reproducible tests |
| `signal.py` | Segment selection, resampling, green/POS extraction, filtering, spectral estimation |
| `report.py` | Headless visualization and CSV/JSON exports |
| `synthetic.py` | Deterministic video fixture and known geometry, used exclusively in demo/tests |
| `cli.py` | `demo` and `analyze` entry points |

1. Decode BGR frames and timestamps. Use OpenCV presentation timestamps when
   monotonic; otherwise use FPS-based fallback and record its count. OpenCV may
   stop early on damaged media, so decoded frame count is not proof of completeness.
2. Track landmarks using MediaPipe's VIDEO mode. Configure up to two faces and
   reject frames unless exactly one is detected. This disables MediaPipe's
   single-face landmark smoothing. It is not an identity tracker; use one person
   throughout the clip. Cuts between people are outside current scope.
3. Build three landmark-anchored, eroded convex patches. Reject out-of-frame or
   small patches. Average their pixels in RGB order. These are geometric patches,
   not semantic skin segmentation; inspect `regions.png` for hair/occlusion.
4. For each region, select the longest valid segment, break on gaps over 0.25 s,
   interpolate only short internal gaps, and resample to the median timestamp
   cadence. Do not fill endpoints or bridge long tracking losses.
5. Extract normalized green intensity or rolling **1.6-second POS**:
   normalize RGB by temporal means, project `X=G−B` and `Y=G+B−2R`, combine
   `X + std(X)/std(Y) * Y`, subtract each window's mean, and average overlapping
   contributions. This is a documented implementation variant using overlap
   averaging; it is not a claimed exact reproduction of a published benchmark.
6. Detrend and apply a fourth-order Butterworth bandpass at 40–200 BPM using
   second-order sections and forward/backward filtering. This is offline,
   zero-phase processing, not a causal real-time filter.
7. Trim one second at each end for HR estimation. Estimate Welch PSD with up to
   10-second windows and 4× zero-padding, select the band peak, and refine it with
   log-parabolic interpolation. Zero-padding does not improve physical resolution.
8. Reject flat signals, band-edge peaks, and diffuse spectra. `peak_fraction`
   is power within ±0.15 Hz of the peak divided by in-band power. Its 0.35 cutoff
   is an engineering heuristic, not a validated physiological quality threshold.

## Tests and reproducibility

```bash
pytest -q
pulsetrace demo --bpm 96 --seconds 20 --method green --output outputs/green-demo
python -m build
```

Tests cover 48/72/120/180 BPM, both extraction methods, lighting drift, noise,
flat signals, NaNs, nonmonotonic timing, irregular sampling, short/long gaps,
Nyquist limits, ROI validity, channel ordering, missing faces, video decoding,
CLI artifacts, and the MediaPipe adapter contract. Tests do not download assets.

To run the optional actual MediaPipe integration test, set asset paths:

```bash
PULSETRACE_TEST_MODEL=models/face_landmarker.task \
PULSETRACE_TEST_PORTRAIT=/absolute/path/to/a/portrait.jpg pytest -q
```

This integration test repeats a portrait into a video with a known injected
color oscillation and small movement, and also checks a blank frame. It verifies
model execution and pipeline wiring. It does not validate natural human pulse
recovery. See `VALIDATION.md` for the checks actually performed for this release.
`requirements-tested.txt` records the environment used, while `pyproject.toml`
contains supported dependency ranges. GitHub Actions runs ordinary tests and a
synthetic demo on Python 3.12. Real model inference is an explicit optional check.
Actual model inference and the real-video CLI passed on a public portrait video
with an injected pulse signal. The installed MediaPipe native runtime also
attempted an unverified network connection during validation; see `VALIDATION.md`
before using private recordings. This release does not assert network isolation
of the upstream native runtime.

## Limits and phase 2 gate

A band-limited oscillation is not proof of a heartbeat. Real videos can have weak
or absent recoverable rPPG due to compression, skin visibility, motion, or light.
Synthetic/edited videos can preserve or fabricate pulse-like oscillations.
No detection accuracy, biometric validation, or Intel FakeCatcher-equivalent
performance is claimed. A missing pulse must not be labeled a deepfake.

Before implementing a classifier:

- Test consented real recordings against synchronized contact PPG/ECG or another
  suitable HR reference; report HR error, usable-signal coverage, and failures.
- Measure behavior across illumination, motion, skin tones, resolution, frame
  rates, and compression, including failure cases rather than only favorable clips.
- Verify ROI placement and identity continuity on real recordings.
- Evaluate spatial/temporal signal features with person/source-disjoint splits;
  never leak overlapping clips into both training and testing.

## References

- [MediaPipe Face Landmarker Python documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python)
- [Official versioned model](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task)
- Wang, W., den Brinker, A. C., Stuijk, S., & de Haan, G. (2017).
  Algorithmic principles of remote PPG. *IEEE Transactions on Biomedical
  Engineering, 64*(7), 1479–1491. [DOI](https://doi.org/10.1109/TBME.2016.2609282)
- [SciPy SOS zero-phase filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html)
- [SciPy Welch PSD](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)

The source is MIT licensed. Downloaded models and optional third-party test
portraits retain their own upstream terms; they are not bundled with this source.

## Experimental stabilization and overlay

See [STABILIZATION.md](STABILIZATION.md) for baseline/template comparison commands and limits.

See [SEGMENTS.md](SEGMENTS.md) for motion exclusions and independent usable sections.

See [PATCHES.md](PATCHES.md) for the experimental 12-patch comparison.
