import cv2
import numpy as np
import pytest
from pulsetrace.regions import region_mask, mean_rgb, extract_regions, REGIONS
from pulsetrace.synthetic import make_video, SyntheticTracker
from pulsetrace.video import VideoReader
from pulsetrace.pipeline import extract_video, analyze_extraction


def test_rgb_order_and_polygon():
    bgr=np.full((30,30,3),[10,20,30],np.uint8)
    points=np.array([[5,5],[25,5],[25,25],[5,25]])
    mask=region_mask(bgr.shape,points,(0,1,2,3))
    assert np.array_equal(mean_rgb(bgr,mask),[30,20,10])
    assert not mask[0,0] and mask[15,15]


@pytest.mark.parametrize('points',[np.zeros((4,2)), np.full((4,2),np.nan),np.array([[-1,5],[25,5],[25,25],[5,25]])])
def test_bad_regions(points):
    with pytest.raises(ValueError): region_mask((30,30,3),points,(0,1,2,3))


def test_empty_mask():
    with pytest.raises(ValueError): mean_rgb(np.zeros((30,30,3)),np.zeros((30,30)))


def test_video_integration(tmp_path):
    video=tmp_path/'fixture.avi'
    make_video(video,bpm=96,seconds=12)
    with VideoReader(video) as reader:
        frames=list(reader)
        assert len(frames)==360
        assert reader.fps==30
        assert np.all(np.diff([f.time for f in frames])>0)
    extraction=extract_video(video,SyntheticTracker())
    results,failures=analyze_extraction(extraction)
    assert not failures
    for name in REGIONS:
        assert extraction.rgb[name].shape==(360,3)
        assert extraction.geometry[name].shape==(360,5)
        assert np.isnan(extraction.geometry[name][0,2])
        assert np.allclose(extraction.geometry[name][1:,2:4],0)
        assert extraction.pixels[name].min()>30
        assert abs(results[name].bpm-96)<2


def test_missing_faces_not_stale(tmp_path):
    video=tmp_path/'fixture.avi'
    make_video(video,seconds=10)
    class MissingTracker:
        def detect(self, bgr, time): return None
    extraction=extract_video(video,MissingTracker())
    assert all(np.isnan(rgb).all() for rgb in extraction.rgb.values())
    results,failures=analyze_extraction(extraction)
    assert not results and len(failures)==3


def test_missing_video(tmp_path):
    with pytest.raises(ValueError): VideoReader(tmp_path/'missing.mp4')


def test_invalid_video(tmp_path):
    path=tmp_path/'invalid.mp4'
    path.write_bytes(b'not a video')
    with pytest.raises(ValueError): VideoReader(path)
