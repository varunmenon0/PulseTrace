# Inspecting contact-reference beat timing

The contact-only audit now exports detected beat times and interbeat intervals
for each complete 12-second reference window. Times refer to the filtered
waveform, after trimming one second from each end to reduce edge artifacts.
No video estimates, expected subject BPM, time shifts, or alternate labels are
used to choose those peaks.

The synthetic regression test uses a known pulse train with 0.8-second spacing
and checks recovered beat times within 70 ms as well as the 75 BPM interval
estimate. Another test confirms that reference gaps are not bridged. These are
algorithm checks, not validation on human contact recordings.

On the checksum-verified subject 14 reference, the first window contains 12
detected positive peaks between 1.467 and 10.333 seconds. The eleven intervals
range from 0.633 to 1.000 seconds; their median is 0.833 seconds (72 BPM). The
spectral estimate is 69 BPM, while the median stored device label is 98 BPM.
This makes the discrepancy inspectable but does not establish its cause.

The timing may reflect changing pulse rate, device averaging, contact artifacts,
filtering, or recording alignment. Positive-peak detection is exploratory and
has not been independently validated on these recordings. The original device
labels and benchmark scores remain unchanged. Hardware synchronization remains
unverified, and a best-fitting video offset must not be treated as validation.

```sh
python scripts/download_ubfc_sample.py \
  --manifest examples/ubfc-heldout/subject14/source.json \
  --output outputs/subject14-video
python scripts/audit_contact_reference.py \
  outputs/subject14-video/ground_truth.txt \
  --output outputs/contact-reference-audit.json
```

The downloader verifies the existing source manifest. The numeric audit output
is preserved at `examples/contact-reference-audit/subject14.json`. Next reference
work needs independent pulse annotation or validated contact processing and
recording synchronization evidence before these estimates can replace labels.
