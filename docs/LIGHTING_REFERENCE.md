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

Older webcam archives contain only face RGB/geometry. An independent
background cannot be reconstructed from them. New sessions can optionally record
the paired reference described below. The screen remains offline and is never
applied to live decisions. Natural validation still requires synchronized
pulse-reference measurements. See the
[reference protocol](REFERENCE_PROTOCOL.md) and
[extraction comparisons](EXTRACTION_EXPERIMENTS.md).

## Record a paired background with the webcam

Choose a plain, stationary background patch visible in the camera view, such as
a wall. Keep faces, hands, other skin, displays, and moving objects out of it.
The software rejects a tracked face entering the rectangle, but it does not
classify skin or objects elsewhere and cannot verify shared illumination.

From the repository root, use a new output folder:

```sh
.venv/bin/pulsetrace webcam --model models/face_landmarker.task --seconds 90 \
  --background-roi 0.02 0.02 0.12 0.12 \
  --output outputs/webcam-lighting-1
```

`--background-roi X Y WIDTH HEIGHT` uses image fractions. This example selects
a small box near the upper-left corner. Check the visible box before relying on
it. Blue means the patch is being sampled; a red box and explanatory message
mean it is unavailable. If the box contains skin or a screen, stop with Q and
choose another rectangle. Keep lighting steady and your face still for the first
test. Blue indicates geometric availability, not a verified lighting reference
or accurate heart rate.

The rectangle stays fixed in image coordinates; it is not automatically moved
or cropped to hide an overlap. Any intersection with the tracked face's
landmark bounding rectangle, padded by 10% of its width/height on each side,
rejects the whole background patch for that frame. Missing/invalid face tracking
or insufficient pixels also makes the reference unavailable. The preview labels
these conditions. It does not detect hands, a second untracked face, or arbitrary
foreground objects. A stationary background and visual inspection remain
necessary. Camera resolution changes preserve the normalized rectangle but
reset the face engine as before.

Face and background averages come from the same sampled frame and share its
original read-completion timestamp. Acquisition, queues, motion exclusions,
face sampling, and existing heart-rate decisions retain their policies. No
frame images are saved. Optional background measurements add only RGB means,
pixel count, rectangle bounds, status, and a reason when unavailable.

The summary counts available and rejected background samples. Sessions using
this option write archive schema 2; sessions without it retain schema 1. The
reader accepts both. Schema 2 requires a background entry in every sample,
including explicit missing-reference entries, and validates their shapes and
status. Older readers that support only schema 1 cannot open schema 2; use this
branch's tools. Omitting `--background-roi` preserves the existing recording
behavior.

## Audit a recorded session without the camera

```sh
.venv/bin/python scripts/audit_lighting_session.py \
  outputs/webcam-lighting-1/samples.jsonl \
  --output outputs/webcam-lighting-1-audit
```

The script first replays the saved face measurements and requires every window
to match the original `stream.jsonl`, ignoring runtime capture timing fields.
It stops if they differ. It then uses each window's exact selected support for
the background screen. Any unavailable background sample on that support makes
the reference unavailable for the whole window. It does not interpolate across
that absence or select a more favorable interval. Existing uncertain or
unavailable live readings stay withheld; the audit cannot resurrect them.

The separate output contains `lighting-audit.json` plus a face replay. The report
retains original displayed and raw candidates, reference status and sample
counts, overlap observations, source/event checksums, and implementation
provenance. Original logs stay untouched. The report scores no human pulse
accuracy and does not change the live display. Old archives can be audited for
face parity, but their references are explicitly unavailable.

Automated tests use synthetic frames and mocked camera I/O. Actual camera
placement, tracking, lighting, and independent-reference accuracy still require
a new recording; no new natural-camera accuracy claim is made.
