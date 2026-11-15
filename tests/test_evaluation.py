import numpy as np
import pytest
from pulsetrace.evaluation import evaluate_reference
from test_diagnostics import example


def test_synchronized_reference_and_coverage():
    e=example(); rt=np.arange(0,34,.1); rb=np.full(len(rt),72.)
    result=evaluate_reference(e,rt,rb,reference_offset=3)
    for methods in result['regions'].values():
        for r in methods.values():
            assert r['compared_windows']==4
            assert r['candidate_coverage']==1
            assert r['mae_bpm']<2


def test_reference_never_extrapolated():
    e=example(); rt=np.arange(10,20,.1); rb=np.full(len(rt),72.)
    result=evaluate_reference(e,rt,rb,reference_offset=0)
    assert result['regions']['forehead']['green']['mae_bpm'] is None
    assert result['regions']['forehead']['green']['reference_covered_windows']==0


def test_missing_pulse_keeps_coverage_denominator():
    e=example(); e.rgb['forehead'][:]=100
    rt=np.arange(0,31,.1); rb=np.full(len(rt),72.)
    r=evaluate_reference(e,rt,rb,reference_offset=0)['regions']['forehead']['green']
    assert r['reference_covered_windows']==4 and r['compared_windows']==0
    assert r['mae_bpm'] is None and r['candidate_coverage']==0


def test_gap_and_invalid_reference():
    e=example(); rt=np.array([0.,30.]); rb=np.array([72.,72.])
    r=evaluate_reference(e,rt,rb,reference_offset=0)['regions']['forehead']['green']
    assert r['reference_covered_windows']==0
    with pytest.raises(ValueError): evaluate_reference(e,[1,0],[72,72],reference_offset=0)
