import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from replay_zone_consensus import CONFIGURATION, replay_report, replay_protocol, summarize


def report():
    return json.loads((Path(__file__).parents[1]/'examples/photometric-guard/subject14.json').read_text())


def test_saved_replay_retains_zero_coverage_and_invalid_reference_windows():
    source = report()
    source['windows'][0]['reference_bpm'] = None
    original = copy.deepcopy(source)
    rows = replay_report(source, 'sources')
    metrics = summarize(rows)['pos/integer_area']
    assert metrics['total_windows'] == 10 and metrics['reference_valid_windows'] == 9
    assert metrics['legacy']['scorable_windows'] == 0
    assert metrics['zone']['scorable_windows'] == 0
    assert source == original


def test_replay_rejects_a_stale_legacy_result():
    source = report()
    source['windows'][0]['sources']['integer_area']['methods']['pos']['twelve_patches']['bpm_candidate'] = 123
    with pytest.raises(ValueError, match='does not reproduce'):
        replay_report(source, 'sources')


def test_protocol_checks_hashes_and_duplicate_recordings(tmp_path):
    path = tmp_path/'report.json'
    path.write_text(json.dumps(report()))
    entry = dict(path='report.json', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    protocol = dict(configuration=CONFIGURATION,
                    groups=[dict(name='fixture', format='sources', reports=[entry])])
    assert len(replay_protocol(protocol, tmp_path)['groups']) == 1
    protocol['groups'][0]['reports'].append(entry)
    with pytest.raises(ValueError, match='Duplicate recording'):
        replay_protocol(protocol, tmp_path)
    protocol['groups'][0]['reports'] = [dict(entry, sha256='wrong')]
    with pytest.raises(ValueError, match='checksum mismatch'):
        replay_protocol(protocol, tmp_path)
