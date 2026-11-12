# Subject 14: mask quantization and reference disagreement

PulseTrace estimates heart rate from video. This investigation does not establish
medical accuracy. The existing frozen evaluation and its reported device-label
scores remain unchanged; all six recordings used below are now development data
for the new area policy.

## Small masks amplify rounding

Inspected overlay frames 12 and 223 show the three parent patches on facial skin.
This is a spot check, not a review of every frame. On a fresh MediaPipe 0.10.21
extraction of the first 450 frames of subject 14, 17 region/frame events exceeded
the 10% raster pixel-count threshold. In 15 of those events the continuous convex
polygon area changed by less than 2%. For example, frame 12's left-cheek raster
area changed 12.3%, while its continuous polygon area changed about 0.5%.

The sampler rounds landmark coordinates, fills an integer polygon, and erodes it
by one pixel. These small cheek patches contain only a few hundred pixels.
The evidence supports raster quantization as a contributor to area flags. It does
not show that every flagged frame is safe, or that continuous area alone measures
sampled-tissue stability. Head movement and changes in sampled pixels remain risks.
Numeric geometry is saved in `examples/subject14-diagnosis/geometry.json`.

## The contact reference also needs verification

A contact-only audit resamples the raw contact waveform at 30 Hz, detrends and
bandpasses 40–200 BPM, and compares its spectral peak with independently detected
interbeat intervals. It never uses video estimates to select a reference peak.
In subject 14's first window, the stored device BPM median is 98, the contact
spectral estimate is 69, the interbeat estimate is 72, and video 12-patch POS is
about 69. Thus the previously reported approximately 11 BPM ungated error against
device labels cannot be attributed entirely to video failure.

This audit is exploratory: neither contact estimator is a validated replacement
reference. Filtering, harmonics, pulse detection, device averaging, or alignment
could contribute. The cause is unresolved. No label was replaced or shifted.
The timestamp origin remains an assumption without hardware synchronization.

| Subject | Audited 12-second windows | Device vs contact PSD >10 BPM | Contact methods differ >6 BPM |
|---|---:|---:|---:|
| 1 | 7 | 0 | 0 |
| 10 | 10 | 0 | 0 |
| 11 | 10 | 2 | 1 |
| 12 | 10 | 1 | 0 |
| 13 | 10 | 0 | 0 |
| 14 | 10 | 3 | 2 |

The contact audit covers complete reference windows, which differs from the
benchmark's video-window and reference-validity denominator.

## Tested alternative, kept experimental

The offline `corroborated` policy ignores area-only events unless accompanied by
a same-direction RGB step above 2% in at least two channels, or normalized shape
change above 0.03. Displacement/loss exclusions, shared-motion exclusions, buffers,
window lengths, candidate calculations, and consensus requirements stay fixed.
These are engineering heuristics, not calibrated reliability thresholds.

Across all six recordings, using 12-patch POS and the original device labels:

| Regional policy | Accepted / reference-valid windows | Mean absolute difference from device BPM |
|---|---:|---:|
| Strict area gate | 17 / 53 | 1.286 BPM |
| Corroborated area gate | 40 / 53 | 3.302 BPM |

These are selectively accepted windows, not full-dataset accuracy. Subject 14
changes from 0 to 6 accepted windows, with 11.079 BPM mean and 28.834 BPM maximum
absolute difference from device BPM. The alternative therefore increases coverage
but does not demonstrate a dependable accuracy improvement. The strict default
remains unchanged. Raw reports for both POS and green and both layouts are saved
alongside a pooled summary; strict source reports remain in their earlier example
folders. Do not present this experiment as a new held-out result.

## Reproduce and continue

Using the previously documented checksum-verified UBFC sources and extraction
caches, run:

```sh
python scripts/diagnose_mask_geometry.py path/to/subject14/vid.avi --output outputs/geometry.json
python scripts/audit_contact_reference.py path/to/ground_truth.txt --output outputs/reference_audit.json
python scripts/evaluate_regional_quality.py --help
```

Use the evaluator's `--area-policy corroborated` only for offline comparisons.
MediaPipe 0.10.21 was used because 0.10.35 crashed in this environment. Recordings,
models, and face overlays are not committed.

Next, verify the contact-waveform extractor and device timing independently,
including visual pulse inspection and alignment evidence. Then evaluate a subpixel
weighted sampler against the existing integer sampler using the same frames and
fixed gates. A reliable sampling fix needs a fresh held-out cohort; simply
increasing area tolerance is not supported by this experiment.
