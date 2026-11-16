# Path to camera-based estimation

The completed CLI analyzes recorded video. The next application milestone is a
camera session that uses the same measured processing rules and makes estimate
timing explicit. Presentation changes must not be reported as accuracy gains.

## Accuracy work before a camera interface

1. Audit accepted outliers against contact waveform quality and reference timing.
   Preserve the device-label benchmark and score any reviewed beat reference as a
   separate protocol. Do not optimize clock offsets against video estimates.
2. Evaluate support diagnostics such as regional agreement, spectral strength,
   and method disagreement on development recordings. Freeze a rule before using
   a fresh cohort. Report estimates rejected by the new rule as well as retained
   errors, so lower coverage cannot masquerade as improved measurement.
3. Replay recordings as timestamped incoming frames and compare completed-window
   estimates with the batch baseline. Check that later frames cannot modify a
   result that has already been finalized.

## First camera engine

Maintain a timestamped RGB/geometry buffer and run the existing estimator over
completed 12-second windows. This can preserve the recorded-video calculation
while accepting frames from a camera. Warm-up time and update intervals should
be visible in the interface. Missing detections, tab pauses, camera changes, and
long timestamp gaps must reset or invalidate the affected support.

The current quality gate uses a symmetric 0.5-second exclusion buffer. A streaming
implementation cannot know about a motion event that has not arrived yet.
Matching batch decisions therefore requires waiting for the look-ahead buffer
before finalizing a window, or separately evaluating a causal quality policy.
The current recorded-video display must not be used as a measured live-latency
benchmark.

Batch pulse filtering uses SciPy's
[forward/backward SOS filter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html).
It can run on an already collected window. A continuously updated causal waveform
is a separate implementation using filter state, such as
[sosfilt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html),
and requires new tests for startup transients, phase delay, and rate recovery.
Switching filters is not a presentation change and needs a paired real-video
evaluation.

## Application acceptance checks

- A first reading appears only after sufficient complete clean support exists.
- The displayed estimate includes the time interval it summarizes.
- Rejected or expired windows clear the last successful estimate.
- Processing and display latency are measured separately from source camera FPS.
- The streaming replay retains explicit failures and reference-invalid windows.
- The frontend is built around these estimator states after the engine passes
  replay and reference checks.
