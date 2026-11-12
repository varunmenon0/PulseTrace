import numpy as np
import pytest
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.quality import analyze_segments


def fixture():
    t=np.arange(0,35,1/30)
    rgb=np.column_stack([100+np.sin(2*np.pi*1.2*t)*a for a in (1,2,.5)])
    return Extraction(t,{n:rgb.copy() for n in REGIONS},{n:np.full(len(t),100.) for n in REGIONS},None,{}, {},{n:np.zeros((len(t),5)) for n in REGIONS})


def test_sneeze_splits_and_retains_both_sides():
    e=fixture(); i=np.argmin(abs(e.time-17))
    e.geometry['forehead'][i,2]=.2
    r=analyze_segments(e)
    assert len(r['excluded_intervals'])==1
    assert len(r['segments'])==2
    assert all(s['status']=='eligible' for s in r['segments'])
    assert r['segments'][0]['end_s']<16.5
    assert r['segments'][1]['start_s']>17.5
    assert np.isfinite(e.rgb['forehead']).all()
    assert all(abs(s['regions']['forehead']['green']['bpm_candidate']-72)<2 for s in r['segments'])


def test_missing_single_frame_is_never_bridged():
    e=fixture();e.pixels['left_cheek'][510]=0
    r=analyze_segments(e,buffer_seconds=0)
    assert len(r['segments'])==2


def test_insufficient_footage_and_geometry():
    e=fixture();e.geometry['forehead'][:,2]=.2
    assert analyze_segments(e)['status']=='insufficient_usable_footage'
    e.geometry={}
    with pytest.raises(ValueError,match='geometry'):analyze_segments(e)


def test_area_jump_excludes_all_regions():
    e=fixture();e.pixels['left_cheek'][510:]=150
    r=analyze_segments(e)
    assert r['event_counts']['left_cheek']['area_spike_frames']==1
    assert len(r['segments'])==2
