import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from benchmark_pulse_trends import score_windows, summarize


def test_linear_reference_uses_window_center_without_changing_estimates():
    trend=dict(windows=[dict(center_s=6,methods=dict(green=dict(bpm_candidate=75.),pos=dict(bpm_candidate=76.)))])
    original=copy.deepcopy(trend)
    rows=score_windows(trend,dict(start_bpm=72,end_bpm=108,seconds=60))
    assert rows[0]['injected_window_mean_bpm']==pytest.approx(75.6)
    assert rows[0]['errors_bpm']['green']==pytest.approx(-.6)
    assert trend==original


def test_window_summary_keeps_missing_estimates():
    summary=summarize([dict(errors_bpm=dict(green=None,pos=.1)),dict(errors_bpm=dict(green=1.,pos=None))])
    assert summary['green']['total_windows']==2
    assert summary['green']['estimated_windows']==1
    assert summary['green']['coverage']==.5
    assert summary['pos']['mae_against_injected_window_mean']==.1
