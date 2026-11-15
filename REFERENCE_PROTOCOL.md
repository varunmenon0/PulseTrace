# External beat-reference evaluation

PulseTrace's existing UBFC scores compare stored device BPM labels. The contact
waveform audit is exploratory and has not replaced those labels. Subject 14's
large device/waveform disagreement remains unresolved.

## Primary-source findings

The [official UBFC page](https://sites.google.com/view/ybenezeth/ubfcrppg) describes
Logitech C920 acquisition and CMS50E reference waveform/heart-rate data. That
page alone does not establish the exact clock mapping of our mirrored files.

Gudi, Bittner and van Gemert's
[CleanerPPG paper](https://doi.org/10.3390/app10238630) describes human-reviewed
beat annotations, including UBFC, and states that research access can be requested
from the authors. Those annotations have not been obtained or imported here.
Their presence in the literature is a route to better reference checking, not
verification of PulseTrace's current labels or scores.

## Implemented adapter

`evaluate_peak_reference.py` reads externally supplied beat times and supplements
an area-gate comparison report. It requires:

- A CSV with a `time_s` column, in seconds, finite and strictly increasing.
- A provenance JSON naming the annotation source and the exact video SHA256.
- An explicitly supplied clock offset: reference time = video time + offset.

Example provenance structure:

```json
{
  "video_sha256": "<SHA256 of the annotated recording>",
  "source": "<annotation publisher, version, and source location>",
  "time_unit": "seconds",
  "alignment_evidence": "<how the reference/video clock mapping was established>"
}
```

The required source/hash/units are checked by the loader; extra annotation and
alignment evidence is preserved for inspection. The tool cannot independently
verify user-supplied provenance. Frames or sample indices need conversion to
seconds using documented acquisition timing before import.

For each video window, beats must bracket both mapped edges. The reference BPM
is the time-weighted mean of 60/RR across the complete window, counting partial
interval overlaps at the edges. Intervals outside the existing 40–200 BPM range
make the window unscorable; missing beats are not bridged. Incomplete edge
coverage also remains unscorable. This deliberately differs from a device-label
median or a spectral peak and is reported as a separate reference protocol.

```sh
python scripts/evaluate_peak_reference.py \
  --report outputs/area-gates/subject14.json \
  --peaks path/to/externally-reviewed-beats.csv \
  --provenance path/to/provenance.json \
  --reference-offset <externally-established-offset-in-seconds> \
  --output outputs/external-reference-evaluation.json
```

The adapter preserves original device labels and reports. Peak timing, source
selection, and offsets are not optimized against video estimates. Output records
input hashes, supplied provenance, offset, aggregation method, reference-valid
window counts, failures, and supplemental errors. A supplied metadata claim is
not automatic certification of annotation quality or synchronization.

Tests use known synthetic beats to check clock offsets, time-weighted interval
rates, coverage, missing-beat rejection, recording identity, and preservation of
original scores. No natural-video accuracy result against reviewed beat
annotations is claimed yet.
