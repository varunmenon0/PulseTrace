import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from pulsetrace.extraction_experiments import METHODS, analyze_variant
from pulsetrace.signal import analyze


@pytest.fixture(scope='module')
def comparison():
    path=Path(__file__).parents[1]/'scripts/compare_extraction.py'
    spec=importlib.util.spec_from_file_location('extraction_comparison',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def protocol():
    path=Path(__file__).parents[1]/'examples/extraction-experiments/protocol.json'
    return json.loads(path.read_text())


@pytest.mark.parametrize('method',METHODS)
@pytest.mark.parametrize('bpm',[48,72,100,140,180])
def test_recovers_clean_rates_on_irregular_dropped_samples(comparison,protocol,method,bpm):
    t,rgb=comparison.fixture(protocol,bpm,15,'clean','jitter_drop',37)
    original=rgb.copy()
    result=analyze_variant(t,rgb,method)
    assert result.bpm==pytest.approx(bpm,abs=2)
    assert np.isfinite(result.pulse).all()
    np.testing.assert_array_equal(rgb,original)


@pytest.mark.parametrize('method',METHODS)
def test_flat_signals_abstain_and_short_signals_fail(method):
    t=np.arange(600)/30
    rgb=np.full((600,3),100.)
    assert analyze_variant(t,rgb,method).bpm is None
    with pytest.raises(ValueError):analyze_variant(t[:30],rgb[:30],method)


@pytest.mark.parametrize('method',['green','pos'])
def test_existing_methods_are_exactly_preserved(comparison,protocol,method):
    t,rgb=comparison.fixture(protocol,140,30,'common_light','jitter_drop',19)
    baseline=analyze(t,rgb,method=method)
    actual=analyze_variant(t,rgb,method)
    assert actual.bpm==baseline.bpm
    assert actual.warnings==baseline.warnings
    assert actual.peak_fraction==baseline.peak_fraction
    for field in ('time','pulse','frequencies','power'):
        np.testing.assert_array_equal(getattr(actual,field),getattr(baseline,field))


@pytest.mark.parametrize('source',[lambda rgb,fs:np.zeros((len(rgb),2)),
                                  lambda rgb,fs:np.full(len(rgb),np.nan)])
def test_malformed_research_source_is_rejected(source):
    t=np.arange(600)/30
    with pytest.raises(ValueError,match='finite vector'):
        analyze(t,np.full((600,3),100.),_source=source)


def test_scoring_keeps_abstentions_separate_from_error(comparison):
    rows=[dict(injected_bpm=100,estimates={'m':dict(bpm=bpm)}) for bpm in (None,101,120)]
    result=comparison.metrics(rows,'m')
    assert result['cases']==3 and result['abstained']==1
    assert result['coverage']==pytest.approx(2/3)
    assert result['accepted_mae_bpm']==10.5
    assert result['accepted_errors_over_5_bpm']==1
    assert comparison.metrics(rows[:1],'m')['accepted_mae_bpm'] is None


@pytest.mark.parametrize('policy',['full','continuous'])
def test_archive_comparison_preserves_votes_support_and_motion_exclusions(comparison,tmp_path,policy):
    from pulsetrace.live import configuration
    from pulsetrace.sample_archive import SampleWriter
    from pulsetrace.streaming import PulseStream
    from test_streaming import samples
    data=list(samples(26))
    for s in data:
        if 18.09<s.time<18.12:
            for region in ('left_cheek','right_cheek'):s.geometry[region][2]=.1
    engine=PulseStream(window_policy=policy)
    readings=[]
    path=tmp_path/'samples.jsonl'
    with SampleWriter(path,dict(configuration=configuration(engine),synthetic=True)) as writer:
        for s in data:
            writer.write(s)
            readings.extend(engine.push(s))
    result=comparison.natural(path,METHODS)
    assert len(result['windows'])==len(readings)==3
    for row,reading in zip(result['windows'],readings):
        vote=row['methods']['pos']['consensus']
        assert vote['bpm_candidate']==reading.bpm
        assert tuple(vote['support'])==reading.support
        if policy=='continuous':
            assert row['analysis_start_s']==reading.analysis_start_s
            assert row['analysis_end_s']==reading.analysis_end_s
    assert not result['windows'][1]['usable_regions']['left_cheek'] or policy=='continuous'
