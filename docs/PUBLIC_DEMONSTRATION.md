# Real-video demonstration and frozen five-recording check

PulseTrace now has a reproducible annotated demonstration from a real public
webcam recording. It shows the 12 sampled facial patches, a normalized POS
waveform from a supported patch, completed-window BPM, the matching device-label
reference, and a pulse trend. The estimator is the same frozen implementation
used in the preceding real-video study.

The demonstration is **68.47 seconds at 1440×900**, encoded as H.264 at 15 presentation
FPS. Its complete source recording yields **10/10 scorable windows**. The source
is a development recording selected for presentation under an explicit rule,
separate from the five new benchmark recordings below. The curated [demo](../assets/PulseTrace-Demo.mp4) and [preview](../assets/demo-preview.png)
are included at the repository owner’s request. Raw recordings and detailed
measurement reports remain local. The repository also contains reproducible code,
protocols, source manifests, and cohort aggregates.

## Completed full-length checks

The two outstanding development recordings were processed in full with paired
integer/fractional extraction, using identical landmarks and verified timestamps.
Fractional sampling yielded pulse estimates throughout one recording, while the
other remained unavailable because the spectral candidates did not support a
cross-region consensus. The remaining failure is signal/voting support, rather
than wholesale rejection for rasterized area steps.

The [development aggregate](../examples/public-demonstration/development-aggregate.json)
retains both full and continuous policies, POS and green, and the three-parent
comparison. It is separate from all fresh-cohort results.

## Demonstration selection and timing

The [protocol](../examples/public-demonstration/protocol.json) was committed before
new acquisitions. Demo candidates were the four already-seen development clips.
Eligibility required scorable estimates in at least 80% of nominal windows and
accepted-set mean absolute device-label difference at most 5 BPM. Candidates were
ranked by scorable fraction, then mean difference, then recording ID. The complete
selected clip is rendered, including less accurate windows.

The display is explicitly offline and windowed:

- No estimate appears before its 12-second nominal window has ended.
- A newly rejected window clears the previous estimate rather than retaining it.
- The waveform comes from an actually supported patch over the analyzed support.
- The device card is the median reference over that same support, with the
  existing assumed zero elapsed-time offset. Reference data enter only after
  signal estimation.
- The presentation replays the exact landmark pass used to extract its samples.
  The output samples source frames at 15 FPS; labels preserve decoded video time.

The [build summary](../examples/public-demonstration/demo-build.json) records encoding,
timing, frame count, and coverage. FFmpeg is required on PATH to generate MP4 output.

## Frozen five-recording evaluation

The estimator was frozen at commit `44c7d8442fe87bddd3ef0540d17be0c094490911`.
The next five numerically ordered available source directories after subject 18
were selected using directory availability only. Missing directory IDs were
recorded before inspecting signals; failed recordings were not substituted.

All **5/5 acquisitions and extractions completed**, totaling **9,463 decoded
frames**. Every recording produced at least one scorable POS estimate. The
cohort has 49 nominal windows; 36 pass the existing reference-label validity
checks. All 13 reference-invalid windows remain in the total-window count.

| Frozen fractional POS layout | Scorable / reference-valid windows | Estimates / all nominal windows | Accepted-set device-label MAE | Maximum difference |
|---|---:|---:|---:|---:|
| Three parent regions | 31/36 | 42/49 | 4.059 BPM | 15.018 BPM |
| Twelve patches | 28/36 | 34/49 | 3.959 BPM | 15.158 BPM |

Full and continuous window policies returned the same estimates in this cohort.
For twelve-patch POS, seven windows lacked majority consensus, six lacked
sufficient spectral support, and two failed regional quality selection. The
three-parent result yields more readings with similar error, so the evidence
does not establish that more patches are inherently superior.

These results establish a functioning real-video proof of concept with explicit
abstentions. They also identify the next engineering priority: inspect large
accepted differences and improve support/reliability diagnostics. Disagreement
may involve video artifacts or reference quality; the existing reference labels
and time offsets were not changed to favor an estimate. Overlapping windows are
dependent, the cohort is small and from the same dataset, and independently
verified clock alignment remains unavailable.

The [frozen aggregate](../examples/public-demonstration/frozen-aggregate.json)
preserves all planned/completed/failure counts, both methods, both layouts, both
policies, rejection counts, and reference-valid denominators. No thresholds,
ROIs, filters, or voting rules were adjusted after fresh outcomes.

## Reproduce

Download the selected development source using its existing manifest:

```bash
python scripts/download_ubfc_sample.py \
  --manifest examples/real-video-recovery/subject16/source.json \
  --output outputs/real-video-recovery/subject16
python scripts/render_public_demo.py \
  --source outputs/real-video-recovery/subject16 \
  --model models/face_landmarker.task --output outputs/public-demo
```

The downloader verifies source checksums, reuses complete verified files, and
writes `source.json` beside them. The renderer writes the MP4, preview, extraction,
and detailed measurement report locally. It rejects a demonstration that does
not meet the protocol's minimum coverage/reference-agreement rule.

Download each of the five sources using the manifests in
[the evaluation directory](../examples/public-demonstration), then run paired
sampling for each:

```bash
python scripts/benchmark_real_sampling.py \
  --source outputs/public-demonstration/subject20 \
  --model models/face_landmarker.task --output outputs/public-frozen-sampling
```

After all five extractions, evaluate without changing estimator settings:

```bash
python scripts/complete_public_study.py \
  --root outputs/public-frozen-sampling/fractional --cohort fresh \
  --output outputs/public-demonstration/frozen
```

This writes an aggregate suitable for the repository and a separate local
`private-results.json`. Failures remain explicit rather than being replaced by
easier recordings. Source videos, models, caches, annotated recordings, and
individual pulse measurements stay outside the public repository.
