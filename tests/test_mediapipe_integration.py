"""Optional inference test; asset paths are explicit, no automatic network calls."""
import os
from pathlib import Path
import cv2
import numpy as np
import pytest
from pulsetrace.tracking import FaceTracker
from pulsetrace.pipeline import extract_video, analyze_extraction
from pulsetrace.regions import extract_regions


@pytest.mark.skipif(not (os.environ.get('PULSETRACE_TEST_MODEL') and os.environ.get('PULSETRACE_TEST_PORTRAIT')),
                    reason='Set model and portrait environment paths for actual MediaPipe inference')
def test_actual_model_video_pipeline(tmp_path):
    model=Path(os.environ['PULSETRACE_TEST_MODEL'])
    image=cv2.imread(os.environ['PULSETRACE_TEST_PORTRAIT'])
    assert image is not None
    image=cv2.resize(image,(410,512))
    with FaceTracker(model) as tracker:
        landmarks=tracker.detect(image,0)
        assert landmarks is not None and landmarks.shape==(478,2)
        _,counts,_=extract_regions(image,landmarks)
        assert all(count>30 for count in counts.values())
        assert tracker.detect(np.zeros_like(image),1) is None
    video=tmp_path/'portrait_injected.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(410,512))
    assert writer.isOpened()
    try:
        for i in range(360):
            t=i/30
            pulse=np.sin(2*np.pi*1.2*t)
            frame=np.clip(image.astype(float)+pulse*np.array([.2,3,.6]),0,255).astype(np.uint8)
            shift=2*np.sin(2*np.pi*.1*t)
            frame=cv2.warpAffine(frame,np.float32([[1,0,shift],[0,1,0]]),(410,512))
            writer.write(frame)
    finally:
        writer.release()
    with FaceTracker(model) as tracker:
        extraction=extract_video(video,tracker)
    results,failures=analyze_extraction(extraction)
    assert not failures
    for name,result in results.items():
        assert np.mean(extraction.pixels[name]>0)>.95
        assert result.bpm is not None and abs(result.bpm-72)<3
