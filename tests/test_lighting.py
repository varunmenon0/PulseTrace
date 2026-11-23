import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from pulsetrace.lighting import build_reference, screen_candidate


def reference(frequency=1.5):
    t=np.arange(600)/30
    rgb=np.array([120.,100.,80.])+np.sin(2*np.pi*frequency*t)[:,None]*[2.,1.,3.]
    return t,rgb


def test_overlapping_light_is_withheld_without_replacing_raw_candidate():
    t,rgb=reference();original=rgb.copy()
    result=build_reference(t,rgb)
    decision=screen_candidate(90.,result)
    assert decision['status']=='lighting_overlap'
    assert decision['raw_bpm']==90. and decision['bpm'] is None
    assert max(decision['channel_power_fractions'])>.5
    far=screen_candidate(150.,result)
    assert far['status']=='no_overlap_observed' and far['bpm']==150.
    np.testing.assert_array_equal(rgb,original)
    with pytest.raises(ValueError):result.spectra[0][1][0]=0


def test_multiple_light_frequencies_and_non_green_channel_are_checked():
    t,rgb=reference()
    rgb[:]=100.
    rgb[:,0]+=2*np.sin(2*np.pi*1.2*t)
    rgb[:,2]+=2*np.sin(2*np.pi*2.6*t)
    result=build_reference(t,rgb)
    assert screen_candidate(72.,result)['status']=='lighting_overlap'
    assert screen_candidate(156.,result)['status']=='lighting_overlap'
    assert screen_candidate(110.,result)['status']=='no_overlap_observed'


@pytest.mark.parametrize('kind',['missing','nan','short','gap','duplicate','shape','nonnumeric'])
def test_missing_or_bad_reference_withholds_instead_of_claiming_clear(kind):
    t,rgb=reference()
    if kind=='missing':rgb=None
    elif kind=='nan':rgb[50,0]=np.nan
    elif kind=='short':t,rgb=t[:20],rgb[:20]
    elif kind=='gap':t[300:]+=1
    elif kind=='duplicate':t[50]=t[49]
    elif kind=='shape':rgb=rgb[:,:2]
    elif kind=='nonnumeric':rgb='invalid'
    result=build_reference(t,rgb)
    assert result.status=='unavailable'
    assert screen_candidate(90.,result)['status']=='reference_unavailable'
    assert screen_candidate(90.,result)['bpm'] is None
    assert screen_candidate(None,result)['status']=='no_candidate'


def test_flat_background_is_available_but_is_not_called_pulse_validation():
    t,rgb=reference();rgb[:]=100.
    decision=screen_candidate(90.,build_reference(t,rgb))
    assert decision['status']=='no_overlap_observed'
    assert decision['channel_power_fractions']==[0.,0.,0.]


@pytest.mark.parametrize('candidate',[0,-1,39.,201.,float('nan'),float('inf')])
def test_invalid_candidate_fails(candidate):
    with pytest.raises(ValueError):screen_candidate(candidate,build_reference([],None))


@pytest.fixture(scope='module')
def comparison():
    folder=Path(__file__).parents[1]/'scripts'
    # The benchmark shares the original comparison helpers, just as direct CLI execution does.
    import sys
    sys.path.insert(0,str(folder))
    try:
        spec=importlib.util.spec_from_file_location('lighting_comparison',folder/'compare_lighting.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    finally:sys.path.remove(str(folder))
    return module


@pytest.fixture(scope='module')
def protocol():
    return json.loads((Path(__file__).parents[1]/'examples/extraction-experiments/lighting-protocol.json').read_text())


def test_reference_modes_preserve_pairing_and_absent_controls_have_no_leaked_pulse(comparison,protocol):
    t=np.arange(600)/30
    a=comparison.reference_fixture(protocol,t,'two_lights',307,None,'shared_light')
    b=comparison.reference_fixture(protocol,t,'two_lights',307,102,'shared_light')
    np.testing.assert_array_equal(a,b)  # Valid background never receives injected pulse rate.
    face_only=comparison.reference_fixture(protocol,t,'two_lights',307,102,'face_only_light')
    noise=comparison.reference_fixture(protocol,t,'noise_only',307,102,'shared_light')
    np.testing.assert_array_equal(face_only,noise)
    assert comparison.reference_fixture(protocol,t,'clean',307,102,'missing') is None


def test_scoring_reports_correct_readings_lost_and_wrong_ones_removed(comparison):
    def row(ref,raw,screened):
        return dict(injected_bpm=ref,raw={'m':dict(bpm=raw)},screened={'m':dict(bpm=screened)})
    rows=[row(100,101,None),row(140,160,None),row(140,141,141),row(None,126,None)]
    result=comparison.score(rows,'m','screened')
    assert result['cases']==3 and result['estimated']==1
    assert result['correct_lost']==1 and result['correct_retained']==1
    assert result['wrong_removed']==1 and result['wrong_retained']==0
    assert result['pulse_absent_cases']==1 and result['spurious_candidates']==0
    assert result['accepted_mae_bpm']==1


def test_paired_runner_keeps_same_face_estimate_for_every_reference_mode(comparison,protocol):
    p=dict(protocol,base_colors=protocol['base_colors'][:1],
        relative_pulse_colors=protocol['relative_pulse_colors'][:1],rates_bpm=[102],fps=[15],
        profiles=['clean'],negative_controls=['flat'],seeds=[307])
    result=comparison.run(p)
    assert len(result['cases'])==8
    present=[r for r in result['cases'] if r['injected_bpm'] is not None]
    assert len({r['face_sha256'] for r in present})==1
    assert all(r['raw']==present[0]['raw'] for r in present)
    assert result['metrics']['missing']['screened']['green']['estimated']==0
    assert result['metrics']['shared_light']['screened']['green']['correct_retained']==1
