import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('benchmark_ubfc',Path(__file__).parents[1]/'scripts/benchmark_ubfc.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_reference_repeated_timestamps_are_averaged(tmp_path):
    p=tmp_path/'ground_truth.txt'
    np.savetxt(p,[[1,2,3,4],[70,72,74,76],[0,.1,.1,.2]])
    t,b=module.load_reference(p)
    assert np.allclose(t,[0,.1,.2])
    assert np.allclose(b,[70,73,76])


def test_bad_reference_clock_rejected(tmp_path):
    p=tmp_path/'ground_truth.txt'
    np.savetxt(p,[[1,2,3],[70,72,74],[0,.2,.1]])
    with pytest.raises(ValueError):module.load_reference(p)


def test_summary_keeps_failures_and_uses_paired_windows():
    import copy
    spec=importlib.util.spec_from_file_location('summary',Path(__file__).parents[1]/'scripts/summarize_benchmarks.py')
    summary=importlib.util.module_from_spec(spec);spec.loader.exec_module(summary)
    def row(base,patch):
        methods={m:{'three_regions':{'error_bpm':base},'twelve_patches':{'error_bpm':patch}} for m in ('pos','green')}
        return {'reference_bpm':70,'motion_excluded':False,'methods':methods}
    result=summary.summarize({'a':{'windows':[row(1,2),row(None,4)]},'b':{'windows':[row(9,None)]}})
    r=result['metrics']['pos']
    assert r['three_regions_all_windows']['compared_windows']==2
    assert r['three_regions_all_windows']['coverage_of_all_windows']==pytest.approx(2/3)
    assert r['twelve_patches_all_windows']['mean_subject_mae_bpm']==3
    assert r['twelve_patches_all_windows']['subjects_with_estimates']==1
    assert r['paired_all_windows']=={'common_windows':1,'three_regions':1,'twelve_patches':2}


def test_reference_dropout_is_unscorable_not_a_large_error():
    from pulsetrace.pipeline import Extraction
    from pulsetrace.regions import REGIONS
    from pulsetrace.patches import PATCHES
    t=np.arange(0,25,1/30)
    rgb=np.column_stack([100+np.sin(2*np.pi*1.2*t)*a for a in (1,2,.5)])
    e=Extraction(t,{n:rgb.copy() for n in REGIONS},{n:np.full(len(t),100.) for n in REGIONS},
                 None,{}, {},{n:np.zeros((len(t),5)) for n in REGIONS},
                 {n:rgb.copy() for n in PATCHES},{n:np.full(len(t),30.) for n in PATCHES})
    rt=np.arange(0,25,.1);rb=np.full(len(rt),72.);rb[(rt>7)&(rt<8)]=2
    r=module.compare(e,rt,rb)
    assert r['windows'][0]['reference_bpm'] is None
    assert r['windows'][0]['methods']['pos']['three_regions']['error_bpm'] is None
    assert '40-200' in r['windows'][0]['reference_warning']
    assert r['windows'][2]['reference_bpm']==72.
