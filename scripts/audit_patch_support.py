"""Controlled geometry-scale and lattice study; no RGB or BPM-based selection."""
import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from compare_subpixel import sha256
from pulsetrace.regions import REGIONS
from pulsetrace.subpixel import fractional_masks
from pulsetrace.tracking import FaceTracker
from pulsetrace.video import VideoReader


def summarize(areas, reference):
    """Each row holds one parent area and its four patch areas, in pixels."""
    areas, reference = np.asarray(areas), np.asarray(reference)
    if areas.shape != reference.shape or areas.ndim != 2 or areas.shape[1] != 5 or not len(areas):
        raise ValueError('Need matching nonempty parent-plus-four-patch area rows')
    parent, patches = areas[:, 0], areas[:, 1:]
    eligible = parent >= 120
    incomplete = (patches < 30).any(axis=1)
    difference = np.abs(areas - reference)
    return dict(region_frames=len(areas), patch_observations=4 * len(areas),
                unavailable_patches=int((patches < 30).sum()),
                complete_region_frames=int((~incomplete).sum()),
                parents_below_four_patch_minimum=int((~eligible).sum()),
                incomplete_despite_parent_area_at_least_120=int((eligible & incomplete).sum()),
                patch_areas_within_half_pixel_of_threshold=int((np.abs(patches - 30) <= .5).sum()),
                minimum_patch_area=float(patches.min()),
                max_parent_area_difference_from_16=float(difference[:, 0].max()),
                max_patch_area_difference_from_16=float(difference[:, 1:].max()),
                median_patch_area_difference_from_16=float(np.median(difference[:, 1:])))


def measure(samples):
    if not samples:
        raise ValueError('No tracked geometry samples')
    measurements = {}
    for scale in (.5, 1., 1.5):
        for partition in ('bbox', 'equal_area'):
            for subdivisions in (4, 8, 16):
                rows = []
                for sample in samples:
                    h, w = sample['shape']
                    scaled_shape = (round(h * scale), round(w * scale), 3)
                    # Image resize convention: map pixel centers, not corners.
                    ratio = np.array([scaled_shape[1] / w, scaled_shape[0] / h])
                    for indices in REGIONS.values():
                        points = (sample['landmarks'][list(indices)] + .5) * ratio - .5
                        try:
                            parent, patches = fractional_masks(scaled_shape, points,
                                subdivisions=subdivisions, partition=partition)
                            rows.append([parent.area] + [p.area for p in patches.values()])
                        except ValueError:
                            rows.append([0.] * 5)
                measurements[scale, partition, subdivisions] = rows
    return [dict(scale=scale, partition=partition, subdivisions=subdivisions,
                 **summarize(rows, measurements[scale, partition, 16]))
            for (scale, partition, subdivisions), rows in measurements.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stride', type=int, default=30)
    args = parser.parse_args()
    if args.stride < 1:
        parser.error('--stride must be positive')
    samples = []
    decoded = 0
    with FaceTracker(args.model) as tracker, VideoReader(args.video) as reader:
        for frame in reader:
            decoded += 1
            landmarks = tracker.detect(frame.bgr, frame.time)
            if frame.index % args.stride == 0 and landmarks is not None:
                samples.append(dict(frame=frame.index, time_s=frame.time,
                                    shape=frame.bgr.shape[:2], landmarks=landmarks))
    report = dict(
        experiment='Controlled geometry scaling on one development recording, not multi-resolution video validation',
        configuration=dict(stride=args.stride, scales=[.5, 1., 1.5], subdivisions=[4, 8, 16],
                           square_inset_pixels=1, minimum_patch_area=30),
        input=dict(video_sha256=sha256(args.video), model_sha256=sha256(args.model),
                   decoded_frames=decoded, tracked_sample_frames=len(samples),
                   sample_frame_indices=[s['frame'] for s in samples]),
        versions={n: importlib.metadata.version(n) for n in ('numpy', 'opencv-contrib-python', 'mediapipe')},
        limitations=['Landmarks are tracked at native resolution, then scaled with pixel-center coordinates',
                     'RGB pixels are not resampled; no claim about tracking or pulse quality at altered resolution',
                     'The 16x16 lattice is a numerical comparator, not exact coverage or ground truth',
                     'A parent needs at least 120 coverage pixels to support four patches of area 30',
                     'Changing patch boundaries can change sampled tissue even with balanced areas'],
        configurations=measure(samples))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
