# Motion exclusion and independent sections

Run from the inner project folder after activating your environment:

```bash
python -m pip install -e '.[dev]'
python -m pulsetrace segments outputs/baseline-overlay/rgb.csv --output outputs/baseline-segments
python -m pulsetrace segments outputs/template-overlay/rgb.csv --output outputs/template-segments
```

No model, internet, or video is needed for existing CSVs with geometry columns.
Each command writes `segments.json` and prints the results. Status 2 means
insufficient usable footage, not a crash. Run the commands separately.
New `analyze` runs also write this report. Existing whole-clip summaries,
waveforms and diagnostics remain unmasked baseline outputs; use `segments.json`
for the motion-excluded results. Raw RGB is never changed.

Any region's frame displacement above 0.05 face units or patch area change above
10% flags the frame for all regions. Missing samples also flag a frame. A
0.5-second buffer on both sides removes adjacent contaminated frames. Every
remaining continuous section is reported; each section at least 10 seconds long
is analyzed independently with both POS and green. Shorter sections are listed
as too_short. There is no interpolation across an excluded frame, concatenation,
longest-only selection, or overall BPM aggregation. Filters operate separately
inside each retained section and retain their existing edge trim.

These are unvalidated engineering thresholds, not calibrated motion detection.
They can reject good footage and miss artifacts, especially if patches remain
consistently outside the face. Color spikes are not used as a rejection trigger
because pulse itself is a color signal. No expected heart-rate range enters
selection. Inspect overlays and compare to a synchronized reference before
claiming accuracy. This pass does not reset or rerun the tracker; reinitializing
tracking after motion remains future work.

On the uploaded baseline CSV, 36.4% of frames are excluded, leaving no section
of at least 10 seconds (longest about 9.24 seconds). On the template CSV, 32.2%
are excluded and 19.79-30.32 seconds remain eligible. Eligibility alone is not
proof of pulse or proof that template sampling is superior. Thresholds were not
adjusted to make these clips produce an estimate.
