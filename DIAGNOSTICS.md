# PulseTrace 0.2: tracking diagnostics and reference evaluation

The extraction/filtering/HR algorithms and their thresholds are unchanged.
Diagnostics observe potential artifacts; they do not repair signals, identify
artifact causes, or classify videos.

## Upgrade on your Mac

Extract this updated project into a **new folder**. Keep your old recordings and
outputs. In the new `pulsetrace` folder:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```

Use your already-downloaded model by giving its absolute path. No model download
is needed if you reuse it. Keep network access disabled while processing personal
footage until the upstream MediaPipe runtime network behavior is resolved.

## Inspect existing RGB without reopening a face video

```bash
pulsetrace diagnose /absolute/path/to/old/outputs/second-pos/rgb.csv \
  --output outputs/old-recording-diagnostics
```

This runs both POS and green on 12-second windows spaced 6 seconds apart.
`--window-seconds` and `--step-seconds` change those values. Each window must
contain its requested usable duration up to one frame tolerance. Long missing
segments are not silently bridged.

Outputs: `diagnostics.json`, `diagnostics.png`, and `windows.csv`. Old CSVs provide
pixel area and RGB diagnostics; they cannot recover missing landmark positions.
A spectral peak can still be listed when the pulse estimator rejects it. Dashed
lines show **unvalidated spectral peaks**; dots show candidates accepted by the
existing spectral heuristic, not proven heartbeats. Window centers are shown on
the plot. Overlapping windows are not independent observations.

## Capture new tracking measurements from the same original video

```bash
pulsetrace analyze /absolute/path/to/recording2.mov \
  --model /absolute/path/to/models/face_landmarker.task \
  --output outputs/second-with-tracking --method pos
```

The usual signal report now also includes diagnostics for both methods, and
`tracking.png`. `rgb.csv` has extra geometry columns per region:

- Landmark polygon center in image pixels (x/y).
- Frame-to-frame center displacement divided by face scale.
- RMS change in centered polygon landmark positions divided by face scale.
- Face scale in pixels, measured between landmarks 33 and 263. The synthetic
  fixture uses patch-point extent when these eye landmarks are absent.

Motion/shape deltas reset after missing detections or gaps over 0.25 seconds.
They observe landmark behavior, not whether a person actually moved. Head pose,
expression, landmark jitter and sampling geometry can all contribute.

Heuristic flags: >10% patch-area step; >2% same-direction RGB change in at least
two channels; >0.05 face units of center displacement; >0.03 face units of shape
change; spectral peaks within 6 BPM of a filter boundary. These are **unvalidated
engineering cutoffs**. Flags never silently discard candidate windows or change
filtering. They must be calibrated on independent recordings before quality
rejection rules are introduced.

## Evaluate against a synchronized reference

Prepare a CSV with `time_s,bpm` columns from a reference device. Then:

```bash
pulsetrace evaluate outputs/second-with-tracking/rgb.csv reference.csv \
  --reference-offset 0 --output outputs/reference-check
```

The offset must be specified: **reference_time = video_time + offset**. Use 0
only if both clocks share the same origin. The evaluator compares window
candidates to median interpolated reference BPM over each analyzed segment. It
refuses extrapolation and reference gaps over 2.5 seconds. `evaluation.json`
reports MAE, RMSE, coverage, all windows, and reasons for missing comparisons.
Error averages only include available candidates; coverage must always accompany
them. No device-reference accuracy can be inferred from an expected BPM range.

## Uploaded recording

The separately packaged `recording-diagnostics` folder contains results computed
from the supplied RGB CSV, without opening the subject video. Do not commit that
folder to a public source repository. The CSV reproduces the original whole-clip
estimates; window estimates vary considerably. Observed area/color events are
consistent with contamination but cannot isolate its source. The expected
60–80 BPM range was not used for extraction, filtering, or peak selection.

## Public validation sources

- [Video Pulse Signals in Stationary and Motion Conditions, PhysioNet](https://physionet.org/content/videopulse/1.0.0/): simultaneous video-derived pulse and finger reference signals, documented timing offsets. The distributed files contain **processed pulse traces**, not raw RGB video, so they cannot validate our face tracker or POS extraction. The header does not fully specify offset sign in the text we inspected; do not guess alignment or report a synchronized benchmark before resolving it.
- [Dataset for video-based pulse detection](https://github.com/vladostan/Dataset-for-video-based-pulse-detection): public raw face videos and matched ECG files. ECG files state sampling rate. The README does not establish the exact video/ECG clock offset. This supports an exploratory tracking check, but no synchronized error metric should be claimed without verifying alignment.
- [LGI-PPGI](https://github.com/partofthestars/LGI-PPGI-DB): documented synchronized finger reference; upstream currently states video downloads are unavailable.

Downloaded reference data are not redistributed in this project. A successful
software check or an exploratory public video does not establish validated pulse
accuracy or deepfake detection performance.

## Exploratory raw-video check performed

One public resting clip (`p1_normal.MP4`) was resized to 640x360 and processed
with the unchanged POS pipeline: forehead 64.189 BPM, left cheek 63.187 BPM,
right cheek rejected. A simple whole-record lead-II ECG summary was 63.830 BPM.
This is encouraging compatibility evidence, not a synchronized accuracy score.
Video/ECG alignment is still unverified, and the ECG peak finder is exploratory.

To reproduce the software check using public data only (about 48 MB download):

```bash
python scripts/public_video_smoke.py --model /path/to/face_landmarker.task
```

This downloads SHA256-checked video/ECG files, resizes the video, runs the tracker,
and writes signal/diagnostic reports and `public_check.json`. It does not tune
filters to the reference or select a different peak to match it.
