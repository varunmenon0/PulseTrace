"""Compare raster mask area steps with continuous landmark polygon area steps."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from pulsetrace.regions import REGIONS, extract_regions
from pulsetrace.tracking import FaceTracker


def diagnose(video, model, max_frames=450):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not np.isfinite(fps) or fps <= 0:
        cap.release()
        raise ValueError('Cannot open video with a valid frame rate')
    rows, events = [], []
    try:
        with FaceTracker(str(model)) as tracker:
            for i in range(max_frames):
                ok, frame = cap.read()
                if not ok:
                    break
                landmarks = tracker.detect(frame, i / fps)
                if landmarks is None:
                    continue
                _, counts, _ = extract_regions(frame, landmarks)
                areas = {name: float(cv2.contourArea(cv2.convexHull(
                    landmarks[list(indices)].astype(np.float32))))
                    for name, indices in REGIONS.items()}
                row = dict(frame=i, time_s=i / fps, pixels=counts,
                           continuous_polygon_area=areas)
                if rows and rows[-1]['frame'] == i - 1:
                    prev = rows[-1]
                    for name in counts:
                        if prev['pixels'][name] <= 0 or prev['continuous_polygon_area'][name] <= 0:
                            continue
                        raster = abs(counts[name] / prev['pixels'][name] - 1)
                        continuous = abs(areas[name] / prev['continuous_polygon_area'][name] - 1)
                        if raster > .1:
                            events.append(dict(frame=i, region=name,
                                raster_relative_step=raster, continuous_relative_step=continuous))
                rows.append(row)
    finally:
        cap.release()
    return dict(frames_with_landmarks=len(rows), frames=rows, area_events=events,
        limitation='Continuous hull area is a diagnostic, not the eroded raster mask area or a signal-quality label.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--model', type=Path, default=Path('models/face_landmarker.task'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-frames', type=int, default=450)
    args = parser.parse_args()
    if args.max_frames < 1:
        parser.error('--max-frames must be positive')
    result = diagnose(args.video, args.model, args.max_frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
