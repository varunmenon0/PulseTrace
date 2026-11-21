import importlib.util
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(scope='module')
def audit():
    path=Path(__file__).parents[1]/'scripts/audit_stream_session.py'
    spec=importlib.util.spec_from_file_location('session_audit',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_overlapping_tied_majorities_are_explained_without_changing_the_vote(audit):
    values=[100.,100.5,101.5,103.,103.2,104.3,105.2,105.5,105.6]
    candidates={str(i):v for i,v in enumerate(values)}
    zones={str(i):str(i%3) for i in range(len(values))}
    result=audit.cluster_audit(candidates,zones)
    assert result['rejection_reason']=='tied_largest_majorities'
    assert result['largest_qualifying_group']==7
    assert result['equally_large_groups']==2
    assert len(result['shared_patches_in_all_best_groups'])==6
    assert result['decision']['bpm_candidate'] is None
    assert list(candidates.values())==values


def test_insufficient_majority_and_accepted_unique_group_are_separate(audit):
    candidates={'a':100.,'b':101.,'c':140.,'d':141.}
    zones={'a':'x','b':'y','c':'x','d':'y'}
    result=audit.cluster_audit(candidates,zones)
    assert result['rejection_reason']=='no_strict_cross_region_majority'
    result=audit.cluster_audit({'a':100.,'b':101.,'c':102.,'d':140.},
                               {'a':'x','b':'y','c':'x','d':'y'})
    assert result['rejection_reason'] is None
    assert result['decision']['bpm_candidate']==101.


def test_spectral_observation_reports_peaks_and_keeps_constants_uninformative(audit):
    t=np.arange(0,12,1/30)
    spectrum=audit.scalar_spectrum(t,np.sin(2*np.pi*2*t),t,30.)
    assert spectrum['peaks'][0]['bpm']==pytest.approx(120.,abs=2)
    near=audit.power_near(spectrum['frequencies'],spectrum['power'],120.)
    far=audit.power_near(spectrum['frequencies'],spectrum['power'],80.)
    assert near > far
    constant=audit.scalar_spectrum(t,np.ones(len(t)),t,30.)
    assert constant['peaks']==[]
    assert audit.power_near(constant['frequencies'],constant['power'],120.) is None
    broken=np.ones(len(t));broken[10]=np.nan
    assert audit.scalar_spectrum(t,broken,t,30.) is None


def test_audit_uses_separate_output_and_preserves_input_folder(audit,tmp_path):
    with pytest.raises(ValueError,match='separate output'):
        audit.run(tmp_path/'samples.jsonl',tmp_path/'stream.jsonl',tmp_path)


def test_only_runtime_capture_metadata_is_removed_from_replay_comparison(audit):
    row=dict(type='window',bpm=100.,status='estimate',quality={'signal':'fixture'},
             capture_timing={'acquired_frames':30},emitted_at_s=13.,computation_seconds=.1)
    result=audit.canonical_windows([row])
    assert result==[dict(type='window',bpm=100.,status='estimate',quality={'signal':'fixture'})]
    assert 'capture_timing' in row
