# Research archive

These reports preserve earlier development experiments, intermediate baselines,
and validation history. Their results belong to the settings and cohorts stated
in each report. For the current project overview and latest evaluation, start
with the [documentation index](../README.md).

## Earlier real-video evaluations

- [Initial public-video check](PUBLIC_VALIDATION.md)
- [Three-recording development check](PUBLIC_VALIDATION_MULTI.md)
- [Frozen-rule check on subjects 12–14](FROZEN_EVALUATION.md)
- [Validation and environment history](VALIDATION.md)

## Sampling and quality experiments

- [Twelve-patch comparison](PATCHES.md)
- [Region-balanced voting](ZONE_CONSENSUS.md)
- [Per-region quality gates](REGIONAL_QUALITY.md)
- [Motion exclusions and independent sections](SEGMENTS.md)
- [Template sampling and overlays](STABILIZATION.md)
- [Fractional coverage sampling](SUBPIXEL_SAMPLING.md)
- [Geometry-balanced patch support](PATCH_SUPPORT.md)
- [Paired balanced-sampling evaluation](SAMPLING_EVALUATION.md)
- [Area-source gate comparison](AREA_GATE_EVALUATION.md)
- [Photometric artifact guard](PHOTOMETRIC_GUARD.md)

## Reference and failure investigations

- [Subject 14 diagnosis](SUBJECT14_DIAGNOSIS.md)
- [Contact-reference audit](CONTACT_REFERENCE_AUDIT.md)

Supporting data remain under [`examples/`](../../examples/) so historical evidence,
test fixtures, and reproduction commands keep their original paths. Commands
in these reports are run from the repository root.
