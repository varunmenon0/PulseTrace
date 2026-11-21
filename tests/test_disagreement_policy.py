import json

import numpy as np
import pytest

from pulsetrace.agreement import method_agreement
from pulsetrace.live import configuration, replay_samples
from pulsetrace.sample_archive import SampleWriter
from pulsetrace.streaming import PulseStream
from test_streaming import samples


def fake_window(monkeypatch, pairs):
    import pulsetrace.streaming
    calls = iter(pairs)
    def build(extraction, **options):
        pos,green = next(calls)
        start = options['window_starts'][0]
        return {'windows':[dict(start_s=start,end_s=start+12,analysis_start_s=start,
            analysis_end_s=start+11.9,usable_regions={n:True for n in extraction.rgb},quality={},
            methods={m:{'twelve_patches':{'regional_gate':dict(bpm_candidate=bpm,
                        support=['forehead_tl','left_cheek_tl'] if bpm is not None else [])}}
                     for m,bpm in [('pos',pos),('green',green)]})]}
    monkeypatch.setattr(pulsetrace.streaming,'build_regional_comparison',build)


@pytest.mark.parametrize('method,expected',[('pos',100.),('green',104.)])
def test_agreeing_methods_keep_selected_method_without_averaging(monkeypatch,method,expected):
    fake_window(monkeypatch,[(100.,104.)])
    engine = PulseStream(method=method,agreement_policy='flag')
    readings = [r for s in samples(13) for r in engine.push(s)]
    assert readings[0].bpm == expected
    assert readings[0].to_dict()['bpm'] == expected
    assert engine.state()['bpm'] == expected
    assert readings[0].to_dict()['quality']['method_agreement']['status'] == 'agreement'


def test_uncertain_window_clears_previous_display_and_preserves_raw_values(monkeypatch):
    fake_window(monkeypatch,[(100.,101.),(104.,120.)])
    engine = PulseStream(agreement_policy='flag')
    readings = []
    for s in samples(20):
        new = engine.push(s)
        readings.extend(new)
        if len(readings)==1:
            assert engine.state()['bpm'] == 100.
    raw = readings[1]
    row = raw.to_dict()
    assert raw.bpm == 104. and raw.status == 'estimate'
    assert row['bpm'] is None and row['status'] == 'uncertain'
    assert row['raw_bpm'] == 104. and row['raw_status'] == 'estimate'
    assert row['unavailable_reason'] == 'method_disagreement'
    check = row['quality']['method_agreement']
    assert check['pos_bpm'] == 104. and check['green_bpm'] == 120.
    assert check['difference_bpm'] == 16.
    assert engine.state()['status'] == 'uncertain' and engine.state()['bpm'] is None
    assert engine.estimated_windows == 2 and engine.uncertain_windows == 1
    assert readings[0].to_dict()['bpm'] == 100.  # Later uncertainty never revises a finalized reading.
    row['quality']['method_agreement']['pos_bpm'] = 1
    assert raw.to_dict()['quality']['method_agreement']['pos_bpm'] == 104.


@pytest.mark.parametrize('pos,green,status,bpm',[(100.,None,'estimate',100.),
    (None,100.,'unavailable',None),(None,None,'unavailable',None)])
def test_missing_method_does_not_force_agreement_or_switch_estimators(monkeypatch,pos,green,status,bpm):
    fake_window(monkeypatch,[(pos,green)])
    engine = PulseStream(agreement_policy='flag')
    for s in samples(13):engine.push(s)
    assert engine.state()['status'] == status and engine.state()['bpm'] == bpm
    assert engine.latest.to_dict()['quality']['method_agreement']['status'] == 'insufficient_estimates'
    assert engine.uncertain_windows == 0


def test_tolerance_boundary_and_disabled_policy(monkeypatch):
    assert method_agreement(100.,105.)['status'] == 'agreement'
    assert method_agreement(100.,105.001)['status'] == 'method_disagreement'
    fake_window(monkeypatch,[(100.,130.)])
    engine = PulseStream(agreement_policy='off')
    for s in samples(13):engine.push(s)
    assert engine.state()['bpm'] == 100.
    assert 'raw_bpm' not in engine.latest.to_dict()
    assert 'method_agreement' not in engine.latest.to_dict()['quality']
    with pytest.raises(ValueError):PulseStream(agreement_policy='unknown')


def test_archive_restores_flag_policy_and_reports_raw_vs_display_counts(tmp_path,monkeypatch):
    path=tmp_path/'capture'/'samples.jsonl'
    engine=PulseStream(agreement_policy='flag')
    fake_window(monkeypatch,[(100.,120.)])
    original=[]
    with SampleWriter(path,dict(configuration=configuration(engine),synthetic=True)) as archive:
        for s in samples(13):
            archive.write(s);original.extend(engine.push(s))
    fake_window(monkeypatch,[(100.,120.)])
    output=tmp_path/'replayed'
    summary=replay_samples(path,output)
    assert summary['estimated_windows']==0 and summary['raw_estimated_windows']==1
    assert summary['uncertain_windows']==1
    rows=[r for line in (output/'stream.jsonl').read_text().splitlines()
          if (r:=json.loads(line))['type']=='window']
    assert rows==[json.loads(json.dumps(r.to_dict())) for r in original]
    records=path.read_text().splitlines();header=json.loads(records[0])
    header['metadata']['configuration']['agreement_tolerance_bpm']=6.
    records[0]=json.dumps(header);path.write_text('\n'.join(records)+'\n')
    with pytest.raises(ValueError,match='tolerance'):
        replay_samples(path,tmp_path/'mismatch')


def test_legacy_archives_remain_unflagged_until_explicitly_overridden(tmp_path,monkeypatch):
    config=configuration(PulseStream())
    config.pop('agreement_policy');config.pop('agreement_tolerance_bpm')
    path=tmp_path/'capture'/'samples.jsonl'
    with SampleWriter(path,dict(configuration=config,synthetic=True)) as archive:
        for s in samples(13):archive.write(s)
    fake_window(monkeypatch,[(100.,120.)])
    legacy=replay_samples(path,tmp_path/'legacy')
    assert legacy['estimated_windows']==1 and legacy['uncertain_windows']==0
    fake_window(monkeypatch,[(100.,120.)])
    flagged=replay_samples(path,tmp_path/'flagged',agreement_policy='flag')
    assert flagged['estimated_windows']==0 and flagged['raw_estimated_windows']==1
    assert flagged['uncertain_windows']==1
