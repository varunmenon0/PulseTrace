import numpy as np
import pytest
from pulsetrace.signal import analyze, prepare_series, pulse_source


def fixture(bpm=72, seconds=24, fps=30):
    t = np.arange(int(seconds*fps)) / fps
    pulse = np.sin(2*np.pi*bpm/60*t)
    rgb = np.array([160,110,80]) + pulse[:,None]*np.array([.6,3,.2])
    rgb += (4*np.sin(2*np.pi*.12*t))[:,None]
    rgb += np.random.default_rng(8).normal(0,.05,rgb.shape)
    return t,rgb


@pytest.mark.parametrize('bpm',[48,72,120,180])
@pytest.mark.parametrize('method',['green','pos'])
def test_recovers_known_pulse(bpm, method):
    t,rgb = fixture(bpm)
    result = analyze(t,rgb,method=method)
    assert result.bpm is not None
    assert abs(result.bpm-bpm) < 2
    assert np.isfinite(result.pulse).all()
    assert result.peak_fraction > .5


def test_short_gaps_interpolated_long_gaps_split():
    t,rgb = fixture(seconds=30)
    rgb[10:13] = np.nan
    rgb[600:650] = np.nan
    result = analyze(t,rgb)
    assert result.time[-1] < t[600]
    assert result.interpolated_fraction > 0
    assert abs(result.bpm-72) < 2
    assert any('longest' in w for w in result.warnings)


def test_timestamp_gap_splits_even_without_nan():
    t,rgb = fixture(seconds=30)
    t[450:] += 5
    result = analyze(t,rgb)
    assert result.duration < 15


@pytest.mark.parametrize('kind',['constant','all_missing','short','reversed','duplicate','nyquist'])
def test_invalid_and_unusable(kind):
    t,rgb = fixture()
    if kind == 'constant':
        result = analyze(t, np.full_like(rgb,100))
        assert result.bpm is None
    else:
        if kind == 'all_missing': rgb[:] = np.nan
        if kind == 'short': t,rgb = t[:100],rgb[:100]
        if kind == 'reversed': t=t[::-1]
        if kind == 'duplicate': t[1]=t[0]
        if kind == 'nyquist': t=t*10
        with pytest.raises(ValueError): analyze(t,rgb)


def test_irregular_timestamps_resampled():
    t,rgb = fixture()
    t[1:-1] += .003*np.sin(np.arange(len(t)-2))
    grid, values, fs, missing, warnings = prepare_series(t,rgb)
    assert np.allclose(np.diff(grid),1/fs)
    assert any('Irregular' in w for w in warnings)
    assert abs(analyze(t,rgb).bpm-72) < 2


def test_noise_has_no_usable_estimate():
    t,rgb = fixture(seconds=60)
    rgb = 100 + np.random.default_rng(45).normal(0,1,rgb.shape)
    assert analyze(t,rgb,method='green').bpm is None


def test_invalid_method():
    with pytest.raises(ValueError): pulse_source(np.ones((100,3)),30,'unknown')


@pytest.mark.parametrize('kwargs',[{'min_seconds':float('nan')},{'max_gap':float('inf')},{'max_gap':0}])
def test_invalid_configuration(kwargs):
    t,rgb=fixture()
    with pytest.raises(ValueError): analyze(t,rgb,**kwargs)
