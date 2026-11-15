# One vote per facial region

The optional zone policy establishes agreement among patches within each parent
region, then gives each supported parent one vote. It addresses unequal patch
availability: four forehead patches no longer outweigh two supported cheeks
simply because the forehead supplies more candidates.

Within each zone, at least two patches must form a unique largest cluster within
5 BPM, supported by a strict majority of available candidates. Each accepted
zone contributes its supported-patch median. The final estimate requires a unique
strict-majority cluster across at least two accepted zones within the same 5 BPM
span. Ties and insufficient support produce an explicit rejection reason.

For example, with four forehead candidates at 72, cheek candidates [72,95,95]
and [95,95], the original patch policy chooses 72. Zone voting chooses 95 because
both cheeks independently support it. This is a controlled voting example, not
a physiological validation result. It demonstrates the change in voting weights.

## Use

```sh
pulsetrace demo --patches --consensus zone --output outputs/zone-demo
pulsetrace analyze recording.mp4 --model models/face_landmarker.task \
  --patches --regional-quality --consensus zone --output outputs/zone-run
```

The default remains `--consensus patch`. Zone selection applies consistently to
both the twelve-patch segment report and the regional/global gate comparison;
three-region baseline votes retain their existing behavior. Reports record the
selected policy, per-zone candidate status, supported patches, supporting zones,
and rejection reasons. Quality-excluded patches remain unavailable.

## Development replay protocol

`examples/zone-consensus/protocol.json` fixes the rule and exact source report
hashes before running the new replay. It includes all six previously evaluated
integer-sampling recordings, plus the existing balanced/photometric experiments
on subjects 10 and 14. Both POS and green are included. Sampling and gate policies
are kept separate, and every original patch-vote result must reproduce first.

The six recordings have already been used for development; the earlier fixed-rule
evaluation remains unchanged. This replay can assess voting behavior and coverage
tradeoffs on stored candidates. Reference-label disagreements, timing assumptions,
and common lighting artifacts still require independent evaluation.
