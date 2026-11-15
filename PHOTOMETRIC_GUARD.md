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
