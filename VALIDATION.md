# Motion-exclusion update (October 26, 2026)

59 tests passed, 1 optional asset-backed test skipped. Tests cover independent
segments before/after a simulated motion spike, injected 72 BPM recovery on each
side, missing-frame hard splits, area jumps and insufficient footage. Uploaded
baseline and template CSVs processed with fixed default thresholds. No natural
pulse accuracy claim or new MediaPipe inference. See SEGMENTS.md.

# Overlay/template update (October 26, 2026)

55 tests passed, 1 optional asset-backed test skipped. Added deterministic
similarity-transform/jitter/reset tests, degenerate-anchor rejection, missing-face
overlay frame-count verification and template video-to-pulse recovery (72 BPM).
The existing extraction tests still pass. No new actual MediaPipe inference or
natural-video stabilization benchmark was run for this update. The subject CSV
cannot reconstruct source frames. See STABILIZATION.md for use and limitations.
No improvement in natural pulse accuracy is claimed.

# Phase 1 validation

## Diagnostics release 0.2.0 (October 12, 2026)

- **51 tests passed, 1 optional asset-backed test skipped**. This includes the
  existing extraction tests, geometry translation/shape separation, legacy and
  new CSV compatibility, missing-frame behavior, artifact events, sliding-window
  changes, and reference alignment/coverage/gap handling.
- POS synthetic demo still reproduces the unchanged 72 BPM estimates.
- Uploaded RGB CSV was diagnosed without reopening the subject video.
  Forehead/left/right cheek had 16/4/6 flagged frames under the documented
  heuristic cutoffs. These counts are not calibrated quality measures.
  Historical CSVs lack landmark coordinates, so actual motion was not reconstructed.
- Public raw-video exploratory check ran actual MediaPipe on `p1_normal.MP4`
  from the dataset linked in DIAGNOSTICS.md, after resizing from 1920x1080 to
  640x360 and encoding MJPG at the source 25 FPS. All regions retained 100%
  valid frames. Whole-clip POS candidates: forehead 64.189 BPM, left cheek
  63.187 BPM; right cheek rejected (diffuse spectrum).
- A simple lead-II QRS-energy peak finder on the accompanying 100 Hz ECG gave
  a whole-record median RR rate of 63.830 BPM. It is an exploratory summary,
  not a validated reference pipeline. Exact video/ECG clock alignment was not
  established, and no synchronized MAE/RMSE is claimed. Checksums and results
  are in `examples/public-smoke/public_check.json`; reproduction helper is
  `scripts/public_video_smoke.py`. Raw dataset files are not bundled.
- Wheel/source builds and dependency consistency checks passed.

Extraction, POS/green algorithms, the 40–200 BPM band, and acceptance thresholds
remain unchanged. New flags are observational, not additional rejection gates.
No classifier or deepfake accuracy claim has been added. Natural pulse accuracy
across independent subjects and conditions remains unvalidated.

The earlier phase-one validation record follows for historical context.


Release: 0.1.0. Verification date: October 11, 2026.

## Completed

- Python 3.12.14, Linux x86_64; exact dependency versions in
  `requirements-tested.txt`.
- Tests: **36 passed across two runs**: 35 ordinary tests passed, then the
  optional actual-model integration test passed with explicit public test assets.
  The default suite still skips that optional test unless asset paths are set.
- Both pulse methods recover injected 48, 72, 120 and 180 BPM signals within
  2 BPM in deterministic signal tests with noise and slow lighting drift.
- Full synthetic video CLI: POS estimates 72.003, 72.012 and 72.003 BPM for a
  72 BPM injected signal. Green estimates 96.004, 96.014 and 95.994 BPM for a
  96 BPM injected signal. These tiny errors concern clean engineered fixtures,
  not natural human recordings or expected real-video performance.
- Tracking adapter contract tested for BGR-to-RGB conversion, landmark pixel
  scaling, monotonically increasing timestamps and multi-face rejection.
- Missing-face handling, invalid inputs, gap selection, interpolation, flat/noise
  rejection, export artifacts and stale-output removal tested.
- Dependency consistency checked with `pip check`; wheel and source distribution
  build successfully. Waveform/PSD plot inspected visually.
- Official model asset downloaded and SHA256 recorded in the downloader.

## Actual-model verification

The MediaPipe Face Landmarker integration test passed using the official model
and a public upstream portrait test asset. It verifies detection of 478 landmarks,
valid patches on all three regions, rejection of a blank frame, and tracking of a
12-second portrait video with small lateral motion and an injected 72 BPM color
oscillation. All regions retain more than 95% valid frames and recover the
injected rate within 3 BPM.

The actual `pulsetrace analyze` CLI was also run on that video. It exited 0,
exported the report files, and returned 71.999, 71.921 and 72.085 BPM for forehead,
left cheek and right cheek. All three regions had 100% valid frame coverage.
These are engineered signals added to a photograph, not natural pulse signals.

## Runtime network behavior and remaining limits

The initial runtime check found a missing `libGLESv2.so.2`; an isolated native
library was supplied for subsequent checks. Automatic approval review initially
blocked the model integration check after observing a `play.googleapis.com`
connection whose payload had not been verified. Following explicit user approval,
the check was retried using only the public test portrait and passed. The native
library contains analytics/logging symbols, but inspection does not establish the
complete content of outbound data. Successful inference does not establish
network isolation or resolve the upstream runtime's network behavior.

The ordinary suite never runs actual model inference or accesses the network.
The model test is optional, requires explicit asset paths, and is excluded from
the default GitHub Actions workflow. Do not use private recordings before
resolving the upstream runtime's network behavior.

No natural human recording, synchronized reference pulse data, real-video HR
error, robustness benchmark, deepfake dataset, classifier, or detection accuracy
has been evaluated. The next milestone is consented real-video signal validation.

## Reproduce

From the repository root after installation:

```bash
pytest -q
pulsetrace demo --method pos --output outputs/pos
pulsetrace demo --method green --bpm 96 --output outputs/green
python -m pip check
python -m build
```

`examples/synthetic-pos` and `examples/synthetic-green` include generated CSV,
JSON and PNG reports. Regenerate the input AVI with the commands above; fixture
videos and third-party model/portrait files are intentionally not distributed.
