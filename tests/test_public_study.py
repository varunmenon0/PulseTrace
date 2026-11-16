import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from complete_public_study import select_demo


def record(name,count,error,total=10):
    return dict(recording=name,metrics=dict(pos=dict(twelve_patches=dict(continuous=dict(
        scorable_windows=count,total_windows=total,mae_against_device_bpm=error)))))


def test_demo_selection_requires_sustained_scorable_coverage():
    assert select_demo([record('too_sparse',7,.1),record('too_wrong',10,6),record('eligible',8,2)])=='eligible'
    assert select_demo([record('no_estimates',0,None)]) is None


def test_demo_selection_ranks_coverage_then_error_then_name():
    rows=[record('a',8,.1),record('z',10,3),record('c',10,2),record('b',10,2)]
    assert select_demo(rows)=='b'
