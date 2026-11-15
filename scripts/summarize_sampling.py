"""Pool compatible paired sampling experiments without dropping failed windows."""
import argparse
import json
from pathlib import Path

from compare_subpixel import paired_metrics, summarize


def summarize_reports(reports):
    if not reports:
        raise ValueError('Need at least one paired report')
    configuration, versions = reports[0]['configuration'], reports[0]['versions']
    model = reports[0]['input']['model_sha256']
    seen, recordings = set(), []
    windows = {'integer': [], 'fractional': []}
    missing = {mode: 0 for mode in windows}
    observations = 0
    for report in reports:
        identity = report['input']['video_sha256']
        if identity in seen:
            raise ValueError('Duplicate recording would double-count windows')
        seen.add(identity)
        if report['configuration'] != configuration or report['versions'] != versions or report['input']['model_sha256'] != model:
            raise ValueError('Sampling configuration, dependency versions, and model must match')
        pair = report['windows']
        if set(pair) != set(windows) or len(pair['integer']) != len(pair['fractional']):
            raise ValueError('Unmatched paired window counts')
        for a, b in zip(pair['integer'], pair['fractional']):
            if any(a[k] != b[k] for k in ('start_s', 'end_s', 'reference_bpm')):
                raise ValueError('Paired timing and reference labels must match')
        for mode in windows:
            windows[mode].extend(pair[mode])
            missing[mode] += sum(report['missing_patch_frames'][mode].values())
        observations += report['input']['decoded_frames'] * 12
        recordings.append(dict(video_sha256=identity, reference_sha256=report['input']['reference_sha256'],
                               decoded_frames=report['input']['decoded_frames'],
                               metrics=report['metrics'], paired_metrics=report['paired_metrics']))
    return dict(recordings=recordings, configuration=configuration, versions=versions,
                model_sha256=model, patch_observations_per_sampler=observations,
                missing_patch_observations=missing,
                metrics={mode: summarize(rows) for mode, rows in windows.items()},
                paired_metrics=paired_metrics(windows),
                limitations=['Development recordings, not a fresh held-out cohort',
                             'Errors compare stored device BPM labels; reference and synchronization limitations remain',
                             'Pooled errors weight accepted windows equally, not recordings',
                             'All video windows remain in denominators; common-window errors are reported separately',
                             'Overlapping windows are not independent samples'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize_reports([json.loads(path.read_text()) for path in args.reports])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
