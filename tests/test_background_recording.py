import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from pulsetrace.background import sample_background,validate_roi
from pulsetrace.sample_archive import SampleWriter,SampleReader


@pytest.mark.parametrize('roi',[[0,0,0,.2],[-.1,0,.2,.2],[.9,0,.2,.2],
                               [0,0,float('nan'),.2],[0,0,.2],[0,0,.2,float('inf')]])
def test_invalid_rectangle_fails_before_capture(roi):
    with pytest.raises(ValueError):validate_roi(roi)


def test_fixed_roi_records_rgb_and_rejects_face_overlap_without_moving_rectangle():
    frame=np.broadcast_to(np.array([10,20,30],np.uint8),(100,100,3)).copy()
    points=np.array([[40,30],[70,70]],float)
    result=sample_background(frame,points,[0,0,.2,.2])
    np.testing.assert_array_equal(result['rgb'],[30,20,10])
    assert result['pixels']==400 and result['bounds']==[0,0,20,20]
    points-=30
    rejected=sample_background(frame,points,[0,0,.2,.2])
    assert rejected['reason']=='face_overlaps_background' and rejected['pixels']==0
    assert rejected['bounds']==result['bounds'] and np.isnan(rejected['rgb']).all()


def test_untracked_face_and_too_small_regions_are_explicitly_unavailable():
    frame=np.zeros((100,100,3),np.uint8)
    assert sample_background(frame,None,[0,0,.2,.2])['reason']=='face_not_tracked'
    points=np.array([[40,30],[70,70]],float)
    assert sample_background(frame,points,[0,0,.01,.01])['reason']=='insufficient_pixels'


def test_background_sampling_preserves_all_face_measurements():
    from pulsetrace.sampling import FrameSampler
    from pulsetrace.controlled import ControlledTracker
    frame=np.full((240,320,3),100,np.uint8)
    points=ControlledTracker().detect(frame,0.)
    a=FrameSampler();b=FrameSampler(background_roi=[0,.85,.1,.1])
    for t in [0.,.1,.2]:
        baseline=a.sample(frame,points,t);recorded=b.sample(frame,points,t)
        for field in ('rgb','pixels','geometry','patch_rgb','patch_pixels'):
            for name in getattr(baseline,field):
                np.testing.assert_array_equal(getattr(baseline,field)[name],getattr(recorded,field)[name])
        assert recorded.background['status']=='available'


def test_archive_v2_preserves_background_and_rejects_missing_or_corrupt_fields(tmp_path):
    from test_streaming import samples
    data=list(samples(.1))
    for s in data:s.background=dict(status='available',reason=None,rgb=np.array([10.,20.,30.]),
                                    pixels=400,bounds=[0,0,20,20])
    path=tmp_path/'samples.jsonl'
    with SampleWriter(path,dict(background_reference=dict(roi=[0,0,.2,.2]))) as writer:
        for s in data:writer.write(s)
    with SampleReader(path) as reader:
        assert reader.header['schema_version']==2
        decoded=list(reader)
    np.testing.assert_array_equal(decoded[0].background['rgb'],data[0].background['rgb'])
    original=path.read_text().splitlines()
    for mutate in ('missing','corrupt'):
        records=original.copy();record=json.loads(records[1])
        if mutate=='missing':record.pop('background')
        else:record['background']['pixels']=3
        records[1]=json.dumps(record);path.write_text('\n'.join(records)+'\n')
        with SampleReader(path) as reader:
            with pytest.raises(ValueError,match='line 2'):list(reader)


def test_v2_archive_preserves_unavailable_reference_reason(tmp_path):
    from test_streaming import samples
    sample=next(samples(.1))
    sample.background=sample_background(np.zeros((100,100,3),np.uint8),None,[0,0,.2,.2])
    path=tmp_path/'samples.jsonl'
    with SampleWriter(path,dict(background_reference=dict(roi=[0,0,.2,.2]))) as writer:writer.write(sample)
    with SampleReader(path) as reader:decoded=list(reader)[0]
    assert decoded.background['reason']=='face_not_tracked'
    assert np.isnan(decoded.background['rgb']).all()


@pytest.fixture(scope='module')
def audit():
    import sys
    folder=Path(__file__).parents[1]/'scripts';sys.path.insert(0,str(folder))
    try:
        spec=importlib.util.spec_from_file_location('lighting_session',folder/'audit_lighting_session.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    finally:sys.path.remove(str(folder))
    return module


def test_session_audit_preserves_live_decisions_and_requires_identical_face_replay(audit,tmp_path):
    from test_streaming import samples
    from pulsetrace.streaming import PulseStream
    from pulsetrace.live import configuration
    folder=tmp_path/'capture';source=folder/'samples.jsonl';events=folder/'stream.jsonl'
    engine=PulseStream();readings=[]
    with SampleWriter(source,dict(configuration=configuration(engine),background_reference=dict(roi=[0,0,.2,.2]))) as writer:
        for sample in samples(26):
            sample.background=dict(status='available',reason=None,
                rgb=np.array([100.,100.,100.])+np.sin(2*np.pi*1.2*sample.time)*np.array([2.,1.,3.]),
                pixels=400,bounds=[0,0,20,20])
            writer.write(sample);readings.extend(engine.push(sample))
    original='\n'.join(json.dumps(r.to_dict()) for r in readings)+'\n';events.write_text(original)
    report=audit.run(source,events,tmp_path/'audit')
    assert report['face_replay_identical'] and report['window_status_counts']=={'lighting_overlap':3}
    assert all(row['original_bpm'] is not None and row['screen']['bpm'] is None for row in report['windows'])
    assert events.read_text()==original
    with pytest.raises(ValueError,match='separate output'):audit.run(source,events,folder)
    changed=[r.to_dict() for r in readings];changed[0]['bpm']=150.
    events.write_text('\n'.join(json.dumps(r) for r in changed)+'\n')
    with pytest.raises(ValueError,match='do not match'):audit.run(source,events,tmp_path/'mismatched')


def test_cli_rejects_invalid_background_roi_before_loading_tracker(monkeypatch):
    from pulsetrace.cli import main
    import pulsetrace.tracking
    def forbidden(*args,**kwargs):pytest.fail('No tracker or camera should be opened')
    monkeypatch.setattr(pulsetrace.tracking,'FaceTracker',forbidden)
    with pytest.raises(SystemExit):main(['webcam','--model','missing.task','--background-roi','.9','0','.2','.2'])


def test_webcam_cli_records_paired_reference_and_audits_missing_support_without_camera(tmp_path,monkeypatch,capsys,audit):
    import queue
    import threading
    import pulsetrace.capture
    import pulsetrace.tracking
    import pulsetrace.live as live
    from pulsetrace.cli import main
    from test_streaming import samples
    class Tracker:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Camera:
        def __init__(self,tracker,sampler,**kwargs):
            assert sampler.background_roi==(.02,.02,.18,.18)
            data=list(samples(14));self.queue=queue.Queue()
            for i,s in enumerate(data):
                s.background=dict(status='available',reason=None,rgb=np.full(3,100.),
                                  pixels=400,bounds=[0,0,20,20])
                if i==0:s.background.update(status='unavailable',reason='face_not_tracked',
                                           rgb=np.full(3,np.nan),pixels=0)
                self.queue.put(s)
            self.frames=len(data);self.dropped_samples=0
            self.done=threading.Event();self.done.set();self.error=None
            self.started=live.time.monotonic()-data[-1].time
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def statistics(self):return dict(backend='mock')
    monkeypatch.setattr(pulsetrace.capture,'CameraSession',Camera)
    monkeypatch.setattr(pulsetrace.tracking,'FaceTracker',Tracker)
    folder=tmp_path/'capture'
    assert main(['webcam','--model','fixture.task','--no-preview','--background-roi',
                 '.02','.02','.18','.18','--output',str(folder)])==0
    with SampleReader(folder/'samples.jsonl') as reader:
        assert reader.header['schema_version']==2
        data=list(reader)
    summary=json.loads((folder/'stream-summary.json').read_text())
    assert summary['background_reference']['sample_status_counts']=={'face_not_tracked':1,'available':419}
    assert not summary['background_reference']['applied_to_estimates']
    assert len(data)==420 and summary['estimated_windows']==1
    result=audit.run(folder/'samples.jsonl',folder/'stream.jsonl',tmp_path/'audit')
    assert result['face_replay_identical']
    assert result['window_status_counts']=={'reference_unavailable':1}
    assert result['windows'][0]['original_bpm'] is not None
    capsys.readouterr()
