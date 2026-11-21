from dataclasses import replace
import json

import numpy as np
import pytest

from pulsetrace.cli import main
from pulsetrace.live import configuration, replay_samples
from pulsetrace.sample_archive import SampleWriter, SampleReader
from pulsetrace.streaming import PulseStream
from test_streaming import samples


def write_archive(path, data):
    engine = PulseStream()
    readings = []
    with SampleWriter(path, dict(configuration=configuration(engine), synthetic=True, sampling='fractional')) as archive:
        for s in data:
            archive.write(s)
            readings.extend(engine.push(s))
    return readings


def test_archive_preserves_all_measurements_nonfinite_markers_and_resets(tmp_path):
    data = list(samples(1))
    data[3].rgb['forehead'][0] = np.nan
    data[4].geometry['left_cheek'][2] = np.inf
    data[5].geometry['right_cheek'][3] = -np.inf
    data[6] = replace(data[6], reset_reason='camera_format_change')
    path = tmp_path/'samples.jsonl'
    write_archive(path, data)
    with SampleReader(path) as reader:
        decoded = list(reader)
        assert reader.header['frames_saved'] is False
        assert 'signal.py' in reader.header['provenance']['source_sha256']
    assert len(decoded) == len(data)
    for a,b in zip(data,decoded):
        assert a.time == b.time and a.reset_reason == b.reset_reason
        for field in ('rgb','pixels','geometry','patch_rgb','patch_pixels'):
            for n in getattr(a,field):
                np.testing.assert_array_equal(getattr(a,field)[n],getattr(b,field)[n])
    for line in path.read_text().splitlines():
        json.loads(line, parse_constant=lambda value:pytest.fail('Nonstandard JSON constant '+value))


def test_archived_session_replays_identical_windows_without_a_camera_or_model(tmp_path, monkeypatch, capsys):
    import pulsetrace.tracking
    def forbidden(*args, **kwargs):
        pytest.fail('Sample replay must not instantiate a face tracker')
    monkeypatch.setattr(pulsetrace.tracking, 'FaceTracker', forbidden)
    path = tmp_path/'capture'/'samples.jsonl'
    data = list(samples(26))
    for s in data:
        if 18.09 < s.time < 18.12:
            for n in ('left_cheek','right_cheek'):
                s.geometry[n][2] = .1
    original = write_archive(path, data)
    output = tmp_path/'reprocessed'
    assert main(['replay-samples',str(path),'--verify-batch','--output',str(output)]) == 0
    events = [json.loads(line) for line in (output/'stream.jsonl').read_text().splitlines()]
    actual = [e for e in events if e['type'] == 'window']
    assert actual == [json.loads(json.dumps(r.to_dict())) for r in original]
    summary = json.loads((output/'stream-summary.json').read_text())
    assert summary['samples'] == len(data) and summary['batch_parity']['passed']
    assert not (output/'samples.jsonl').exists()
    capsys.readouterr()


def test_unsupported_or_corrupt_archives_fail_clearly_and_preserve_inputs(tmp_path):
    path = tmp_path/'samples.jsonl'
    write_archive(path, list(samples(1)))
    original = path.read_bytes()
    with pytest.raises(ValueError,match='overwrite'):
        replay_samples(path,tmp_path)
    assert path.read_bytes() == original
    records = path.read_text().splitlines()
    row = json.loads(records[2]);row['patch_rgb'].pop('forehead_tl')
    records[2] = json.dumps(row)
    path.write_text('\n'.join(records)+'\n')
    with SampleReader(path) as reader:
        with pytest.raises(ValueError,match='line 3'):
            list(reader)
    header = json.loads(records[0]);header['schema_version']=999
    path.write_text(json.dumps(header)+'\n')
    with pytest.raises(ValueError,match='header'):
        with SampleReader(path): pass


def test_sample_replay_preserves_gap_and_explicit_reset_boundaries(tmp_path):
    data = list(samples(14)) + list(samples(14,origin=16))
    data[450] = replace(data[450],reset_reason='camera_format_change')
    path = tmp_path/'source'/'samples.jsonl'
    original = write_archive(path,data)
    output = tmp_path/'replay'
    summary = replay_samples(path,output,verify=True)
    windows = [json.loads(line) for line in (output/'stream.jsonl').read_text().splitlines()
               if json.loads(line)['type']=='window']
    assert windows == [json.loads(json.dumps(r.to_dict())) for r in original]
    assert summary['resets'] == 2
    assert summary['batch_parity']['passed']
