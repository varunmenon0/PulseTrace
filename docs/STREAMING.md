# Streaming replay and local webcam prototype

This implementation lives on `work/live-window-engine`, separately from `main`.
It adds a rolling measurement engine and a local camera interface. It has not
established live-camera accuracy, inference throughput, or a browser application.

## Run a local camera session

From the repository root, install the project and acquire its verified model:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/download_model.py
pulsetrace webcam --model models/face_landmarker.task
```

Allow camera access when your operating system requests it. Use `--camera 1` to
select another camera. Press **Q** or **Esc** in the preview to stop. For console
use, run `--no-preview --seconds 60`, or stop with Ctrl+C. Keep a single face in
view in steady, diffuse lighting. The preview is local and frames are not saved.

The default is fractional sampling of twelve patches, POS extraction, patch
consensus, and continuous clean-support selection. `--sampling landmarks`,
`--method green`, `--consensus zone`, and `--window-policy full` expose existing
comparisons. They do not tune the estimator to an expected heart rate.

The command writes sampled-result events to `outputs/webcam/stream.jsonl` and
a final `stream-summary.json`. These contain derived measurements and timing;
they remain local and are not tracked by Git. Use `--output` to choose a folder.

Each finalized window now includes a `quality` object, including when its BPM
is unavailable. The session configuration identifies this as
`quality_diagnostics_version: 1`. These observations do not change any gate,
threshold, selected interval, pulse estimate, or consensus decision.

- `quality.regions` reports raw motion, sampled-area-step, missing-sample, and
  optional photometric flag counts for the forehead and both cheeks. Missing
  samples can reflect an unusable sampling region as well as face-detection loss;
  the log does not claim to distinguish those causes.
- Buffered exclusion counts show the effect of the existing 0.5-second buffer.
  Raw counts cover events inside the nominal window; buffered counts can include
  an event just outside it. Causes overlap and must not be added together.
- Shared motion/loss in two parent regions excludes every region. A region can
  therefore be excluded with no raw flags of its own; the log names this cause.
- `longest_clean_interval` gives each region's longest uninterrupted clean span.
  `clean_pairs` and `longest_clean_pair` do the same for each pair of regions.
  Durations are last-sample time minus first-sample time, not frame-count/FPS.
- `clean_pair_requirement_met` reports whether a pair has at least the required
  ten clean seconds. This alone is not enough for `--window-policy full`, which
  requires clean support across the full window. The selected-policy usable
  regions and support endpoints are logged separately.
- Peak displacement, peak relative area change, and timestamp-gap counts help
  distinguish repeated small coverage disturbances from missing footage. An
  unavailable peak is `null`, never a fabricated zero or a non-JSON NaN value.

The latest finalized window's diagnostics are also included in the final summary
when that window is still retained as the current reading. `stream.jsonl` keeps
every finalized window's diagnostics even if face loss later clears the display.

For another diagnostic test, preserve the first run and use a new folder:

```bash
pulsetrace webcam --model models/face_landmarker.task --seconds 60 \
  --output outputs/webcam-test-2
```

Remain still with your face visible for the first 30 seconds before testing a
brief face disappearance. Share both JSON files from the new folder. Earlier
logs without `quality` cannot retroactively identify the per-region rejection
cause; RGB samples and geometry were not saved in those files.

## Replay a recording before testing the camera

```bash
pulsetrace replay recording.mp4 --model models/face_landmarker.task \
  --verify-batch --output outputs/replay
```

Frames are decoded and consumed sequentially using their source timestamps.
Replay is unpaced: it checks the measurement path without claiming live-camera
throughput. `--verify-batch` explicitly retains all sampled measurements to audit
against full-session batch analysis using the same tracked samples. Normal
operation retains only a bounded rolling buffer. Reference labels never enter
the estimator or parity check.

A model-free synthetic check is also available:

```bash
pulsetrace demo --profile clean --seconds 26 --patches --output outputs/stream-fixture
pulsetrace replay outputs/stream-fixture/synthetic.avi --fixture-profile clean \
  --verify-batch --output outputs/stream-replay
python scripts/benchmark_streaming.py --output outputs/streaming-benchmark
```

`--fixture-profile` uses known rendered geometry and must only be used with the
matching controlled synthetic fixture. Those sessions are marked synthetic.
The fixed [benchmark protocol](../examples/streaming/protocol.json) covers a
steady pulse, a rising pulse, a motion burst, and face loss. Synthetic results
do not measure natural-video accuracy.

The [recorded synthetic check](../examples/streaming/benchmark.json) decoded
2,700 frames. All **22 finalized window decisions** matched batch analysis on
identical samples, including four unavailable motion/face-loss windows.
Eighteen windows produced estimates. Each recording's last nominal window was
left unfinalized because the remaining look-ahead was unavailable.

| Synthetic case | Estimated / finalized windows | Mean absolute difference from injected support-average rate |
|---|---:|---:|
| Steady 72 BPM | 4/4 | 0.0009 BPM |
| Rising 72–108 BPM | 6/6 | 0.0661 BPM |
| Motion burst | 4/6 | 0.0007 BPM |
| Face loss | 4/6 | 0.0007 BPM |

These use known rendered geometry and lossless video. No camera, MediaPipe
tracking accuracy, natural-video accuracy, or live throughput is established
by these numbers. Rejected windows remain in each denominator.

## Timing and result semantics

- Nominal windows are **12 seconds**, updated every **6 seconds**.
- A window is finalized only after **0.5 seconds of motion look-ahead** arrives.
  The first reading therefore needs at least 12.5 seconds of source support
  after session start, plus capture, tracking, queueing, and computation time.
- `available_at_s` is the earliest source-time deadline. `observed_at_s` records
  the consumed sample that made finalization possible. Webcam events also have
  `emitted_at_s` (result emission time, not a measured screen-presentation time)
  and `computation_seconds`.
- The estimate describes `analysis_start_s` through `analysis_end_s`. Continuous
  mode selects at least ten uninterrupted clean seconds inside the nominal window.
- Finalized readings are immutable. Rejected windows remain unavailable rather
  than carrying forward the previous BPM. Face loss clears the display immediately;
  a face returning cannot revive a reading cleared by face loss.
- Gaps over **0.25 seconds**, camera format changes, and buffer overruns reset
  the session. A new full warm-up follows; support is never joined across resets.
- A capture stall clears the displayed value even if no new sample arrives.
  End-of-file or stopping the camera does not flush an incomplete final window.

The rolling engine retains signal/geometry samples, not video frames. Its time
buffer includes pre-window motion context and a predecessor for area-step checks.
The default hard limit is 10,000 samples; exceeding it resets rather than silently
truncating the data needed by a window. The camera worker samples independently
of window analysis and hands over at most 120 samples. Queue overflow drops the
oldest sample, records the drop count, and preserves actual timestamps so gaps
remain detectable. The preview retains only the latest frame.

Camera timestamps are monotonic frame-read completion times, not verified sensor
exposure timestamps. Camera backends may ignore the requested one-frame capture
buffer. Drops, pauses, and queue delay must be inspected on the target machine.

## What remains before a public live application

The existing offline filter is applied to completed windows. This is not a
continuously causal pulse waveform. The existing quality rules are engineering
heuristics and the previously reported real-video outliers remain unresolved.

Tests cover streaming/batch parity, look-ahead events, incomplete tails, resets,
face-loss clearing, queue limits, and capture cleanup. Camera I/O is mocked in
automated tests; an actual camera session and synchronized contact-reference
evaluation are still required. See the [live-camera development notes](LIVE_CAMERA.md)
for the accuracy work and the later browser interface.
