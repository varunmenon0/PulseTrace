"""MediaPipe Tasks video tracker. Requires an official Face Landmarker asset."""
from pathlib import Path
import cv2
import numpy as np


class FaceTracker:
    def __init__(self, model_path: str | Path):
        if not Path(model_path).is_file():
            raise ValueError(f"Face model missing: {model_path}. See README model setup.")
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        self.mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=2,  # Reject ambiguous multi-person frames instead of switching faces.
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)
        self.last_ms = -1

    def detect(self, bgr: np.ndarray, time: float) -> np.ndarray | None:
        timestamp_ms = max(round(time * 1000), self.last_ms + 1)
        self.last_ms = timestamp_ms
        rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        result = self.detector.detect_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), timestamp_ms
        )
        if len(result.face_landmarks) != 1:
            return None
        h, w = bgr.shape[:2]
        return np.array([(p.x * (w - 1), p.y * (h - 1))
                         for p in result.face_landmarks[0]], dtype=np.float64)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.detector.close()
