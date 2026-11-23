# Experimental background-light ambiguity screen

`pulsetrace.lighting` adds an independent-reference screen for research. It does
not change webcam estimates, replay results, face extraction, or consensus.
It never corrects a candidate toward an expected pulse rate.

Background signals have been used to address illumination in
[Li et al., CVPR 2014](https://openaccess.thecvf.com/content_cvpr_2014/papers/Li_Remote_Heart_Rate_2014_CVPR_paper.pdf).
The screen here is a local engineering experiment, not a reproduction of their
illumination-rectification algorithm or evidence of comparable performance.

## What it observes

The caller supplies independent non-skin RGB measurements on exactly the same
selected timestamps as the face. Each background channel passes through the
existing green-channel filtering/PSD path independently, using the same 40–200
BPM band, fourth-order filter, resampling, and edge trim. Multiple channels can
expose different light frequencies. No background pulse candidate is required.

For a face candidate, the screen measures background band power within ±0.15 Hz
of that frequency. If any channel has at least 35% of its band power there, it
withholds the candidate as `lighting_overlap`. The width and threshold reuse the
existing spectral-concentration settings; they are unvalidated heuristics.
Absolute flat-signal checks also match the existing signal analyzer.

Other states distinguish `no_candidate`, `reference_unavailable`, and
`no_overlap_observed`. A missing or invalid reference withholds an existing
candidate in this experimental policy. Flat background data are available but
have zero spectral power. Missing values, discontinuities over 0.25 seconds,
insufficient duration, and mismatched array lengths make the reference
unavailable. Lost support is not bridged or silently shortened.

Every decision retains the original candidate and channel power fractions.
The screen only withholds; it never substitutes a background frequency, changes
the face waveform, or estimates a new rate.

**A match is ambiguity, not proof of lighting. No match is not proof of pulse.**
Lighting may affect the face without affecting the background. A background ROI
may contain skin, moving objects, displays, or a different lighting mixture.
A real pulse can coincide with a light frequency. These conditions defeat or
over-trigger the screen.

## Fixed synthetic experiment

The [protocol](../examples/extraction-experiments/lighting-protocol.json) was
committed as `700f1b4` before evaluation. Methods and thresholds were held fixed.
It uses 232 distinct face signals: 192 pulse-present signals and 40 pulse-absent
controls. Each face signal is shared across all methods and four reference
conditions, producing 928 paired comparison rows. The background has different
base colors and colored-light response from the face, and independently seeded
noise. These are generated RGB means, not video or natural measurements.

The injected rates are 60, 102, and 138 BPM; lighting is 0.8 and 2.3 Hz. The 138
BPM pulse deliberately coincides with the colored light. Each experiment
preserves both raw and screened results. Correct means within 5 BPM of the
injected synthetic rate; no-pulse controls are scored separately, never against
zero BPM. The reference normally has no pulse component; only the deliberately
invalid `pulse_leakage` condition includes one.

With shared simulated lighting:

| Method | Raw correct / wrong | Screened correct / wrong | Correct readings lost | No-pulse candidates, raw → screened |
|---|---:|---:|---:|---:|
| Green | 96 / 96 | 80 / 0 | 16 | 24 → 0 |
| POS | 128 / 64 | 96 / 0 | 32 | 16 → 0 |
| CHROM axes | 146 / 12 | 114 / 0 | 32 | 10 → 2 |
| POS variant | 124 / 64 | 92 / 0 | 32 | 16 → 0 |

Every method has 192 pulse-present cases and 40 no-pulse controls. Rejected or
previously unavailable cases are not counted as correct. All 32 correct POS
readings lost in the shared-light condition had an injected rate of 138 BPM,
coinciding with the colored light. Thus eliminating wrong accepted POS readings
also loses real injected pulse components. The CHROM-axis method still returns
two false candidates on pulse-absent colored-light cases, so this policy is not
a complete artifact detector even within the fixture suite.

Reference failure modes are substantial. For POS:

| Reference condition | Correct retained | Wrong retained | Correct lost | No-pulse candidates retained |
|---|---:|---:|---:|---:|
| Shared light | 96 | 0 | 32 | 0 |
| Lighting affects only face | 128 | 64 | 0 | 16 |
| Background contaminated with pulse | 40 | 0 | 88 | 0 |
| Missing reference | 0 | 0 | 128 | 0 |

The missing-reference row is total abstention, not successful artifact detection.
The face-only-lighting row shows that a quiet background cannot validate the
face candidate. Pulse contamination makes correct-reading retention much worse.
These limitations prevent promotion to live display decisions.

## Reproduce and next validation

From the repository root after installing the project:

```sh
python scripts/compare_lighting.py --output outputs/lighting-screen
```

The local `lighting-benchmark.json` contains all raw estimates, screened
decisions, face/reference input checksums, protocol and implementation checksums,
package versions, coverage, accepted-set errors, correct readings retained/lost,
wrong readings retained/removed, and no-pulse candidate counts by reference mode.
Generated outputs are not committed.

Existing webcam archives contain only face RGB/geometry. An independent
background cannot be reconstructed from them. Natural validation first needs
paired non-skin sampling with a visible ROI and explicit missing/contaminated
reference handling, plus synchronized pulse-reference measurements. Until then,
this module remains an offline experimental API. See the
[reference protocol](REFERENCE_PROTOCOL.md) and
[extraction comparisons](EXTRACTION_EXPERIMENTS.md).
