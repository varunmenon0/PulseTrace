# Frozen-rule check on new UBFC subjects

This evaluation uses subjects 12, 13 and 14, selected before downloading or
examining their results. Subjects 1, 10 and 11 remain development examples and
are not pooled into the new-subject score.

The protocol is committed in examples/ubfc-heldout/protocol.json. Algorithm
commit b974f2a is frozen: no thresholds, masks, filters, consensus rules,
window settings or reference validity rules changed for these recordings.
The newly added report script only aggregates saved outcomes.

This is a small same-dataset subject holdout, not cross-dataset or clinical
validation. The public mirror and elapsed-time alignment assumptions from
PUBLIC_VALIDATION_MULTI.md still apply. Overlapping windows are dependent;
both window-weighted MAE and mean subject MAE are reported with subject counts.
Subjects without estimates are retained explicitly and have no finite MAE.

All source hashes, individual windows, rejected windows and gate comparisons
are recorded. Download/inference failures remain explicit rather than silently
replaced by easier subjects. No source videos or extraction caches are committed.

## Reproduce

Use the same isolated MediaPipe 0.10.21 runtime. Each subject folder includes
source.json compatible with scripts/download_ubfc_sample.py. After downloading,
run benchmark_ubfc.py and evaluate_regional_quality.py as in REGIONAL_QUALITY.md.
The evaluator receives labels only after region-quality selection has finished.

Aggregate the cohort:

```sh
python scripts/report_frozen_evaluation.py examples/ubfc-heldout --output outputs/heldout-summary.json
```

The report includes errors over 10 BPM among newly admitted windows. This
threshold is a reporting diagnostic fixed in the protocol, not an algorithm
rejection threshold or a medical accuracy criterion.

## Results

All three planned recordings completed: 30 reference-valid windows, 10 per subject.
No download or inference failures occurred.

| POS layout and gate | Accepted windows | Pooled MAE on accepted windows |
| --- | --- | --- |
| 3 regions, global | 5/30 | 2.002 BPM |
| 3 regions, regional | 12/30 | 1.368 BPM |
| 12 patches, global | 4/30 | 2.058 BPM |
| 12 patches, regional | 10/30 | 1.324 BPM |

For 12 patches, six newly admitted windows have MAE 0.834 BPM and maximum
absolute error 1.482 BPM. No newly admitted POS window exceeds 10 BPM error.
No globally accepted estimate was lost. These subset means compare different
windows, so the lower pooled MAE alone is not an accuracy-superiority claim.

Per-subject 12-patch POS results:

| Subject | Global accepted | Regional accepted | Regional MAE |
| --- | --- | --- | --- |
| 12 | 3/10 | 6/10 | 1.480 BPM |
| 13 | 1/10 | 4/10 | 1.089 BPM |
| 14 | 0/10 | 0/10 | Unavailable |

Subject14 must remain in the coverage denominator. It has no displacement
spikes under the fixed threshold, but 37/19/16 area flags on the forehead and
cheeks respectively. Each window intersects exclusions in all three parents.
Ungated 12-patch POS returns 10/10 windows with about 11.33 BPM MAE; simply
bypassing quality gating would not solve this failure. No thresholds were
adjusted after seeing it.

Three-region POS returns more windows than 12 patches with similar error.
This experiment supports the local gate on two new recordings; it does not
establish that 12 patches are superior to three regions.

Green remains secondary: three-region regional returns 8/30 windows at 1.503
BPM MAE, and 12-patch regional returns 8/30 at 1.770 BPM. Earlier development
failures of green remain documented.

The aggregate JSON reports both window-weighted and equal-subject MAE, explicitly
counting how many subjects have estimates. Subject14 contributes no finite
MAE and must not be interpreted as zero error. Hardware reference alignment
is still assumed from dataset elapsed time, not independently verified.

## Decision and next investigation

Keep regional quality opt-in. It generalizes usefully to subjects12/13 but
coverage is still only 10/30 windows for 12-patch POS and fails completely on
subject14. The next development investigation should inspect area instability
and actual skin sampling on that failure, then evaluate any changed strategy
on different subjects. Subjects12-14 are now seen and cannot serve as an unseen
test set for subsequent changes.
