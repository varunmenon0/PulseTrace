import json
from types import SimpleNamespace
import numpy as np
import pytest
from pulsetrace.cli import main
from pulsetrace.tracking import FaceTracker


def test_cli_demo_artifacts(tmp_path):
    assert main(['demo','--seconds','12','--output',str(tmp_path)])==0
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert summary['metadata']['synthetic'] is True
    for name,result in summary['regions'].items():
        assert abs(result['bpm_candidate']-72)<2
        assert (tmp_path/f'{name}_pulse.csv').exists()
    assert (tmp_path/'waveforms.png').stat().st_size>1000
    assert (tmp_path/'regions.png').exists()
    assert (tmp_path/'rgb.csv').exists()
    from pulsetrace.diagnostics import load_rgb_csv
    extraction=load_rgb_csv(tmp_path/'rgb.csv')
    assert len(extraction.geometry)==3
    assert (tmp_path/'tracking.png').exists()


def test_report_rerun_removes_stale_success(tmp_path):
    from pulsetrace.pipeline import Extraction
    from pulsetrace.report import write_report
    from pulsetrace.regions import REGIONS
    (tmp_path/'forehead_pulse.csv').write_text('old success')
    (tmp_path/'regions.png').write_bytes(b'old preview')
    extraction=Extraction(np.arange(10)/30,
                          {name:np.full((10,3),np.nan) for name in REGIONS},
                          {name:np.zeros(10) for name in REGIONS},None,{}, {})
    write_report(extraction,{}, {name:'No face' for name in REGIONS},tmp_path,'pos')
    assert not (tmp_path/'forehead_pulse.csv').exists()
    assert not (tmp_path/'regions.png').exists()


def test_missing_model(tmp_path):
    with pytest.raises(ValueError,match='model missing'): FaceTracker(tmp_path/'missing.task')


def test_tracker_adapter_timestamp_rgb_and_ambiguity():
    # Exercise production adapter without network/model, separate from integration test.
    tracker=object.__new__(FaceTracker)
    tracker.last_ms=-1
    seen=[]
    class FakeMP:
        ImageFormat=SimpleNamespace(SRGB='rgb')
        @staticmethod
        def Image(**kwargs): return kwargs['data']
    class Detector:
        def detect_for_video(self, image, timestamp):
            seen.append((image,timestamp))
            faces=[[SimpleNamespace(x=.5,y=.25)]] if len(seen)==1 else [[],[]]
            return SimpleNamespace(face_landmarks=faces)
    tracker.mp=FakeMP
    tracker.detector=Detector()
    frame=np.full((20,40,3),[1,2,3],np.uint8)
    landmarks=tracker.detect(frame,0)
    assert np.allclose(landmarks,[[19.5,4.75]])
    assert np.array_equal(seen[0][0][0,0],[3,2,1])
    assert tracker.detect(frame,0) is None
    assert [x[1] for x in seen]==[0,1]
