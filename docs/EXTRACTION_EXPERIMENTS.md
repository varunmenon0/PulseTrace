# Paired extraction experiments

These research methods are available through a comparison script. Webcam defaults
and display decisions remain unchanged. No method is selected using a person's
usual heart rate or a manual session-average count.

## Methods and pairing

- `green` and `pos`: existing PulseTrace baselines.
- `chrom_window`: CHROM color axes (`X = 3R − 2G`,
  `Y = 1.5R + G − 1.5B`) on mean-normalized colors. Estimate the standard-deviation
  ratio from band-limited axes across the completed analysis window. This is a
  whole-window adaptation, **not** the original overlapping-window CHROM algorithm.
- `pos_bandlimited`: preserve POS's 1.6-second sliding normalization and overlap
  averaging, but estimate its balancing coefficient from band-limited color axes.
  This is a POS adaptation, not a new name for the original implementation.

Algorithm references: [de Haan and Jeanne's CHROM paper](https://pubmed.ncbi.nlm.nih.gov/23744659/),
[Idiap's CHROM guide](https://www.idiap.ch/software/bob/docs/bob/bob.rppg.base/v1.0.0/guide_chrom.html),
and the [rPPG-Toolbox POS implementation](https://github.com/ubicomplab/rPPG-Toolbox/blob/main/unsupervised_methods/methods/POS_WANG.py).
The adaptations here are implemented locally and should not be treated as a
benchmark of canonical CHROM or another toolkit.

All methods share timestamps, resampling, final fourth-order 40–200 BPM filter,
one-second edge trim, spectral calculation, and existing rejection criteria.
The adapters only replace the color-to-pulse source. Completed windows can use
zero-phase filtering; this does not provide instantaneous estimates.

## Frozen synthetic comparison

The [protocol](../examples/extraction-experiments/protocol.json) was committed as
`c140742` before running comparisons. It specifies 400 generated RGB sequences:
five pulse rates (48, 72, 100, 140, 180 BPM), two frame rates, five lighting/noise
profiles, two timing patterns, and four noise seeds. Development and held-out
seeds each contain 200 cases. Jittered timing drops indices congruent to 17 modulo
53. Expected BPM enters signal generation and scoring, never the estimator.

| Method | Development returned / 200 | Development MAE | Held-out returned / 200 | Held-out MAE | Held-out max error | Held-out errors >5 BPM |
|---|---:|---:|---:|---:|---:|---:|
| Green | 193 | 8.725 | 191 | 8.762 | 72.047 | 36 |
| POS | 180 | 9.247 | 179 | 9.344 | 72.077 | 40 |
| CHROM axes, whole window | 178 | 0.058 | 177 | 0.088 | 1.806 | 0 |
| POS, band-limited coefficient | 178 | 9.336 | 176 | 9.501 | 72.081 | 40 |

Errors are BPM and apply **only to returned readings**. Missing readings are
abstentions, not zero-error results. Report coverage alongside error.

All methods returned all clean and slow-drift cases. Green followed the imposed
1.8 Hz common lighting interference; both POS variants followed the imposed
chromatic interference. The CHROM-axis adaptation avoided those failures in
these fixed fixtures. In low-SNR held-out cases, however, it returned only 17/40
readings, compared with green's 31/40 and POS's 19/40.

These are RGB means with one base color, one pulse color direction, and fixed
interference directions/frequencies. They contain no encoded video, skin
diversity, facial motion, camera auto-exposure, or tracking errors. Held-out seeds
test new noise realizations within these conditions, not new populations or
lighting families. Low synthetic error does **not** establish camera accuracy.
The coefficient-only POS variant provides no convincing improvement here.

## Expanded color and pulse-absent challenge

The follow-up [stress protocol](../examples/extraction-experiments/stress-protocol.json)
was committed as `d8c3fe8` before execution. The extraction methods were unchanged.
The full grid contains 576 pulse-present cases: three base colors, three relative
pulse color directions, four injected rates (48, 84, 126, 174 BPM), two frame
rates, four lighting profiles, and two seeds. Every case has timing jitter and
frame drops. Sixty separate controls have **no injected pulse**: five conditions,
each across three base colors, two frame rates, and two seeds. These are
post-initial-study stress cases, not a clinical holdout or a skin-tone model.

| Method | Returned / 576 pulse cases | MAE of returned readings (BPM) | Errors >5 BPM | Largest error (BPM) |
|---|---:|---:|---:|---:|
| Green | 576 | 31.998 | 324 | 120.008 |
| POS | 576 | 21.044 | 216 | 78.023 |
| CHROM axes, whole window | 489 | 11.788 | 90 | 120.048 |
| POS, band-limited coefficient | 576 | 21.069 | 216 | 78.023 |

All four methods returned readings in the same 489 cases. On this common set,
MAE was 37.684 BPM for green, 24.778 for POS, 11.788 for CHROM axes, and 24.799
for the POS variant. This paired comparison avoids interpreting differing
accepted sets as equivalent coverage.

The CHROM-axis variant returned only **63/144 clean cases**, versus 144/144 for
each other method. It returned all 144 two-light cases, but 90 exceeded 5 BPM
error, with 39.672 BPM MAE. Its earlier near-zero error did not generalize to the
expanded directions and lighting. The axes can subtract away a single pulse
component when the projected components have the same sign; these arbitrary
color challenges expose that limitation without establishing its prevalence
in natural video.

No-pulse controls are scored as spurious candidates, never as BPM error against
zero. Each cell below is candidates returned / 12 controls:

| Pulse-absent condition | Green | POS | CHROM axes | POS variant |
|---|---:|---:|---:|---:|
| Flat | 0/12 | 0/12 | 0/12 | 0/12 |
| Noise only | 0/12 | 0/12 | 0/12 | 0/12 |
| Common periodic light | 12/12 | 0/12 | 0/12 | 0/12 |
| Colored periodic light | 12/12 | 12/12 | 0/12 | 12/12 |
| Two periodic lights | 12/12 | 12/12 | 12/12 | 12/12 |

These are individual RGB-trace extraction results, not an evaluation of the
complete webcam display, region consensus, or disagreement policy. They show
that spectral concentration alone accepts periodic lighting artifacts. No
threshold, method, or fallback was changed after seeing the results, and neither
experimental method is promoted to live use.

## Reproduce

From the repository root, after installing the project:

```sh
python scripts/compare_extraction.py --output outputs/extraction-experiments
```

`synthetic-benchmark.json` contains every case, abstention, input checksum,
development/held-out metrics by profile, protocol checksum, source checksums,
and package versions. Generated results remain local.

Run the expanded challenge separately:

```sh
python scripts/compare_extraction.py --suite stress --output outputs/extraction-stress
```

`stress-benchmark.json` separates pulse-present errors from pulse-absent
spurious-candidate counts, includes the common accepted set, and breaks down
pulse cases by lighting profile and pulse color direction. The original suite
and its results are preserved. Selecting a protocol for the wrong suite fails
before writing results.

Optionally compare an existing private sample archive without opening the camera:

```sh
python scripts/compare_extraction.py \
  --samples outputs/webcam-test-5/samples.jsonl \
  --output outputs/extraction-experiments
```

This adds `private-session-comparison.json` with patch spectra acceptance,
quality-gated votes, and support. It uses identical saved frames' measurements,
motion exclusions, selected intervals, and consensus rules for all four methods.
It checks that both baseline votes and patch support match the original batch
comparison exactly. It supports patch consensus, 12-second windows, 6-second
steps, 0.5-second look-ahead, 0.25-second maximum gaps, and no session resets;
incompatible archives are rejected. It does not apply a new display policy or
score a manual average against individual windows.

Two saved webcam development sessions were compared privately. Candidate counts
changed in opposite directions across sessions. More accepted windows alone
cannot establish accuracy, so neither adaptation has been promoted into the
webcam command. Next validation needs additional color/lighting families and
natural video with synchronized independent reference measurements, using the
same frames and exclusions across methods. See the
[reference protocol](REFERENCE_PROTOCOL.md).
