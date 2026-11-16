import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from render_public_demo import active_window


def test_demo_never_displays_future_or_reuses_a_rejected_estimate():
    windows=[dict(start_s=0,end_s=12,bpm_candidate=72),dict(start_s=6,end_s=18,bpm_candidate=None),
             dict(start_s=12,end_s=24,bpm_candidate=80)]
    assert active_window(windows,11.9) is None
    assert active_window(windows,12)['bpm_candidate']==72
    assert active_window(windows,18)['bpm_candidate'] is None
    assert active_window(windows,24)['bpm_candidate']==80
