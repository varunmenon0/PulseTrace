# Windowed pulse tracking

PulseTrace can export a pulse-rate curve from overlapping, quality-gated windows.
The new `--track` option uses twelve patches, the selected consensus policy,
12-second windows and six-second steps. Each row records both its center and the
time when its complete window is available. This is offline windowed analysis.

```sh
pulsetrace demo --profile clean --bpm 72 --end-bpm 108 --seconds 60 \
  --patches --consensus zone --track --output outputs/rising-pulse
```

`--end-bpm` adds a phase-continuous linear rate ramp to controlled synthetic
profiles. The instantaneous rate changes linearly; the rendered sine phase is
the integral of that rate. Omitting `--end-bpm` preserves the original constant
fixture behavior. The existing standard demo remains available.

For a supplied video:

```sh
pulsetrace analyze recording.mp4 --model models/face_landmarker.task \
  --patches --consensus zone --track --output outputs/pulse-trend
```

The command preserves normal regional and patch reports and adds:

| Output | Contents |
|---|---|
| `pulse_trend.csv` | Window bounds, center, availability time, green/POS estimates |
| `pulse_trend.json` | Quality-gated estimates, supporting patches/zones, coverage |
| `pulse_trend.png` | Both pulse-rate curves with missing estimates shown as gaps |

Tracking reuses the existing regional-window comparison rather than introducing
another filter or candidate selector. It respects `--max-gap`, regional quality
exclusions, and the chosen patch/zone consensus. Expected fixture rates are not
inputs to the tracking function. Rejected windows remain in the output and in
coverage denominators; there is no fill across missing estimates. Exit status
in tracking mode reflects availability of the selected method's window estimates.

## Fixed controlled benchmark

`examples/pulse-trends/protocol.json` defines rising 72–108 BPM and falling
120–72 BPM cases at 30 FPS over sixty seconds, plus a constant 83 BPM control at
60 FPS over twenty-four seconds. These use the clean, lossless synthetic renderer
and known geometry. All rate, sampling, filtering, and window settings are fixed
before scoring the suite.

The reference for a linear ramp is its analytic mean rate across each full
window, equivalent to the rate at the window center. This reference is computed
only after tracking. Output centers are not claims of instantaneous or causal
measurement; each estimate uses its complete twelve-second window.
