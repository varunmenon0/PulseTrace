import json
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

from pulsetrace.peak_reference import load_peak_reference, window_rate


def test_known_clock_offset_recovers_75_bpm():
    peaks = 2 + np.arange(21) * .8
    assert window_rate(peaks, 0, 12, reference_offset=2)['bpm'] == pytest.approx(75)
    assert window_rate(peaks, 0, 12, reference_offset=0)['bpm'] is None


def test_irregular_intervals_are_time_weighted_without_count_rounding():
    # One 1-second interval (60 BPM), then two .5-second intervals (120 BPM).
    assert window_rate([0, 1, 1.5, 2], 0, 2, reference_offset=0)['bpm'] == pytest.approx(90)


def test_missing_annotation_is_not_bridged():
    result = window_rate([0, .8, 1.6, 4, 4.8], 0, 4, reference_offset=0)
    assert result['bpm'] is None and 'no gap bridging' in result['warning']


def test_peak_file_must_match_recording_and_explicit_units(tmp_path):
    peaks, metadata = tmp_path/'beats.csv', tmp_path/'provenance.json'
    peaks.write_text('time_s\n0\n0.8\n1.6\n')
    metadata.write_text(json.dumps(dict(video_sha256='recording-a', source='synthetic fixture', time_unit='seconds')))
    with pytest.raises(ValueError, match='video hash'):
        load_peak_reference(peaks, metadata, video_sha256='recording-b')
    data, provenance = load_peak_reference(peaks, metadata, video_sha256='recording-a')
    assert np.allclose(data, [0, .8, 1.6])
    assert provenance['source'] == 'synthetic fixture'


@pytest.mark.parametrize('peaks', [[0, .8, .8], [0, np.nan], [1, 0]])
def test_invalid_beat_sequences_are_rejected(peaks):
    with pytest.raises(ValueError):
        window_rate(peaks, 0, 1, reference_offset=0)


def test_external_scores_preserve_device_labels_and_source_report():
    sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
    from evaluate_peak_reference import evaluate
    report = dict(input=dict(video_sha256='synthetic'), windows=[dict(
        start_s=0., end_s=12., reference_bpm=98.,
        sources=dict(fractional_area=dict(methods=dict(pos=dict(twelve_patches=dict(bpm_candidate=74.))))))])
    original = copy.deepcopy(report)
    result = evaluate(report, np.arange(21)*.8, dict(source='synthetic fixture'), reference_offset=0)
    row = result['windows'][0]
    assert row['device_reference_bpm'] == 98
    assert row['peak_reference']['bpm'] == pytest.approx(75)
    assert row['sources']['fractional_area']['pos']['twelve_patches']['error_against_external_beats'] == pytest.approx(-1)
    assert report == original
