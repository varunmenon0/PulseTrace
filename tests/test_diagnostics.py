import json
import numpy as np
import pytest
from pulsetrace.diagnostics import geometry_sample, inspect_extraction, load_rgb_csv, window_estimates
from pulsetrace.pipeline import Extraction
from pulsetrace.regions import REGIONS
from pulsetrace.cli import main


def example(seconds=30):
    t=np.arange(seconds*30)/30
    pulse=np.sin(2*np.pi*1.2*t)
    rgb=np.array([160,110,80])+pulse[:,None]*np.array([.6,3,.2])
    return Extraction(t,{n:rgb.copy() for n in REGIONS},
                      {n:np.full(len(t),1000.) for n in REGIONS},None,{}, {})


def test_translation_separate_from_shape():
    before=np.array([[0.,0.],[10.,0.],[0.,10.]])
    after=before+[3,4]
    row=geometry_sample(after,(0,1,2),before,100)
    assert row[2]==pytest.approx(.05)
    assert row[3]==pytest.approx(0)
    assert np.isnan(geometry_sample(after,(0,1,2),None,100)[2])


def test_shape_deformation_detected():
    before=np.array([[0.,0.],[10.,0.],[0.,10.]])
    after=before.copy(); after[0]+=[5,0]
    assert geometry_sample(after,(0,1,2),before,100)[3]>0


def test_area_and_broad_jump_are_observations():
    e=example()
    e.pixels['forehead'][200:]*=1.3
    e.rgb['forehead'][201:]*=.94
    report,_=inspect_extraction(e)
    events=report['regions']['forehead']['events']
    assert any('area_jump' in r['flags'] for r in events)
    assert any('broad_rgb_jump' in r['flags'] for r in events)
    assert report['regions']['forehead']['motion_available'] is False


def test_missing_frame_does_not_create_jump():
    e=example(); e.rgb['forehead'][200]=np.nan; e.pixels['forehead'][200]=0
    report,_=inspect_extraction(e)
    assert not report['regions']['forehead']['events']


def test_known_pulse_windows():
    e=example()
    for method in ('green','pos'):
        rows=window_estimates(e.time,e.rgb['forehead'],method=method)
        assert len(rows)==4
        assert all(abs(row['bpm_candidate']-72)<2 for row in rows)


def test_window_frequency_switch():
    e=example(seconds=36)
    t=e.time
    phase=2*np.pi*np.where(t<18,1.2*t,1.2*18+2*(t-18))
    rgb=np.array([160,110,80])+np.sin(phase)[:,None]*np.array([.6,3,.2])
    rows=window_estimates(t,rgb,method='green')
    assert abs(rows[0]['bpm_candidate']-72)<2
    assert abs(rows[-1]['bpm_candidate']-120)<2


def test_motion_unavailable_and_missing_data_json_safe():
    e=example(); e.rgb['forehead'][:]=np.nan; e.pixels['forehead'][:]=0
    report,_=inspect_extraction(e)
    json.dumps(report,allow_nan=False)
    assert report['regions']['forehead']['pixel_count_range'] is None


def test_legacy_csv_and_cli(tmp_path):
    e=example()
    path=tmp_path/'rgb.csv'
    header=['time_s']+[f'{n}_{c}' for n in REGIONS for c in ('r','g','b','pixels')]
    values=np.column_stack([e.time]+[v for n in REGIONS for v in (*e.rgb[n].T,e.pixels[n])])
    np.savetxt(path,values,delimiter=',',header=','.join(header),comments='')
    loaded=load_rgb_csv(path)
    assert not loaded.geometry
    output=tmp_path/'report'
    assert main(['diagnose',str(path),'--output',str(output)])==0
    assert (output/'diagnostics.png').exists()
    assert (output/'windows.csv').exists()
    assert not (output/'tracking.png').exists()


@pytest.mark.parametrize('window,step',[(9,6),(12,0),(float('nan'),6)])
def test_invalid_window_configuration(window,step):
    e=example()
    with pytest.raises(ValueError):
        window_estimates(e.time,e.rgb['forehead'],method='pos',window_seconds=window,step_seconds=step)


def test_invalid_csv(tmp_path):
    path=tmp_path/'bad.csv'; path.write_text('time_s,foo\n0,1\n1,2\n')
    with pytest.raises(ValueError): load_rgb_csv(path)
