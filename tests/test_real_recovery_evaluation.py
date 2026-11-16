import sys
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from evaluate_real_recovery import reference_window, summarize


def test_reference_uses_actual_support_and_rejects_invalid_labels():
    time=np.arange(0,20,.1);bpm=60+time
    assert reference_window(time,bpm,2,12)==67
    assert reference_window(time,bpm,4,12)==68
    bpm[50]=0
    assert reference_window(time,bpm,2,12) is None
    assert reference_window(time,bpm,None,None) is None


def test_reference_gaps_and_uncovered_edges_are_unscorable():
    time=np.r_[np.arange(0,5,.1),np.arange(8,20,.1)]
    assert reference_window(time,np.full(len(time),72.),0,12) is None
    assert reference_window(time,np.full(len(time),72.),-1,3) is None


def test_summary_keeps_failed_windows_and_reports_common_and_added_errors():
    windows=[]
    for full,continuous in ((1.,2.),(None,4.),(None,None)):
        row=dict(nominal_reference_bpm=72.,policies={})
        for policy,error in (('full',full),('continuous',continuous)):
            row['policies'][policy]=dict(methods={m:{l:dict(error_bpm=error,
                bpm_candidate=None if error is None else 72+error,
                rejection_reason='quality_exclusions' if error is None else None)
                for l in ('three_regions','twelve_patches')} for m in ('pos','green')})
        windows.append(row)
    result=summarize([dict(windows=windows)])['pos']['twelve_patches']
    assert result['full']['scorable_windows']==1
    assert result['continuous']['scorable_windows']==2
    assert result['continuous']['reference_valid_windows']==3
    assert result['paired']['full_common_mae']==1
    assert result['paired']['continuous_common_mae']==2
    assert result['paired']['newly_scorable_errors_bpm']==[4.]
