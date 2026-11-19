"""Connect decoding, injectable tracking, regional sampling, and signal analysis."""
from dataclasses import dataclass, field
import numpy as np
import cv2
from contextlib import ExitStack
from pathlib import Path
from .video import VideoReader
from .regions import REGIONS
from .patches import PATCHES
from .signal import analyze, PulseResult


@dataclass
class Extraction:
    time: np.ndarray
    rgb: dict[str, np.ndarray]
    pixels: dict[str, np.ndarray]
    preview: np.ndarray | None
    masks: dict[str, np.ndarray]
    metadata: dict
    geometry: dict[str, np.ndarray] = field(default_factory=dict)


    patch_rgb: dict[str, np.ndarray] = field(default_factory=dict)
    patch_pixels: dict[str, np.ndarray] = field(default_factory=dict)


def extract_video(path, tracker, *, max_seconds=None, min_pixels=30, sampling="landmarks", overlay_path=None, patches=False):
    if max_seconds is not None and (not np.isfinite(max_seconds) or max_seconds <= 0):
        raise ValueError("max_seconds must be positive")
    if min_pixels < 1:
        raise ValueError("min_pixels must be positive")
    if sampling not in ("landmarks", "template", "fractional"):
        raise ValueError("Unknown sampling mode")
    from .sampling import FrameSampler
    sampler = FrameSampler(sampling=sampling, min_pixels=min_pixels, patches=patches)
    patch_rgb = {name: [] for name in PATCHES} if patches else {}
    patch_pixels = {name: [] for name in patch_rgb}
    timestamps = []
    rgb = {name: [] for name in REGIONS}
    pixels = {name: [] for name in REGIONS}
    preview, masks = None, {}
    geometry = {name: [] for name in REGIONS}
    with ExitStack() as stack:
        reader = stack.enter_context(VideoReader(path))
        writer = None
        for frame in reader:
            if max_seconds is not None and frame.time >= max_seconds:
                break
            landmarks = tracker.detect(frame.bgr, frame.time)
            raw_landmarks = landmarks
            sample = sampler.sample(frame.bgr, landmarks, frame.time)
            landmarks, current_masks = sampler.landmarks, sampler.masks
            values, counts = sample.rgb, sample.pixels
            for name in patch_rgb:
                patch_rgb[name].append(sample.patch_rgb[name])
                patch_pixels[name].append(sample.patch_pixels[name])
            for name in REGIONS:
                geometry[name].append(sample.geometry[name])
            if overlay_path is not None:
                if writer is None:
                    Path(overlay_path).parent.mkdir(parents=True, exist_ok=True)
                    h,w = frame.bgr.shape[:2]
                    writer = cv2.VideoWriter(str(overlay_path), cv2.VideoWriter_fourcc(*"MJPG"), reader.fps, (w,h))
                    stack.callback(writer.release)
                    if not writer.isOpened():
                        raise OSError("Cannot open overlay video writer")
                annotated = frame.bgr.copy()
                for name,indices in REGIONS.items():
                    if raw_landmarks is not None:
                        cv2.polylines(annotated,[np.rint(raw_landmarks[list(indices)]).astype(np.int32)],True,(128,128,128),1)
                    if name in current_masks:
                        contours,_ = cv2.findContours(current_masks[name],cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                        cv2.drawContours(annotated,contours,-1,(0,255,0),2)
                cv2.putText(annotated,f"{frame.time:.3f}s {sampling} | gray: raw, green: sampled" + (" | NO SAMPLE" if not current_masks else ""),
                            (10,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,255),1)
                writer.write(annotated)
            if preview is None and len(current_masks) == len(REGIONS):
                preview, masks = frame.bgr.copy(), current_masks
            timestamps.append(frame.time)
            for name in REGIONS:
                rgb[name].append(values[name])
                pixels[name].append(counts[name])
        metadata = {"sampling": sampling, "geometry_describes": "sampled polygons", "overlay_timing": "constant source FPS; labels show decoded timestamps", "source_fps": reader.fps, "timestamp_fallbacks": reader.timestamp_fallbacks,
                    "decoded_frames": len(timestamps)}
    if not timestamps:
        raise ValueError("Video contains no decodable frames")
    if sampling == 'fractional':
        metadata['fractional_sampling'] = dict(subdivisions=8,inset_pixels=1.,partition='equal_area',
            area_units='effective covered pixels; previews show any contributing pixel')
    return Extraction(np.asarray(timestamps), {k: np.asarray(v) for k,v in rgb.items()},
                      {k: np.asarray(v) for k,v in pixels.items()}, preview, masks, metadata, {k:np.asarray(v) for k,v in geometry.items()},
                      {k:np.asarray(v) for k,v in patch_rgb.items()},
                      {k:np.asarray(v) for k,v in patch_pixels.items()})


def analyze_extraction(extraction, **options):
    results: dict[str, PulseResult] = {}
    failures = {}
    for name in REGIONS:
        try:
            results[name] = analyze(extraction.time, extraction.rgb[name], **options)
        except ValueError as exc:
            failures[name] = str(exc)
    return results, failures
