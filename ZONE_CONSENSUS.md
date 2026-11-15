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

## Replay results

The candidate-only replay reproduced every legacy decision before running the
new policy. It uses the original window boundaries, filters, candidates,
quality exclusions, and device-reference labels, including unscorable labels.
The primary group has 57 windows across subjects 1, 10, 11, 12, 13 and 14; 53
have scorable device references. All of these recordings are development data
for this new voting policy.

| POS policy, integer sampling | Patch scorable windows | Zone scorable windows | Common windows | Patch common difference | Zone common difference |
|---|---:|---:|---:|---:|---:|
| Global gate | 7/53 | 6/53 | 5 | 1.640 BPM | 1.697 BPM |
| Regional gate | 17/53 | 17/53 | 14 | 1.194 BPM | 1.214 BPM |

For the regional gate, accepted-set mean absolute device-label difference is
1.286 BPM for patch voting and 1.231 BPM for zone voting. That apparent reduction
comes largely from different accepted windows: three are gained and three lost.
On common windows the difference slightly increases. The accepted-set maximum
falls from 4.039 to 2.798 BPM, but this is not a demonstrated accuracy improvement
or a fresh held-out result.

| Recording, regional POS | Patch scorable windows | Zone scorable windows |
|---|---:|---:|
| Subject 1 | 2/7 | 1/7 |
| Subject 10 | 5/10 | 5/10 |
| Subject 11 | 0/6 | 0/6 |
| Subject 12 | 6/10 | 5/10 |
| Subject 13 | 4/10 | 6/10 |
| Subject 14 | 0/10 | 0/10 |

The four invalid subject 11 reference windows remain in the total-window count
but are not scored. Green-channel regional coverage changes from 13/53 to 10/53;
its accepted-set device-label difference changes from 1.652 to 1.660 BPM. Both
methods are retained in the full report.

The separate balanced-sampling group replays subjects 10 and 14 under all three
existing gate policies. With the photometric guard, POS coverage changes from
18/20 to 14/20. The fourteen common BPM decisions are identical. Three subject 10
windows and one subject 14 window lose sufficient zone support. The previously
observed 7.299 BPM subject 10 device-label difference remains accepted: the new
policy is not a general detector of inaccurate estimates. Sampling and gate
groups are kept separate rather than double-counted in a single headline score.

## Reproduce and inspect

```sh
python scripts/replay_zone_consensus.py \
  --protocol examples/zone-consensus/protocol.json \
  --output outputs/zone-consensus/replay.json
```

No videos or models need downloading for this replay. Inputs are committed,
checksummed candidate reports. The evaluator rejects changed source hashes,
duplicate recordings within a group, incompatible rule configuration, and any
legacy result that fails to reproduce. The report preserves per-recording and
pooled metrics, candidate and scorable coverage, common-window differences,
newly/lost decisions, and each zone's voting diagnostics.

## Development assessment

Sampling support and reproducibility are established engineering capabilities;
measurement quality is the current priority. The review identified three issues:
device/PPG disagreement and unverified clock mapping, lighting that can be shared
across all patches, and patch-count imbalance in voting. The zone policy directly
addresses the last issue and exposes its support requirements in the CLI.

Keep patch voting as the default. Region-balanced voting is now a selectable
comparison, with its coverage tradeoffs measured rather than inferred from a
synthetic success. A regression case confirms that coherent periodic lighting
still produces 108 BPM green consensus across all three zones while POS follows
the injected 72 BPM component. Regional agreement alone does not verify pulse.

Next validation needs independently reviewed beat references and physical
motion/occlusion recordings, followed by a fresh cohort for a frozen sampler,
gate, and consensus policy. The external-reference adapter is already available;
reviewed natural-video beat annotations have not been imported. Existing frozen
reports and production defaults remain unchanged.
