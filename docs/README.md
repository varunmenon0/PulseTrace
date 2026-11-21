# PulseTrace documentation

Run the project using the [main README](../README.md). Commands in these guides
are run from the repository root. Historical findings retain their original
settings and results; see each protocol before comparing scores.

## Evaluation and reproduction

| Guide | Contents |
|---|---|
| [Real-video demonstration](PUBLIC_DEMONSTRATION.md) | Demo reproduction, selection rule, and frozen five-recording evaluation |
| [Real-video sampling and recovery](REAL_VIDEO_RECOVERY.md) | Paired sampling results and continuous-window analysis |
| [Controlled synthetic videos](CONTROLLED_VIDEO.md) | Known pulse fixtures and lighting challenges |
| [Windowed pulse tracking](PULSE_TRENDS.md) | Changing-rate signals and quality-gated trends |
| [Motion recovery](MOTION_RECOVERY.md) | Motion exclusions and recovery checks |
| [Face-loss recovery](TRACKING_LOSS.md) | Missing-face intervals and unavailable estimates |
| [Reference protocol](REFERENCE_PROTOCOL.md) | Reference provenance, clock offsets, and beat-time scoring |

## Development and design

- [Streaming prototype](STREAMING.md): branch-only replay engine and local webcam command.
- [Extraction experiments](EXTRACTION_EXPERIMENTS.md): fixed color-projection variants, paired synthetic results, and saved-session comparisons.
- [Diagnostics](DIAGNOSTICS.md): inspect signals, geometry, and quality decisions.
- [Demo design](DEMO_DESIGN.md): visual research and presentation choices.
- [Live-camera development](LIVE_CAMERA.md): accuracy, buffering, and timing requirements.
- [Research archive](archive/README.md): earlier experiments and validation history.

Protocols, source checksums, and measured results remain in
[`examples/`](../examples/). Some are used directly by tests and benchmark scripts.
Raw recordings and downloaded model files stay outside version control.
