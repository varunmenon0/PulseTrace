import copy

import numpy as np
from PIL import Image

from pulsetrace.demo_layout import render_frame, line_chart, WIDTH, HEIGHT


def test_presentation_handles_missing_results_without_modifying_measurements():
    frame=np.full((240,320,3),100,np.uint8)
    windows=[dict(start_s=0,end_s=12,analysis_start_s=None,analysis_end_s=None,bpm_candidate=None,reference_bpm=None)]
    original=copy.deepcopy(windows)
    result=render_frame(frame,None,13,windows,{},(0,0,320,240),20)
    assert result.shape==(HEIGHT,WIDTH,3) and result.dtype==np.uint8
    assert windows==original
    assert np.all(frame==100)


def test_chart_does_not_connect_across_a_missing_estimate():
    image=Image.new('RGB',(110,100),'white')
    line_chart(image,(0,0,100,100),[0,1,2,3,4],[1,1,None,1,1],(0,4,0,2),'black')
    assert max(image.getpixel((12,50)))<80
    assert image.getpixel((50,50))==(255,255,255)
