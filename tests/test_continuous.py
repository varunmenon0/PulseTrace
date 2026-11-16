import numpy as np
import pytest

from pulsetrace.continuous import select_interval
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.patches import PATCHES
from pulsetrace.regional_quality import write_regional_comparison
from pulsetrace.trends import build_trend


def fixture():
    t=np.arange(0,18,1/30)
    rgb=np.column_stack([100+a*np.sin(2*np.pi*1.2*t) for a in (1,2,.5)])
    return Extraction(t,{n:rgb.copy() for n in REGIONS},{n:np.full(len(t),100.) for n in REGIONS},
        None,{}, {},{n:np.zeros((len(t),5)) for n in REGIONS},
        {n:rgb.copy() for n in PATCHES},{n:np.full(len(t),30.) for n in PATCHES})


def test_late_disruption_uses_clean_support_and_preserves_default(tmp_path):
    e=fixture()
    for n in REGIONS:e.geometry[n][345,2]=.2
    full=write_regional_comparison(e,tmp_path)
    shorter=write_regional_comparison(e,tmp_path,window_policy='continuous')
    assert full['windows'][0]['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate'] is None
    row=shorter['windows'][0]
    assert row['analysis_start_s']==0 and 10 < row['analysis_end_s'] < 11.1
    assert abs(row['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate']-72)<1
    trend=build_trend(shorter)['windows'][0]
    assert trend['available_at_s']==12
    assert trend['center_s']==row['analysis_end_s']/2
    assert (tmp_path/'regional_comparison.json').exists()
    assert (tmp_path/'continuous_comparison.json').exists()


def test_short_sections_are_never_joined():
    t=np.arange(0,12,.1);mask=np.zeros(len(t),bool);mask[55:65]=True
    indices,usable=select_interval(t,{n:mask.copy() for n in REGIONS},np.ones(len(t),bool))
    assert not len(indices) and not any(usable.values())


def test_at_least_two_fixed_zones_must_share_the_whole_interval():
    t=np.arange(0,12,.1);masks={n:np.zeros(len(t),bool) for n in REGIONS}
    masks['forehead'][60:]=True;masks['left_cheek'][:60]=True
    indices,_=select_interval(t,masks,np.ones(len(t),bool))
    assert not len(indices)  # Two zones per frame is insufficient if the pair changes.


def test_timestamp_gap_cannot_be_bridged():
    t=np.r_[np.arange(0,6,.1),np.arange(7,13,.1)]
    indices,_=select_interval(t,{n:np.zeros(len(t),bool) for n in REGIONS},np.ones(len(t),bool))
    assert not len(indices)


@pytest.mark.parametrize('seconds',[0,-1,float('nan')])
def test_invalid_selection_settings(seconds):
    t=np.arange(0,12,.1)
    with pytest.raises(ValueError):
        select_interval(t,{n:np.zeros(len(t),bool) for n in REGIONS},np.ones(len(t),bool),min_seconds=seconds)


def test_cli_requires_tracking_for_continuous_policy():
    from pulsetrace.cli import main
    with pytest.raises(SystemExit):main(['demo','--patches','--window-policy','continuous'])
