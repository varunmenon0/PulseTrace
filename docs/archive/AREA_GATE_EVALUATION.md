# Fractional-area gate experiment

Earlier paired sampler tests deliberately fixed quality exclusions to the integer
baseline. This experiment changes the regional gate's area measurements to the
fractional mask's measured coverage, while both gate variants vote on the same
balanced fractional RGB and spectral candidates. It is a separate gate test,
not a revision of the previous fixed-gate sampler comparison.

## Fixed settings and diagnostics

Both variants use the same native frames, landmarks, 8x8 lattice, balanced
partition, motion measurements, 10% area threshold, 0.05 displacement threshold,
0.5-second rejection buffers, 12-second windows, six-second steps, and consensus
rules. Two displaced/unavailable parent regions still exclude all regions. Any
rejected frame makes its parent unavailable for the full window. There is no
area tolerance increase, gap bridging, device-label adjustment, or pulse-rate
selection of settings. Fractional-parent sample validity also participates in
the fractional-area gate, so unavailable samples remain rejected.

The per-window report includes each parent's rejected-frame count and usability,
accepted candidates and parent-zone counts, consensus support, and a rejection
classification. `quality_exclusions` means fewer than two parents are usable;
`insufficient_spectral_support` means fewer than two parents supply a candidate;
otherwise a rejected estimate has no unique strict-majority consensus. These
are engineering explanations, not physiological signal-quality certifications.

## Development results

Both subjects were already used in development. All twenty windows are scorable
against the original device labels; synchronization and label reliability remain
unverified. The table uses 12-patch POS and the regional gate.

| Recording | Integer-area gate: scorable windows | Fractional-area gate: scorable windows | Integer-area difference from device BPM | Fractional-area difference from device BPM |
|---|---:|---:|---:|---:|
| Subject 10 | 6/10 | 8/10 | 2.058 BPM | 1.918 BPM |
| Subject 14 | 0/10 | 9/10 | Unavailable | 12.134 BPM |
| Pooled | 6/20 | 17/20 | 2.058 BPM | 7.326 BPM |

These accepted-set means have different denominators. On subject 10's five
common windows, mean absolute device-label difference increases from 1.992 to
2.181 BPM. It gains three newly scorable windows (1.480 BPM mean difference,
2.377 maximum) and loses one previously scorable window because changing which
regions vote can change consensus. Subject 14 gains nine windows with 12.134 BPM
mean and 29.236 maximum difference from device BPM. The contact/device discrepancy
makes their accuracy unresolved; they are not established valid pulse readings.

With the integer-area gate, twelve windows fail for fewer than two usable
parents, while two fail consensus. With fractional area, all windows retain at
least two usable parents, but three still fail consensus. Individual parents can
remain excluded even when the window retains two usable parents.

The 6-to-17 change establishes improved engineering coverage on these two clips,
not improved heartbeat accuracy or safe rejection behavior on new motion clips.
The threshold settings remain unvalidated. In particular, the newly admitted
subject 14 estimates require independent reference review before they can
support an accuracy claim. The production gate remains unchanged.

## Reproduce

Download each recording using its existing checksum-verified source manifest,
then run:

```sh
python scripts/compare_area_gates.py \
  --video outputs/subject10-video/vid.avi \
  --reference outputs/subject10-video/ground_truth.txt \
  --model models/face_landmarker.task \
  --output outputs/area-gates/subject10.json
```

Repeat with subject14 paths. MediaPipe 0.10.21 was used. Reports in
`examples/area-gates/` preserve source/model hashes, versions, settings, per-window
availability, all decisions, accepted-set differences, matched comparisons,
newly/lost scorable windows, and rejection reasons for POS and green on both
layouts. No recordings, face images, or downloaded models are committed.

Synthetic tests verify that replacing a raster-only area event can recover a
known sinusoidal candidate on identical RGB, and that shared motion is still
rejected. These tests do not establish natural-video physiological validity.

## Reference path and next decision

The new [external beat-reference evaluator](../REFERENCE_PROTOCOL.md) can supplement
these reports once independently reviewed beats and clock-mapping evidence are
available. Its synthetic tests verify aggregation and provenance checks; no
reviewed natural-recording annotations were imported in this experiment. Existing
device-reference reports and the earlier frozen evaluation remain unchanged.

Keep this gate offline. Next evaluation needs externally reviewed references,
motion/occlusion cases that test rejection safety, and a fresh cohort after the
sampling/gating protocol is frozen. Neither higher coverage nor the small
accepted-set error on subject 10 justifies a default change yet.

The optional [photometric guard and artifact stress suite](PHOTOMETRIC_GUARD.md)
tests broad RGB-step exclusions separately. Its default is disabled, and its
known gradual/periodic lighting blind spots are documented.
