# Geometry-balanced patch support

The previous fractional sampler reduced parent-area quantization, but bounding-box
quadrants made small tapered cheek patches unusable. This follow-up tests a
geometry-only partition that divides the continuous inset polygon into four
approximately equal coverage areas. Thresholds, parent masks, signal processing,
reference labels, and the default pipeline remain unchanged.

## Full subject 14 recording

All 1,993 development-video frames were decoded once per paired run. Both samplers
received the same landmarks in each run. The integer window results exactly match
the previous fractional-sampling experiment, and fractional parent-area metrics
are unchanged. Each minimum remains 30 pixels of coverage, with an 8x8 lattice.

| Sampler / partition | Missing patch/frame observations out of 23,916 |
|---|---:|
| Original integer sampler | 270 |
| Fractional bounding-box split | 811 |
| Fractional geometry-balanced split | 0 |

A missing observation means insufficient coverage or unavailable geometry, not
absence of a heartbeat. Removing that sampling failure does not guarantee a
usable pulse spectrum. The balanced sampler still returns ungated 12-patch POS
consensus in only 9 of 10 windows. On its nine common scorable windows with the
integer sampler, mean absolute difference from stored device BPM is 11.544 versus
11.377 BPM. The accepted sets differ from the earlier bounding-box experiment,
so its nine-window mean must not be compared directly to this nine-window mean.

Both strict global and regional gates still accept zero subject 14 windows.
Those exclusions were deliberately fixed to the original integer stream. This
experiment measures sampling support, not a replacement exclusion policy. The
contact/device-label discrepancy and recording synchronization are unresolved.
No accuracy improvement or independent validation is established.

## Controlled geometry scale and lattice check

The tracker processed the complete native video. Geometry from every 30th frame
provided 67 tracked samples, or 201 parent-region observations per configuration.
Those landmark coordinates were then scaled with the pixel-center convention,
without retracking or resampling RGB. Each configuration has 804 patch observations.
The one-pixel inset and 30-pixel minimum stayed fixed in the resulting coordinate
system. This is a geometry study, not a low-resolution video benchmark.

| Geometry scale | Lattice | Missing bbox patches | Missing balanced patches |
|---|---:|---:|---:|
| 0.5x | 4x4 | 804 | 804 |
| 0.5x | 8x8 | 804 | 804 |
| 0.5x | 16x16 | 804 | 804 |
| 1.0x | 4x4 | 28 | 0 |
| 1.0x | 8x8 | 29 | 0 |
| 1.0x | 16x16 | 31 | 0 |
| 1.5x | 4x4 | 1 | 0 |
| 1.5x | 8x8 | 1 | 0 |
| 1.5x | 16x16 | 1 | 0 |

Every half-scale parent had less than the 120 coverage pixels necessary for four
patches of area 30. At native scale, all parents had enough total area, but the
bounding-box split sometimes allocated too little to one child. The balanced
split had minimum patch area 45.172 at 8x8 in this sample.

Compared with the 16x16 numerical comparator, the largest individual patch-area
difference across scales/partitions was 4.609 pixels at 4x4 and 2.145 pixels at
8x8. The 16x16 lattice is not exact coverage. Near-threshold bounding-box decisions
varied across lattices; this study does not establish universal numerical
convergence or justify a new default resolution.

## Reproduce

Acquire the checksum-verified recording using the existing subject 14 source
manifest, as documented in `CONTACT_REFERENCE_AUDIT.md`.

```sh
python scripts/compare_subpixel.py \
  --video outputs/subject14-video/vid.avi \
  --reference outputs/subject14-video/ground_truth.txt \
  --model models/face_landmarker.task \
  --partition equal_area \
  --output outputs/equal-area-subject14/comparison.json
python scripts/audit_patch_support.py \
  --video outputs/subject14-video/vid.avi \
  --model models/face_landmarker.task \
  --output outputs/equal-area-subject14/support.json
```

The latter script fixes scales to 0.5, 1.0 and 1.5; lattices to 4, 8 and 16;
and samples every 30th frame by default. No RGB, expected BPM, or reference labels
select its cuts or settings. Reports preserve source/model hashes, dependency
versions, configuration, sample indices, and all measured counts. MediaPipe
0.10.21 was used. Only numeric reports are committed under
`examples/equal-area-subject14/`.

## Decision and next step

Keep equal-area sampling experimental. It resolves the patch-area imbalance on
this development recording, while spectral ambiguity and reference reliability
remain. More patch support is not equivalent to more pulse information. Moving
area-balanced boundaries can also change sampled tissue, which needs further
motion and waveform evaluation.

Next, repeat the fixed-gate comparison on other development recordings, then
freeze any proposed sampler and test a fresh cohort with independently checked
references. Geometry-based insufficiency should continue to produce an explicit
unusable result at small face sizes. Do not lower the area minimum or tune to
expected pulse rates to make this clip pass.
