# Experimental 12-patch comparison

After installing with `python -m pip install -e '.[dev]'`:

```sh
python -m pulsetrace demo --patches --output outputs/patch-demo
python -m pulsetrace analyze recording2.mov --model models/face_landmarker.task --patches --output outputs/patch-test
```

The flag adds 12 traces (four non-overlapping image-space quadrants inside
each forehead and cheek mask) while preserving the original three-region
outputs. Both layouts use the same decoded frames, parent masks, motion
exclusions, intervals, filters, and POS/green analysis. No model is needed
for the synthetic demo. Existing averaged RGB CSVs cannot reconstruct patches.

Open `patch_comparison.json` for per-interval results and `patch_rgb.csv` for
raw traces and pixel counts. A patch under the minimum 30 pixels is unavailable.
Each patch needs valid samples throughout the interval; the existing spectral
quality checks can also withhold its candidate. Consensus requires a strict
majority of accepted candidates within a 5 BPM span across at least two
parent zones. The reported estimate weights each supporting zone equally.
No consensus returns exit status 2 but still writes reports. The optional
tracking video shows parent outlines. These masks do not segment hair or
confirm skin visibility.

The original motion pass still excludes shared intervals for both layouts.
The report is exploratory: nearby patches can share artifacts, and clean
synthetic recovery does not establish better real-video accuracy. Compare
absolute BPM error and valid-interval coverage with a synchronized reference.
