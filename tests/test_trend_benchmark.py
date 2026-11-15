import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from benchmark_pulse_trends import score_windows, summarize
from benchmark_motion_recovery import recovery_metrics


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


def test_recovery_reports_availability_and_failed_motion_exclusions():
    rows = []
    for start, shared, bpm in ((12, True, None), (18, True, 72), (24, False, None), (30, False, 72)):
        rows.append(dict(start_s=start, available_at_s=start+12, shared_motion_or_loss=shared,
            methods={m:dict(bpm_candidate=bpm) for m in ('green', 'pos')}))
    result = recovery_metrics(dict(fixture=dict(motion=dict(event_interval_s=[20,22])), windows=rows))
    for method in ('green', 'pos'):
        assert result[method]['shared_motion_windows_with_estimate'] == 1
        assert result[method]['first_recovered_window_start_s'] == 30
        assert result[method]['first_recovered_estimate_available_at_s'] == 42
        assert result[method]['availability_delay_after_event_s'] == 20
    missing = recovery_metrics(dict(fixture=dict(motion=dict(event_interval_s=[20,22])), windows=[]))
    assert missing['pos']['availability_delay_after_event_s'] is None
