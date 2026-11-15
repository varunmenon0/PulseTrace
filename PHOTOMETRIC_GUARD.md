# Optional photometric artifact guard

`regional_masks(..., photometric_threshold=.02)` adds an independent region-level
exclusion when at least two RGB channels change by more than 2% in the same
direction between consecutive valid samples. The existing diagnostics already
used this RGB-step magnitude; it was not selected by matching subject BPM.
The guard uses the same 0.5-second buffer and complete-window parent exclusions
as the existing regional gate. It leaves RGB untouched and bridges no missing
samples. Displacement, area, and shared-motion/loss checks remain in force.

The default is `None` (disabled). This heuristic identifies abrupt broad color
steps, not occlusion, skin identity, or pulse validity. Gradual changes, small
occluders, and periodic interference can evade it. Recoverable illumination
changes can also be rejected. It is currently exposed only in offline experiments.

## Reproduce the experiments

```sh
python scripts/stress_artifact_gates.py --output outputs/photometric-guard/synthetic.json
python scripts/compare_area_gates.py \
  --video outputs/subject10-video/vid.avi \
  --reference outputs/subject10-video/ground_truth.txt \
  --model models/face_landmarker.task \
  --photometric-guard \
  --output outputs/photometric-guard/subject10.json
```

Repeat the latter for subject14. Acquire public recordings with the existing
checksum-verified source manifests. Both variants use the same fractional RGB
and spectral candidates. The new policy adds color-step exclusions to the
fractional-area gate; the prior integer-area and fractional-area policies are
also retained for comparison. Default sampling/gating is unchanged.

The stress suite has seven deterministic RGB/geometry cases: clean, shared
motion, one-region sample loss, abrupt local attenuation, shared exposure step,
gradual color drift, and periodic lighting. It injects a known 72 BPM component;
the periodic lighting case adds 108 BPM common-mode interference. It uses no
video decoder, face model, human physiology, or physical occluder. Attenuation
approximates a color consequence of occlusion and is not an occlusion-detector
benchmark. No threshold or rate-based candidate selection changes between cases.

Tests protect local vote exclusions, unaffected regions, shared-motion behavior,
unchanged RGB, invalid settings, and explicit blind spots. The synthetic
periodic-lighting case deliberately demonstrates that green-channel consensus
can follow the interference while POS follows the injected pulse. That single
control does not establish POS robustness on natural video.

## Controlled trace results

There are three overlapping 12-second windows per 25-second fixture. Counts below
refer to POS consensus with fractional area. Scorable synthetic windows use the
known injected pulse as their fixture reference, not a human measurement.

| Case | Without color guard | With color guard | Observed limitation or behavior |
|---|---:|---:|---|
| Clean | 3/3 | 3/3 | No clean samples flagged |
| Shared motion | 1/3 | 1/3 | Existing buffered rejection preserved |
| One-region loss | 3/3 | 3/3 | Two unaffected parents can still supply consensus |
| Abrupt local attenuation | 3/3 | 3/3 | Affected parent's votes removed; other parents remain |
| Shared exposure step | 3/3 | 1/3 | Two affected windows rejected |
| Gradual color drift | 3/3 | 3/3 | Small consecutive steps evade the guard |
| Periodic lighting | 3/3 | 3/3 | Subthreshold interference evades the guard |

Shared motion rejects 61 buffered frames in every region under either policy.
The exposure step adds 61 rejected frames per region; local attenuation adds
61 only in the left cheek. The clean, gradual, and periodic cases have zero
photometric exclusions. These are controlled cue checks, not measured artifact
detection sensitivity or specificity.

In the periodic-lighting fixture, green estimates approximately 108 BPM in all
three windows, following the lighting component instead of the injected 72 BPM
component. POS estimates approximately 72 BPM in all three. Consensus across
patches does not prove a heartbeat when the same artifact affects every patch.
Conversely, the exposure-step fixture's underlying pulse remains recoverable by
POS without the guard: rejecting its windows shows conservative behavior, not
proof that an unguarded estimate was wrong.

## Natural development replay

Both previous unguarded policies reproduce their earlier per-window decisions
exactly on subjects 10 and 14. The new policy uses identical fractional RGB,
spectral candidates, and thresholds, adding only the optional RGB-step exclusions.
The table shows 12-patch POS regional decisions against stored device BPM.

| Recording | Unguarded scorable windows | Guarded scorable windows | Common windows | Unguarded common difference | Guarded common difference |
|---|---:|---:|---:|---:|---:|
| Subject 10 | 8/10 | 10/10 | 8 | 1.918 BPM | 1.888 BPM |
| Subject 14 | 9/10 | 8/10 | 8 | 11.491 BPM | 11.347 BPM |

Removing votes can create a unique majority among those that remain. Thus a
stricter sample gate does not guarantee fewer output estimates. Subject 10 gains
two scorable windows with mean device-label difference 4.706 BPM and maximum
7.299 BPM. Its guarded accepted-set mean is 2.452 BPM, compared with 1.918 across
the unguarded eight-window set. Subject 14 loses one window whose device-label
difference was 17.278 BPM. Its guarded eight-window mean is 11.347 BPM.

These changes do not establish an accuracy improvement. The device-reference
and alignment uncertainties remain, and the small common-window differences are
not independent statistical evidence. This remains development data; no new
held-out cohort, physical occlusion test, or reviewed beat reference was used.

## Decision

Keep the color guard disabled by default. It catches the designed abrupt steps
and retains the existing motion/loss behavior, but misses gradual and periodic
interference and changes consensus membership. Raw traces stay unchanged.
The complete numeric synthetic and natural reports, including gained/lost
windows, source hashes, versions, settings, and all candidates, are preserved in
`examples/photometric-guard/`.

Next tests need physical occlusion and changing-illumination videos with an
independently checked reference. The periodic-lighting fixture should remain a
regression case for future quality/consensus work. Existing production defaults,
device-label reports, and the earlier frozen evaluation remain unchanged.
