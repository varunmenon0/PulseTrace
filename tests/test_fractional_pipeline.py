import numpy as np

from pulsetrace.controlled import ControlledTracker, make_controlled_video
from pulsetrace.pipeline import extract_video
from pulsetrace.regional_quality import write_regional_comparison
from pulsetrace.patches import PATCHES


def test_decoded_fractional_sampler_retains_all_patches_and_pulse(tmp_path):
    path=tmp_path/'input.avi';make_controlled_video(path,seconds=12)
    extraction=extract_video(path,ControlledTracker(),patches=True,sampling='fractional')
    assert extraction.metadata['sampling']=='fractional'
    assert extraction.metadata['fractional_sampling']['partition']=='equal_area'
    assert all(np.all(extraction.patch_pixels[n]>30) for n in PATCHES)
    assert any(np.any(v!=np.rint(v)) for v in extraction.pixels.values())
    report=write_regional_comparison(extraction,tmp_path)
    assert abs(report['windows'][0]['methods']['pos']['twelve_patches']['regional_gate']['bpm_candidate']-72)<1


def test_fractional_tracking_loss_stays_missing(tmp_path):
    path=tmp_path/'input.avi';make_controlled_video(path,seconds=10)
    class Loss(ControlledTracker):
        def detect(self,bgr,time):
            return None if 4<=time<5 else super().detect(bgr,time)
    extraction=extract_video(path,Loss(),patches=True,sampling='fractional')
    missing=(extraction.time>=4)&(extraction.time<5)
    assert all(np.all(v[missing]==0) for v in extraction.pixels.values())
    assert all(np.isnan(v[missing]).all() for v in extraction.patch_rgb.values())
