# Paired balanced-sampling evaluation on two development recordings

The geometry-balanced sampler now has a fixed-gate comparison on UBFC subjects
10 and 14. Both recordings were previously used for development. This is not a
new held-out evaluation. The original integer sampler remains the default.

## Sampling support

Each paired run decodes the video once and gives both samplers the same frames
and landmarks. Filters, thresholds, consensus, device reference labels, and
baseline global/regional exclusions stay fixed. The fractional sampler uses an
8x8 lattice, one-pixel square inset, geometry-balanced partition, and minimum
coverage area of 30 per patch.

| Recording | Frames | Integer missing patch observations | Balanced missing patch observations |
|---|---:|---:|---:|
| Subject 10 | 2,024 | 0 | 0 |
| Subject 14 | 1,993 | 270 | 0 |
| Total | 4,017 | 270 | 0 |

There are 48,204 patch/frame observations per sampler. The improvement comes
entirely from subject 14; subject 10 already had full patch availability. The
replayed integer subject 10 estimates match the earlier archived benchmark.
Missing observations describe sample availability, not heartbeat presence.

## Pulse estimates: coverage and matched errors

The table uses 12-patch POS with the fixed regional gate. Each recording has ten
reference-valid 12-second windows, stepped every six seconds. Errors below are
mean absolute differences from stored device BPM, whose accuracy/alignment has
not been independently established.

| Recording | Integer scorable windows | Balanced scorable windows | Common windows | Integer difference on common windows | Balanced difference on common windows |
|---|---:|---:|---:|---:|---:|
| Subject 10 | 5/10 | 6/10 | 4 | 1.664 BPM | 2.058 BPM |
| Subject 14 | 0/10 | 0/10 | 0 | Unavailable | Unavailable |
| Pooled | 5/20 | 6/20 | 4 | 1.664 BPM | 2.058 BPM |

Subject 10 gains two newly scorable windows and loses one; the change is not
simply an added window. Both streams use the same exclusions, but their sampled
RGB and consensus decisions differ. All failures stay in the denominators.

Without quality exclusions, the two samplers share sixteen scorable windows
across both recordings. Mean absolute difference from device labels is 7.191 BPM
for integer versus 7.342 BPM for balanced sampling. These pooled errors are
strongly influenced by subject 14's reference discrepancy. Separate accepted-set
means can look better merely because the accepted sets differ; use the report's
common-window comparisons and coverage changes together.

The strict global gate scores only two of twenty windows for either sampler.
There is no demonstrated improvement in heart-rate accuracy, and the remaining
coverage loss is substantial. Better geometric support does not establish a
better pulse spectrum or a valid measurement.

## Scale study and reference audit

The subject 10 geometry audit tracks the native recording and selects every
30th frame: 68 tracked samples, giving 204 parent and 816 patch observations per
configuration. At native and 1.5x geometry scale, both partitions keep all patches
above the minimum on all three tested lattices (4x4, 8x8, 16x16). At half scale,
all 816 patch observations fail the minimum for both partitions at every lattice.
Coordinates are scaled with the pixel-center convention. RGB is not resized and
tracking is not repeated at altered resolution. This does not measure
low-resolution pulse or tracking performance.

The contact-only subject 10 audit has no windows with device-median versus contact
spectral disagreement exceeding 10 BPM. In its first window, device median is
98 BPM, contact spectral estimate is 91.5, and interbeat estimate is 94.737.
This is more consistent than subject 14's first-window 98 versus 69/72, but it
does not verify reference timing or validate the exploratory contact extractor.
No device labels or offsets were changed. The original frozen evaluation remains
unchanged; these sampler experiments use development data.

## Reproduce and inspect

Use `examples/ubfc-subject10/source.json` with the existing checksum-verifying
downloader, then run the same commands documented in `PATCH_SUPPORT.md`, replacing
subject14 paths with subject10. The source/model hashes, dependency versions,
settings, all candidates, and geometry summaries are preserved in
`examples/equal-area-subject10/`. Subject 14's corresponding reports stay in
`examples/equal-area-subject14/`.

Pool compatible reports with:

```sh
python scripts/summarize_sampling.py \
  examples/equal-area-subject10/comparison.json \
  examples/equal-area-subject14/comparison.json \
  --output outputs/balanced-sampling-summary.json
```

The committed pooled summary is `examples/balanced-sampling-summary.json`. The
pooler rejects duplicate video hashes, mismatched settings/dependency versions or
models, unequal paired window counts, and mismatched timing/reference labels.
It reports accepted-set and common-window errors, newly/lost scorable windows,
missing observations, and per-recording results. Pooled errors weight accepted
windows equally, not recordings. Overlapping windows are not independent.

## Decision

Keep the sampler opt-in. The pipeline, tests, experiment provenance, and numeric
failure reporting are in place, but reference verification and reliable usable
coverage remain the next scientific hurdles. Further changes need independent
reference processing and recording alignment evidence, broader motion/lighting
coverage, and a fresh evaluation cohort. Avoid choosing geometry or gates by
whether they match a subject's expected BPM.
