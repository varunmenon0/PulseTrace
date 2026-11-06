"""Experimental rigid-template patches following current face pose, without temporal lag."""
import numpy as np
from .regions import REGIONS

ANCHORS = (33, 133, 362, 263, 1, 168)

class TemplateStabilizer:
    """Fit a least-squares similarity transform; reset on detection gaps.

    This reduces independent polygon deformation, not global tracking error.
    No RGB values or expected heart rates enter the fit.
    """
    def __init__(self):
        self.template = None

    def reset(self):
        self.template = None

    def apply(self, landmarks):
        points = np.asarray(landmarks, dtype=float)
        if not np.isfinite(points).all():
            self.reset()
            return None
        anchors = points[list(ANCHORS)]
        if self.template is None:
            if np.linalg.norm(anchors-anchors.mean(axis=0)) < 1e-6:
                return None
            self.template = points.copy()
        source = self.template[list(ANCHORS)]
        # x' = a*x - b*y + tx; y' = b*x + a*y + ty
        matrix = np.zeros((2*len(source),4))
        matrix[0::2] = np.column_stack((source[:,0],-source[:,1],np.ones(len(source)),np.zeros(len(source))))
        matrix[1::2] = np.column_stack((source[:,1],source[:,0],np.zeros(len(source)),np.ones(len(source))))
        fit, _, rank, _ = np.linalg.lstsq(matrix, anchors.ravel(), rcond=None)
        a,b,tx,ty = fit
        if rank < 4 or not .5 <= np.hypot(a,b) <= 2:
            self.reset()
            return None
        result = points.copy()
        for indices in REGIONS.values():
            p = self.template[list(indices)]
            result[list(indices)] = p @ np.array([[a,b],[-b,a]]) + [tx,ty]
        return result
