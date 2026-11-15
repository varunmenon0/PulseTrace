import numpy as np
import pytest

from pulsetrace.subpixel import fractional_masks


def rectangle(dx=0):
    return np.array([[10.25 + dx, 10.25], [30.25 + dx, 10.25],
                     [30.25 + dx, 30.25], [10.25 + dx, 30.25]])


def test_area_and_quadrants_conserve_coverage():
    parent, patches = fractional_masks((50, 50, 3), rectangle())
    assert parent.area == pytest.approx(18 ** 2)
    assert np.allclose(sum(p.weights for p in patches.values()), parent.weights)
    assert all(p.area == pytest.approx(81) for p in patches.values())
    image = np.full((50, 50, 3), [20, 40, 80], dtype=np.uint8)
    assert np.allclose(parent.mean_rgb(image), [80, 40, 20])


def test_subpixel_translation_preserves_area_and_moves_gradient_mean():
    image = np.zeros((50, 50, 3), dtype=float)
    image[:, :, 2] = np.arange(50)
    a, _ = fractional_masks(image.shape, rectangle())
    b, _ = fractional_masks(image.shape, rectangle(.25))
    assert b.area == pytest.approx(a.area)
    assert b.mean_rgb(image)[0] - a.mean_rgb(image)[0] == pytest.approx(.25)


@pytest.mark.parametrize("points,options", [
    (rectangle(-11), {}), (np.ones((3, 2)), {}),
    (rectangle() * np.nan, {}), (rectangle(), {"subdivisions": 0}),
    (rectangle(), {"subdivisions": 2.5}), (rectangle(), {"inset": -1}),
])
def test_invalid_geometry_is_rejected(points, options):
    with pytest.raises(ValueError):
        fractional_masks((50, 50, 3), points, **options)


def test_small_fractional_regions_are_rejected():
    parent, patches = fractional_masks((50, 50, 3), rectangle(), inset=9)
    with pytest.raises(ValueError, match="too small"):
        parent.mean_rgb(np.ones((50, 50, 3)))
    with pytest.raises(ValueError, match="too small"):
        patches['tl'].mean_rgb(np.ones((50, 50, 3)))


def test_equal_area_partition_balances_triangle_without_changing_parent():
    points = np.array([[5., 5.], [45., 5.], [5., 45.]])
    original, uneven = fractional_masks((50, 50, 3), points, subdivisions=32)
    parent, balanced = fractional_masks((50, 50, 3), points, subdivisions=32,
                                        partition='equal_area')
    assert np.array_equal(parent.weights, original.weights)
    assert np.allclose(sum(p.weights for p in balanced.values()), parent.weights)
    assert max(abs(p.area-parent.area/4) for p in balanced.values()) < 1
    assert min(p.area for p in uneven.values()) < parent.area/8


def test_equal_area_empty_inset_is_rejected_as_small():
    parent, patches = fractional_masks((50, 50, 3), rectangle(), inset=11,
                                       partition='equal_area')
    assert parent.area == 0
    assert all(p.area == 0 for p in patches.values())


def test_unknown_partition_is_rejected():
    with pytest.raises(ValueError, match='partition'):
        fractional_masks((50, 50, 3), rectangle(), partition='unknown')
