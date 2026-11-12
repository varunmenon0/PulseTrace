import numpy as np
from pulsetrace.patches import PATCHES, sample_patches, consensus
from pulsetrace.regions import REGIONS


def test_partitions_preserve_pixel_count_and_mean():
    rng = np.random.default_rng(2)
    image = rng.integers(0, 256, (40, 40, 3), dtype=np.uint8)
    mask = np.zeros((40, 40), np.uint8)
    mask[3:30, 5:36] = 255
    samples = sample_patches(image, {n:mask for n in REGIONS}, 30)
    assert len(samples) == 12
    for zone in REGIONS:
        group = [samples[n] for n in samples if PATCHES[n] == zone]
        assert sum(n for _,n in group) == np.count_nonzero(mask)
        assert np.allclose(np.average([c for c,_ in group], weights=[n for _,n in group], axis=0),
                           image[mask>0].mean(axis=0)[::-1])


def test_consensus_ignores_outlier_and_requires_cross_zone_support():
    assert consensus({"forehead_tl":72, "forehead_tr":73}, PATCHES)["bpm_candidate"] is None
    result = consensus({"forehead_tl":72, "forehead_tr":74, "left_cheek_tl":72,
                        "right_cheek_tl":115}, PATCHES)
    assert result["bpm_candidate"] == 72.5
    assert "right_cheek_tl" not in result["support"]
