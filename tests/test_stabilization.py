import cv2
import numpy as np
from pulsetrace.stabilization import TemplateStabilizer, ANCHORS
from pulsetrace.regions import REGIONS
from pulsetrace.synthetic import make_video, SyntheticTracker
from pulsetrace.pipeline import extract_video


def test_pose_preserved_local_jitter_removed_and_reset():
    rng=np.random.default_rng(4)
    p=rng.uniform(30,100,(478,2)); tracker=TemplateStabilizer()
    assert np.allclose(tracker.apply(p),p)
    transform=np.array([[1.1,.2],[-.2,1.1]])
    expected=p@transform+[10,20]; noisy=expected.copy()
    noisy[list(REGIONS['forehead'])]+=5
    actual=tracker.apply(noisy)
    assert np.allclose(actual[list(REGIONS['forehead'])],expected[list(REGIONS['forehead'])])
    tracker.reset()
    assert np.allclose(tracker.apply(noisy),noisy)
    assert tracker.apply(np.full((478,2),np.nan)) is None


def test_overlay_has_all_frames_including_missing(tmp_path):
    video=tmp_path/'input.avi'; out=tmp_path/'tracking.avi'
    make_video(video,seconds=10)
    class Missing:
        def detect(self,*args): return None
    result=extract_video(video,Missing(),overlay_path=out)
    capture=cv2.VideoCapture(str(out)); count=0
    while capture.read()[0]: count+=1
    capture.release()
    assert count==len(result.time)==300
    assert all(np.isnan(v).all() for v in result.rgb.values())


def test_template_rejects_degenerate_anchors():
    assert TemplateStabilizer().apply(np.zeros((478,2))) is None


def test_template_video_recovers_injected_pulse(tmp_path):
    from pulsetrace.pipeline import analyze_extraction
    video=tmp_path/'input.avi'
    make_video(video,seconds=12,bpm=72)
    class Anchored(SyntheticTracker):
        def detect(self,bgr,time):
            p=super().detect(bgr,time)
            for i,point in zip(ANCHORS,[(50,40),(65,40),(95,40),(110,40),(80,70),(80,50)]):
                p[i]=point
            return p
    result=extract_video(video,Anchored(),sampling='template',overlay_path=tmp_path/'overlay.avi')
    pulses,failures=analyze_extraction(result)
    assert not failures
    assert all(abs(p.bpm-72)<2 for p in pulses.values())
    assert result.metadata['sampling']=='template'
