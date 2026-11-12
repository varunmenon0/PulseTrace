import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('benchmark_ubfc',Path(__file__).parents[1]/'scripts/benchmark_ubfc.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_reference_repeated_timestamps_are_averaged(tmp_path):
    p=tmp_path/'ground_truth.txt'
    np.savetxt(p,[[1,2,3,4],[70,72,74,76],[0,.1,.1,.2]])
    t,b=module.load_reference(p)
    assert np.allclose(t,[0,.1,.2])
    assert np.allclose(b,[70,73,76])


def test_bad_reference_clock_rejected(tmp_path):
    p=tmp_path/'ground_truth.txt'
    np.savetxt(p,[[1,2,3],[70,72,74],[0,.2,.1]])
    with pytest.raises(ValueError):module.load_reference(p)
