import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from audit_patch_support import summarize


def test_support_audit_separates_total_area_shortage_from_imbalanced_partition():
    rows = [[100, 25, 25, 25, 25], [160, 10, 50, 50, 50], [160, 40, 40, 40, 40]]
    result = summarize(rows, rows)
    assert result['unavailable_patches'] == 5
    assert result['complete_region_frames'] == 1
    assert result['parents_below_four_patch_minimum'] == 1
    assert result['incomplete_despite_parent_area_at_least_120'] == 1
    assert result['max_patch_area_difference_from_16'] == 0


def test_support_audit_rejects_unmatched_rows():
    with pytest.raises(ValueError):
        summarize([[160, 40, 40, 40, 40]], [])
