# Controlled synthetic-video proof of concept

PulseTrace can generate clean, face-shaped video fixtures with a known pulse
component applied only to the skin. The background, eyes, and other features
remain separate. Lossless FFV1 encoding preserves the generated 8-bit frames.
Known region geometry makes the demo reproducible without a model download.

```sh
pulsetrace demo --profile clean --bpm 83 --fps 30 --seconds 20 \
  --patches --consensus zone --output outputs/clean-demo
```

The command creates and decodes the video, extracts all twelve patches, runs
POS and green processing, and exports waveform/spectrum plots and comparison
reports. `summary.json` records the fixture settings and injected BPM;
`controlled_check.json` contains independently computed estimates and a
method-agreement diagnostic. Expected BPM is used for scoring, not candidate
selection or warning decisions.

## Fixture profiles

| Profile | Conditions |
|---|---|
| `clean` | Stable geometry and lighting, zero added pixel noise |
| `mild_noise` | Independent skin noise with standard deviation 0.25 intensity units |
| `slow_light` | Four-percent global illumination drift at 0.15 Hz |
| `periodic_light` | Five-percent global modulation at 1.8 Hz, separate from the skin pulse |

Skin pulse amplitudes are fixed at RGB (0.6, 3.0, 0.2) intensity units. Every case
uses the same analysis filters, spectral checks, and consensus rules. A fixed
corner samples background brightness; that reference contains no injected skin
pulse. The agreement diagnostic compares green, POS, and background estimates
with a fixed 5 BPM tolerance. It reports method disagreement and a shared-lighting
cue without replacing either estimator's output.

## Benchmark plan

`examples/controlled-video/protocol.json` fixes nine 20-second cases: five clean
rates (48, 72, 83, 120, 180 BPM) at 30 FPS; 72 BPM at 60 FPS; and three isolated
variation/challenge profiles at 72 BPM. The off-grid 83 BPM case exercises spectral
interpolation. Clean controls, controlled variations, and lighting challenges
are scored separately. Missing estimates remain in coverage denominators.

These are encoded synthetic video tests with known geometry, not natural-video
or MediaPipe face-detection measurements. The original `standard` demo remains
available. Artifact profiles are independent test cases rather than conditions
selected to match an expected heart rate.
