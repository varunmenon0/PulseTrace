import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from benchmark_controlled import summarize


def test_controlled_summary_keeps_missing_estimates_and_profiles_separate():
    rows=[dict(case=dict(group='clean'),decoded_frames=600,errors_bpm=dict(green=0.1,pos=None)),
          dict(case=dict(group='clean'),decoded_frames=600,errors_bpm=dict(green=-.3,pos=.2)),
          dict(case=dict(group='lighting_challenge'),decoded_frames=600,errors_bpm=dict(green=36,pos=.1))]
    for row in rows:
        row['estimates']=dict(method_agreement=dict(shared_lighting_cue=row['case']['group']=='lighting_challenge'))
    summary=summarize(rows)
    assert summary['clean']['methods']['pos']['estimated_cases']==1
    assert summary['clean']['methods']['pos']['total_cases']==2
    assert summary['clean']['methods']['pos']['coverage']==.5
    assert summary['lighting_challenge']['methods']['green']['mae_against_injected_bpm']==36
    assert summary['clean']['decoded_frames']==1200
    assert summary['clean']['shared_lighting_cue_cases']==0
    assert summary['lighting_challenge']['shared_lighting_cue_cases']==1
