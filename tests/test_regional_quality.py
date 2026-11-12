import numpy as np
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.regional_quality import regional_masks,gate_candidates
import pytest


def fixture():
    t=np.arange(0,25,1/30)
    return Extraction(t,{n:np.full((len(t),3),100.) for n in REGIONS},
                      {n:np.full(len(t),100.) for n in REGIONS},None,{}, {},
                      {n:np.zeros((len(t),5)) for n in REGIONS})


def test_local_area_preserves_other_zones():
    e=fixture();e.pixels['left_cheek'][300:]=150
    masks,shared=regional_masks(e)
    assert masks['left_cheek'][300] and not shared.any()
    assert not masks['forehead'].any() and not masks['right_cheek'].any()
    assert not masks['left_cheek'][0]


def test_shared_displacement_rejects_every_region_with_buffer():
    e=fixture()
    for n in ('left_cheek','right_cheek'):e.geometry[n][300,2]=.1
    masks,shared=regional_masks(e)
    assert shared[300] and shared[290]
    assert all(m[300] for m in masks.values())
    assert not shared[200]


def test_single_missing_region_does_not_contaminate_others():
    e=fixture();e.pixels['forehead'][300]=0
    masks,shared=regional_masks(e)
    assert masks['forehead'][300] and not masks['left_cheek'][300]
    e.pixels['left_cheek'][300]=0
    masks,shared=regional_masks(e)
    assert shared[300] and masks['right_cheek'][300]


def test_bad_zone_cannot_vote_and_one_zone_is_insufficient():
    zones={n:n for n in REGIONS};c={'forehead':72.,'left_cheek':110.,'right_cheek':73.}
    r=gate_candidates(c,zones,{'forehead':True,'left_cheek':False,'right_cheek':True})
    assert r['bpm_candidate']==72.5 and r['individual_candidates']['left_cheek'] is None
    assert gate_candidates(c,zones,{'forehead':True,'left_cheek':False,'right_cheek':False})['bpm_candidate'] is None


def test_invalid_timing_rejected():
    e=fixture();e.time[2]=e.time[1]
    with pytest.raises(ValueError):regional_masks(e)


def test_reference_failure_never_counts_as_admitted_result():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('regional_evaluation',Path(__file__).parents[1]/'scripts/evaluate_regional_quality.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def row(start):
        return {'start_s':start,'end_s':start+12,'methods':{
            m:{l:{'global_gate':{'bpm_candidate':None},'regional_gate':{'bpm_candidate':72.}}
               for l in ('three_regions','twelve_patches')} for m in ('pos','green')}}
    report={'windows':[row(0),row(6)]}
    refs={'windows':[{'start_s':0,'end_s':12,'reference_bpm':None},
                     {'start_s':6,'end_s':18,'reference_bpm':70.}], 'input':{}}
    result=module.score(report,refs)
    assert result['metrics']['pos']['twelve_patches']['newly_admitted']=={'windows':1,'mae_bpm':2.,'errors_bpm':[2.]}
    refs['windows'].pop()
    with pytest.raises(ValueError):module.score(report,refs)


def test_end_to_end_local_gate_recovers_clean_pair_without_using_bad_region(tmp_path):
    from pulsetrace.patches import PATCHES
    from pulsetrace.regional_quality import write_regional_comparison
    e=fixture();t=e.time
    pulse=np.sin(2*np.pi*1.2*t)
    rgb=np.column_stack([100+a*pulse for a in (1,2,.5)])
    e.rgb={n:rgb.copy() for n in REGIONS}
    e.patch_rgb={n:rgb.copy() for n in PATCHES}
    e.patch_pixels={n:np.full(len(t),30.) for n in PATCHES}
    e.pixels['left_cheek'][300:]=150
    report=write_regional_comparison(e,tmp_path)
    first=report['windows'][0]
    assert first['usable_regions']=={'forehead':True,'left_cheek':False,'right_cheek':True}
    for layout in ('three_regions','twelve_patches'):
        assert first['methods']['pos'][layout]['global_gate']['bpm_candidate'] is None
        assert abs(first['methods']['pos'][layout]['regional_gate']['bpm_candidate']-72)<2
        assert all(not n.startswith('left_cheek') for n in first['methods']['pos'][layout]['regional_gate']['support'])
    assert (tmp_path/'regional_comparison.json').exists()


def test_cli_writes_regional_report(tmp_path,monkeypatch):
    from pulsetrace.synthetic import make_video,SyntheticTracker
    from pulsetrace.cli import main
    import pulsetrace.tracking
    class Tracker(SyntheticTracker):
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(pulsetrace.tracking,'FaceTracker',Tracker)
    video=tmp_path/'input.avi';make_video(video,seconds=12)
    output=tmp_path/'result'
    assert main(['analyze',str(video),'--model','unused.task','--patches','--regional-quality','--output',str(output)])==0
    import json
    report=json.loads((output/'regional_comparison.json').read_text())
    assert abs(report['windows'][0]['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate']-72)<2
