# Experimental per-region quality gate

The original global gate remains the default. This mode compares it to local
exclusions on the same continuous 12-second windows (six-second steps).

## Rules fixed before this comparison

- A displacement over 0.05 face units, an area step over 10%, or missing samples
  excludes the affected parent region (forehead or cheek).
- When at least two parent regions are displaced or unavailable in the same
  frame, all parents are excluded.
- The same half-second buffer surrounds all flagged frames.
- If a region has any excluded frame in a window, none of its samples or
  child-patch estimates can vote in that window. No bridging or concatenation.
- Remaining candidates still need the existing spectral checks and consensus
  across at least two parent zones. Region-quality selection never sees the
  reference pulse or expected subject BPM.

These rules can miss occlusion/shared artifacts and reject good samples.
They are development heuristics, not calibrated physiological confidence.

## Use

```sh
python -m pulsetrace analyze recording.mov --model models/face_landmarker.task --patches --regional-quality --output outputs/regional-test
```

This writes regional_comparison.json alongside the usual baseline outputs.
Baseline whole-clip plots/summary and exit-code behavior remain unchanged.
Use the explicitly labeled global_gate and regional_gate fields for this
experiment. Green is still an exploratory baseline and can fail badly.

## Offline evaluation

benchmark_ubfc.py saves a local extraction.npz. To reuse it:

```sh
python scripts/evaluate_regional_quality.py --cache outputs/subject10/benchmark/extraction.npz --benchmark outputs/subject10/benchmark/benchmark.json --output outputs/subject10/regional
```

The benchmark and cache must come from the same input/run. The evaluator checks
dimensions, times and window agreement, but does not independently authenticate
the cache file. Its paired reference labels retain the UBFC validity policy;
reference-invalid windows remain unscorable.

This compares three development subjects; overlapping windows are not independent
subjects. Publication of error/coverage on these recordings does not establish
held-out accuracy. The full raw videos are not committed.


## Development results (subjects 1, 10, 11)

27 overlapping windows, of which 23 have valid reference labels. Same source
hashes as the preceding public comparison, same MediaPipe 0.10.21 runtime,
same filters/thresholds. Restored videos were checksum-verified before processing.

| POS layout and gate | Accepted/reference-valid windows | Pooled MAE (BPM) |
| --- | --- | --- |
| 3 regions, original global gate | 4/23 | 1.757 |
| 3 regions, experimental regional gate | 11/23 | 1.930 |
| 12 patches, original global gate | 3/23 | 1.431 |
| 12 patches, experimental regional gate | 7/23 | 1.231 |

The 12-patch mode admits four additional windows: MAE 1.082 BPM, maximum
absolute error 2.589 BPM. Three-region mode admits seven additional windows:
MAE 2.029 BPM, maximum 3.895 BPM. Neither layout loses an estimate accepted by
the global gate on these recordings. The pooled MAEs use different accepted
subsets and are not proof of an overall accuracy improvement.

Green returns 2 to 4 windows for three regions (MAE 1.734 to 2.381 BPM) and
4 to 5 for 12 patches (MAE 1.540 to 1.462 BPM). The previously observed large
green errors outside retained windows remain in the earlier benchmark reports.

Full reports are examples/ubfc-subject*/regional_comparison.json; aggregate
is examples/ubfc-regional-summary.json. To regenerate the aggregate:

```sh
python scripts/summarize_regional_quality.py examples/ubfc-subject1/regional_comparison.json examples/ubfc-subject10/regional_comparison.json examples/ubfc-subject11/regional_comparison.json --output outputs/regional-summary.json
```

A new exact-12-second CLI test exposed a window boundary rounding issue.
Benchmark and regional window loops now allow one frame of endpoint tolerance,
consistent with diagnostic window construction. It does not change the window
counts on these three recordings.

Next step: freeze these rules and test unseen subjects. These development
results are too small and dependent to justify switching the default gate.

See [FROZEN_EVALUATION.md](FROZEN_EVALUATION.md) for subsequent frozen-rule results on subjects 12-14, including a complete-coverage failure.
