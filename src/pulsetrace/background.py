"""Explicit fixed background ROI measurements; never a skin classifier."""
import numpy as np


def validate_roi(roi):
    values=np.asarray(roi,float)
    if (values.shape!=(4,) or not np.isfinite(values).all() or
        (values[:2]<0).any() or (values[2:]<=0).any() or
        values[0]+values[2]>1 or values[1]+values[3]>1):
        raise ValueError('Background ROI must be X Y WIDTH HEIGHT fractions within the image')
    return tuple(float(v) for v in values)


def sample_background(bgr, landmarks, roi, min_pixels=30):
    x,y,width,height=validate_roi(roi)
    h,w=bgr.shape[:2]
    left,top=int(np.floor(x*w)),int(np.floor(y*h))
    right,bottom=min(w,int(np.ceil((x+width)*w))),min(h,int(np.ceil((y+height)*h)))
    result=dict(status='unavailable',reason=None,rgb=np.full(3,np.nan),pixels=0,
                bounds=[left,top,right,bottom])
    if landmarks is None:
        result['reason']='face_not_tracked';return result
    points=np.asarray(landmarks)
    if points.ndim!=2 or points.shape[1]!=2 or not len(points) or not np.isfinite(points).all():
        result['reason']='invalid_face_geometry';return result
    low,high=points.min(axis=0),points.max(axis=0)
    if (high<=low).any():
        result['reason']='invalid_face_geometry';return result
    pad=.1*(high-low)
    low,high=low-pad,high+pad
    if left<high[0] and right>low[0] and top<high[1] and bottom>low[1]:
        result['reason']='face_overlaps_background';return result
    if (right-left)*(bottom-top)<min_pixels:
        result['reason']='insufficient_pixels';return result
    result.update(status='available',rgb=bgr[top:bottom,left:right].mean(axis=(0,1))[::-1],
                  pixels=(right-left)*(bottom-top))
    return result
