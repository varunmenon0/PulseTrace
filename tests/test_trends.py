import copy
import csv
import json

import pytest

from pulsetrace.trends import build_trend, write_trend


def report():
    windows=[]
    for start, bpm in ((0,72.), (6,None), (12,84.)):
        detail=dict(bpm_candidate=bpm,support=['forehead_tl','left_cheek_tl'] if bpm is not None else [])
        windows.append(dict(start_s=start,end_s=start+12,usable_regions=dict(forehead=True,left_cheek=True,right_cheek=False),
                            methods={m:dict(twelve_patches=dict(regional_gate=copy.deepcopy(detail))) for m in ('green','pos')}))
    return dict(configuration=dict(window_seconds=12,step_seconds=6),windows=windows)


def test_missing_windows_remain_in_json_csv_and_coverage(tmp_path):
    source=report();original=copy.deepcopy(source)
    result=write_trend(source,tmp_path)
    assert source==original
    assert result['metrics']['pos']==dict(total_windows=3,estimated_windows=2)
    assert result['windows'][1]['methods']['pos']['bpm_candidate'] is None
    assert result['windows'][0]['center_s']==6
    assert result['windows'][0]['available_at_s']==12
    with (tmp_path/'pulse_trend.csv').open() as file:
        rows=list(csv.DictReader(file))
    assert rows[1]['pos_bpm']=='' and len(rows)==3


def test_out_of_order_windows_are_rejected():
    source=report();source['windows'].reverse()
    with pytest.raises(ValueError):build_trend(source)


def test_cli_tracks_a_phase_continuous_ramp(tmp_path):
    from pulsetrace.cli import main
    output=tmp_path/'ramp'
    assert main(['demo','--profile','clean','--bpm','72','--end-bpm','90','--seconds','18',
                 '--patches','--consensus','zone','--track','--output',str(output)])==0
    result=json.loads((output/'pulse_trend.json').read_text())
    assert len(result['windows'])==2
    for row in result['windows']:
        expected=72+row['center_s']
        for method in ('green','pos'):
            assert abs(row['methods'][method]['bpm_candidate']-expected)<2
    assert (output/'patch_comparison.json').is_file()
    metadata=json.loads((output/'summary.json').read_text())['metadata']
    assert metadata['rate_trajectory']['end_bpm']==90
    assert metadata['expected_bpm'] is None


@pytest.mark.parametrize('args', [['demo','--track'], ['demo','--end-bpm','90']])
def test_cli_rejects_incomplete_tracking_options(args):
    from pulsetrace.cli import main
    with pytest.raises(SystemExit):main(args)
