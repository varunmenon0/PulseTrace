# Three-recording UBFC development check

This extends the first subject1 check with subjects 10 and 11, selected in
advance in filename order. All three use the same filters, estimator thresholds,
consensus rules and motion/area thresholds. Raw recordings stay outside Git.

The source is the public thachha901/UBFC mirror of Dataset 2, not a download
directly verified against official UBFC video checksums. Source manifests store
URLs, file hashes and sizes. Nominal elapsed-time origin zero is assumed;
hardware synchronization has not been independently verified. These are
development recordings, not a held-out accuracy benchmark.

## Findings

Across 27 overlapping 12-second windows, 23 are scorable against reference BPM.

| POS comparison | Three regions | Twelve patches |
| --- | --- | --- |
| Estimates on reference-valid windows, before motion gate | 22/23 | 17/23 |
| Pooled window MAE on those estimates | 2.317 BPM | 1.641 BPM |
| MAE on the same 16 windows accepted by both | 1.842 BPM | 1.740 BPM |
| Estimates after existing global motion/area gate | 4/23 | 3/23 |

The paired difference is small and 12 patches sacrifice coverage. No statistically
supported superiority is claimed. The pooled MAE values use different accepted
subsets; the paired comparison is the fairer layout comparison. Window counts
are not independent sample counts. Per-subject and pooled/macro errors and
all window candidates remain in the JSON reports.

Green on subject11 can be about 43 BPM off even on reference-valid windows.
Cross-patch agreement alone does not rule out shared lighting/motion artifacts.
Green remains a baseline; these failures must remain in subsequent evaluations.

## Reference dropout discovered

Subject11's device BPM falls to 1-2 BPM during part of the recording.
The initial unfiltered evaluation is preserved as
benchmark-before-reference-check.json. Scoring these labels as real heart
rates inflated error. The evaluator now marks any window touching reference
values outside the estimator's supported 40-200 BPM band, or gaps over
2.5 seconds, unscorable. It does not bridge those samples or select the
reference peak closest to the estimate. Four subject11 windows are unscorable.
The raw reference medians and exclusion reasons are retained in benchmark.json.

This reference check was introduced after inspecting this development example;
it was not a pre-registered held-out protocol. It limits evaluation to the
supported band and does not certify all remaining reference labels as correct.

## What rejects the footage?

| Subject | Raw displacement-flagged frames (union across regions) | Raw area-flagged frames (union) |
| --- | --- | --- |
| 1 | 0 | Per-region counts 1, 1, 3; union unavailable in older report |
| 10 | 0 | 11 |
| 11 | 7 | 39 |

Subject1 and subject10 have no displacement flags. Their global exclusions
come from patch-area changes, not large measured landmark translation.
These are not proven false positives: local landmark deformation, pose or
pixel rounding may change sampled tissue. Existing rules buffer every flagged
frame and a benchmark window is excluded if it overlaps any buffered interval.
A few events can therefore exclude many overlapping windows.

New cause accounting separates displacement, area, and missing samples with
raw counts, buffered fractions and intervals. Combined rejection behavior is
unchanged. No threshold was loosened to improve these results.

## Reproduce

Use the isolated runtime in PUBLIC_VALIDATION.md (MediaPipe 0.10.21 completed;
0.10.35 crashed in earlier attempts). For each new subject:

```sh
python scripts/download_ubfc_sample.py --manifest examples/ubfc-subject10/source.json --output outputs/subject10
python scripts/benchmark_ubfc.py --video outputs/subject10/vid.avi --reference outputs/subject10/ground_truth.txt --model models/face_landmarker.task --output outputs/subject10/results
```

Replace subject10 with subject11 for the second recording. Each download is
about 1.87 GB. Benchmark inference also writes a local extraction.npz cache;
do not commit it. The cache preserves RGB/pixel/geometry arrays for diagnostic
recomputation without rerunning inference.

```sh
python scripts/summarize_benchmarks.py examples/ubfc-subject1/benchmark.json examples/ubfc-subject10/benchmark.json examples/ubfc-subject11/benchmark.json --output outputs/ubfc-summary.json
```

## Next experiment

Keep the current global gate as the reproducible baseline. Develop an
experimental per-region quality gate that can withhold one bad cheek while
retaining independent clean regions, with global exclusion for shared movement.
Measure lost coverage and large-error false acceptance on additional recordings.
Keep subject1/10/11 as development cases; use new subjects for the next frozen
evaluation. Investigate large green errors before allowing green consensus to
serve as a trusted result.
