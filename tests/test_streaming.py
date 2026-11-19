from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from pulsetrace.patches import PATCHES
from pulsetrace.regions import REGIONS
from pulsetrace.regional_quality import build_regional_comparison
from pulsetrace.sampling import Sample, samples_to_extraction
from pulsetrace.streaming import PulseStream


def samples(seconds=44, origin=0.):
    for t in origin+np.arange(0, seconds, 1/30):
        pulse = np.sin(2*np.pi*1.2*t)
        rgb = np.array([100+pulse, 100+2*pulse, 100+.5*pulse])
        yield Sample(float(t), {n: rgb.copy() for n in REGIONS}, {n: 100. for n in REGIONS},
                     {n: np.zeros(5) for n in REGIONS}, {n: rgb.copy() for n in PATCHES},
                     {n: 30. for n in PATCHES})


@pytest.mark.parametrize('policy', ['full', 'continuous'])
@pytest.mark.parametrize('method,consensus', [('pos', 'patch'), ('green', 'zone')])
@pytest.mark.parametrize('origin', [0., 2.3])
def test_rolling_buffer_matches_same_sample_batch_with_future_motion(policy, method, consensus, origin):
    data = list(samples(origin=origin))
    # Motion just AFTER a nominal end must still affect that window's final decision.
    for sample in data:
        if origin+18.09 < sample.time < origin+18.12:
            for n in ('left_cheek', 'right_cheek'):
                sample.geometry[n][2] = .1
    engine = PulseStream(method=method, consensus=consensus, window_policy=policy)
    actual = [r for s in data for r in engine.push(s)]
    baseline = build_regional_comparison(samples_to_extraction(data), consensus_policy=consensus,
                                        window_policy=policy)
    expected = [r for r in baseline['windows'] if r['end_s']+.5 <= data[-1].time]
    assert len(actual) == len(expected) >= 5
    for a, b in zip(actual, expected):
        decision = b['methods'][method]['twelve_patches']['regional_gate']
        assert a.start_s == b['start_s']
        assert a.bpm == decision['bpm_candidate']
        assert a.support == tuple(decision['support'])
        assert a.observed_at_s >= a.available_at_s-1e-9
        if policy == 'continuous':
            assert (a.analysis_start_s, a.analysis_end_s) == (b['analysis_start_s'], b['analysis_end_s'])
    if policy == 'full':
        assert actual[1].bpm is None
        assert actual[2].bpm is None
    assert len(engine.samples) < 450  # Eviction really runs, rather than retaining the recording.


def test_no_reading_before_lookahead_and_final_results_are_immutable():
    engine = PulseStream()
    data = list(samples(20))
    emitted = []
    for s in data:
        new = engine.push(s)
        if s.time < 12.5:
            assert not new
        emitted.extend(new)
    first = emitted[0]
    assert first.available_at_s == 12.5
    assert first.bpm == pytest.approx(72, abs=.2)
    original = first.to_dict()
    with pytest.raises(FrozenInstanceError):
        first.bpm = 99
    for s in samples(5, origin=20):
        for n in REGIONS:
            s.rgb[n][:] = np.nan
            s.pixels[n] = 0
        engine.push(s)
    assert first.to_dict() == original
    assert engine.state()['bpm'] is None


def test_rejected_latest_window_clears_previous_reading_and_no_eof_flush():
    engine = PulseStream(window_policy='full')
    readings = []
    for s in samples(18.5):
        if s.time >= 15:
            for n in REGIONS:
                s.rgb[n][:] = 100  # Flat signal mixed into the window; use explicit quality event too.
                s.geometry[n][2] = .1
        readings.extend(engine.push(s))
    assert len(readings) == 1 and readings[0].bpm is not None
    assert engine.next_start == 6
    # Exactly one further source sample supplies the look-ahead needed by window two.
    engine.push(next(samples(1/30, origin=18.5)))
    assert engine.latest.bpm is None
    assert engine.state()['status'] == 'unavailable'


def test_gap_and_format_change_start_new_sessions_without_crossing_support():
    engine = PulseStream()
    for s in samples(14):
        engine.push(s)
    assert engine.state()['bpm'] is not None
    assert engine.state(now=14.3)['status'] == 'capture_stalled'
    assert engine.state(now=14.3)['bpm'] is None
    assert not engine.push(next(samples(1/30, origin=16)))
    assert engine.session == 1 and engine.origin == 16
    assert engine.state()['bpm'] is None
    s = next(samples(1/30, origin=16.1))
    engine.push(replace(s, reset_reason='camera_format_change'))
    assert engine.session == 2 and engine.state()['reset_reason'] == 'camera_format_change'
    assert engine.state()['next_available_at_s'] == 28.6


def test_face_loss_clears_reading_and_return_does_not_revive_it():
    engine = PulseStream()
    data = list(samples(15))
    for s in data[:-2]:
        engine.push(s)
    assert engine.state()['status'] == 'estimate'
    absent = data[-2]
    for n in REGIONS:
        absent.pixels[n] = 0
        absent.rgb[n][:] = np.nan
    engine.push(absent)
    assert engine.state()['status'] == 'waiting_for_face'
    engine.push(data[-1])
    assert engine.state()['status'] == 'measuring'
    assert engine.state()['bpm'] is None


def test_capacity_and_input_ownership_and_invalid_time():
    engine = PulseStream(max_samples=10)
    first = next(samples())
    engine.push(first)
    first.rgb['forehead'][:] = 999
    assert not np.all(engine.samples[0].rgb['forehead'] == 999)
    with pytest.raises(ValueError):
        engine.push(first)
    with pytest.raises(ValueError):
        engine.push(replace(first, time=np.nan))
    for s in list(samples(2))[1:]:
        engine.push(s)
        assert len(engine.samples) <= 10
    assert engine.resets and engine.latest is None
