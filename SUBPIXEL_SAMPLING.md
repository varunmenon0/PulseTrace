# Fractional coverage sampling experiment

The default video extractor still uses integer polygon masks. The experimental
`pulsetrace.subpixel` module samples float convex polygons with an 8 by 8 lattice
per image pixel, then computes RGB means from fractional pixel coverage. It does
not smooth landmarks, RGB traces, or time windows.

The polygon is inset by an axis-aligned square with one-pixel radius, a continuous
analogue of the baseline's 3 by 3 square erosion. Twelve patches partition the
same subpixel samples at float bounding-box midpoints. Parent and patch weights
sum exactly; every sample requires at least 30 pixels of fractional coverage.
This changes both raster coverage and the precise inset/quadrant boundaries, so
it is not an isolated test of antialiasing alone. The finite lattice itself still
quantizes coverage, and the method has no throughput benchmark.

## Paired subject 14 result

The checksum-verified public development recording was decoded once. Both
samplers received exactly the same 1,993 frames and MediaPipe 0.10.21 landmarks.
Signal filters, spectral thresholds, consensus, windows, and reference labels
were unchanged. Global and regional exclusions were fixed to the original
integer sampler, including its area events. Fractional sample availability can
still remove a candidate, but cannot override a baseline exclusion.

| Parent region | Integer area jumps >10% | Fractional area jumps >10% |
|---|---:|---:|
| Forehead | 37 | 8 |
| Left cheek | 19 | 0 |
| Right cheek | 16 | 0 |
| Total region/frame events | 72 | 8 |

The 88.9% reduction concerns mask-area events, not physical motion, RGB noise,
heart-rate error, or validated pulse quality. Each parent had 1,992 comparable
adjacent-frame pairs. Small patches also became unavailable more often:

| Patch | Integer missing frames | Fractional missing frames |
|---|---:|---:|
| Forehead top right | 0 | 28 |
| Left cheek bottom right | 187 | 463 |
| Right cheek top right | 83 | 320 |

All other patches had zero missing frames. Different pixel support and float
quadrant boundaries affect which patches meet the fixed area minimum. Lowering
that minimum to rescue this recording was not part of the experiment.

For 12-patch POS, the integer sampler returned ungated consensus in 10 of 10
windows; fractional sampling returned 9. On the nine common scorable windows,
mean absolute difference from stored device BPM was 12.007 versus 11.818 BPM.
That small change is not evidence of validated accuracy, particularly because
the contact waveform and device labels disagree in this recording. Both methods
have zero accepted windows under the fixed strict global or regional gates.
The default pipeline and earlier frozen results are unchanged.

The report includes POS and green results, three-region and twelve-patch layouts,
all candidates, separate coverage denominators, common-window comparisons,
source/model hashes, settings, dependency versions, and missing-frame counts.
It is saved at `examples/subpixel-subject14/comparison.json`.

## Reproduce

Use the source downloader documented in `CONTACT_REFERENCE_AUDIT.md`, then run:

```sh
python scripts/compare_subpixel.py \
  --video outputs/subject14-video/vid.avi \
  --reference outputs/subject14-video/ground_truth.txt \
  --model models/face_landmarker.task \
  --output outputs/subpixel-subject14/comparison.json
```

The default is eight subdivisions and the full recording. `--max-seconds` supports
short diagnostic runs, which must be reported separately. The isolated benchmark
environment pins MediaPipe 0.10.21 as described in earlier validation notes.
Recordings, models, and face overlays are not committed.

Tests cover analytic rectangle area, quadrant conservation, constant RGB,
translation across a gradient, invalid/small polygons, and preservation of
baseline quality exclusions in the paired evaluator. Those synthetic tests do
not validate pulse detection on natural video.

## Decision

Retain the integer default. Fractional coverage reduces area quantization here,
but patch availability and reference reliability remain unresolved. Next, test
patch support and lattice convergence across multiple recording scales without
using expected BPM to choose settings. A future policy that uses fractional area
for exclusions must be evaluated separately from this fixed-gate sampler test,
with independent reference processing and a fresh held-out cohort.
