# Public natural-video heart-rate check

PulseTrace's scope is estimating heart rate from facial video. This is an
exploratory check, not clinical validation or deepfake classification.

## Input and access

UBFC-rPPG Dataset 2 subject1: 640x480 AVI, 1,547 frames, nominal 29.264106 FPS,
about 53 seconds. The accompanying file has waveform, device BPM, and elapsed
seconds. Official source:
https://sites.google.com/view/ybenezeth/ubfcrppg
Mirror used:
https://huggingface.co/datasets/thachha901/UBFC

The official Drive sample videos were quota-blocked and the OneDrive link
redirected to sign-in. The video/reference were downloaded from the public
mirror. Mirror identity was not independently matched against official checksums.
Hashes, byte sizes and exact URLs are in examples/ubfc-subject1/source.json.
Do not redistribute recordings in this repository.

## Reproduce

Use an isolated Python 3.12 environment, install the project, then:

```bash
python -m pip install 'mediapipe==0.10.21'
python scripts/download_model.py
python scripts/download_ubfc_sample.py --output outputs/ubfc-subject1
python scripts/benchmark_ubfc.py --video outputs/ubfc-subject1/vid.avi --reference outputs/ubfc-subject1/ground_truth.txt --model models/face_landmarker.task --output outputs/ubfc-subject1/benchmark
```

Linux also needs libgles2, libegl1 and libgl1. MediaPipe 0.10.35 crashed natively
with "corrupted double-linked list" in two environments on this recording.
An isolated 0.10.21 environment completed. This identifies a reproducible
compatibility issue, not a proven root cause. Benchmark dependencies are recorded
in examples/ubfc-subject1/requirements-benchmark.txt; the project-wide default
dependency range has not been changed on the basis of one run.

## Method

Seven overlapping 12-second windows, spaced six seconds apart, identical for
three-region and 12-patch layouts. No rescaling/re-encoding, expected-BPM peak
selection, or threshold tuning. POS and green are both reported. Consensus rules
are the same as patches.py; no value is forced for rejected windows.

Reference BPM is interpolated on the elapsed-time grid and summarized by window
median. Duplicate reference timestamps are averaged. Shared time origin
(offset=0) is an assumption consistent with the paired dataset structure, not
independently verified hardware synchronization. This does not validate waveform
shape or pulse transit timing.

## Results

| Method/layout | Accepted windows | Exploratory MAE (BPM) |
| --- | --- | --- |
| POS, 3 regions | 6/7 | 2.591 |
| POS, 12 patches | 5/7 | 1.112 |
| Green, 3 regions | 4/7 | 2.072 |
| Green, 12 patches | 6/7 | 2.669 |

These averages include different accepted windows. The saved JSON also reports
a paired comparison using only windows accepted by both layouts. On four
shared POS windows, errors were 1.570 BPM (three regions) and 1.373 BPM (12
patches). On four shared green windows, errors were 2.072 and 2.089 BPM.
The matched-window POS advantage is modest, and green is essentially tied.

The existing motion/area gate rejects five windows, leaving two eligible.
POS returns 2/7 total windows for three regions and 1/7 for 12 patches after this
gate. Green returns 1/7 and 2/7 respectively. Lower error on this small retained
subset cannot establish superiority. The gate's coverage loss needs investigation,
including overlays and separate motion versus patch-area rejection analysis.

Next: repeat across independent subjects, verify reference/video alignment more
closely, inspect area-trigger exclusions, and report failures and coverage.
Do not calibrate the gate to make this subject pass.

See [PUBLIC_VALIDATION_MULTI.md](PUBLIC_VALIDATION_MULTI.md) for the subsequent three-recording development check and reference-dropout policy.
