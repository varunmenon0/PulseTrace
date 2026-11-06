# Overlay and experimental template sampling

From the inner `pulsetrace` directory, activate your environment and reinstall:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

Use your original video and downloaded model. With network access disabled as
before for personal footage, run both modes into separate fresh directories:

```bash
pulsetrace analyze recording2.mov --model models/face_landmarker.task --output outputs/baseline-overlay --sampling landmarks --overlay
pulsetrace analyze recording2.mov --model models/face_landmarker.task --output outputs/template-overlay --sampling template --overlay
```

Both use POS for the whole-clip report and also export green/POS window diagnostics.
A command may exit with status 2 when no pulse candidate passes; reports and
video are still produced. Run the second command independently.

Open `tracking.avi` locally in each output directory. Gray outlines show raw
landmark polygons. Green contours show the actual inset sampled masks. The
video contains the subject's face; do not commit it or upload it unless intended.
It has no audio. Playback uses constant source FPS, while labels show decoded
video timestamps; variable-frame-rate playback is only approximate.

Template mode fits a 2-D similarity transform from the first valid face to the
current eye/nose anchors using least squares. Region shapes stay fixed relative
to that template. Missing detection, invalid fitting, or a timestamp gap over
0.25 seconds resets the template. The next valid frame initializes a new template.
No past-frame smoothing, RGB correction, skin/hair classification, optical flow,
or heart-rate-based peak selection is performed. The baseline remains default.

This may reduce independent polygon deformation. It cannot correct shared
tracker translation, exposure changes, occlusion, or out-of-plane head rotation.
A least-squares fit is sensitive to anchor outliers. Extreme relative scale
fits are rejected (0.5 to 2); these are engineering limits, not validated quality
criteria. Geometry diagnostics in template mode describe the sampled polygons,
not the raw landmarks; lower shape-change metrics alone do not prove improvement.

Compare full-clip and window rejection/coverage as well as BPM estimates. Do
not select a method because it matches the expected 60-80 range. Quantitative
accuracy needs a synchronized independent reference. No automatic clean-interval
selection or new quality rejection rules have been introduced in this release.

Send `diagnostics.json`, `diagnostics.png`, and `rgb.csv` from both new runs.
Inspect the overlay at 9-10 seconds and 13-19 seconds locally to see whether the
outlines follow actual face movement or slip across the skin. Existing CSVs
cannot be resampled: the original video must be processed locally.
