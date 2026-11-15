"""Supplement area-gate reports with external beat-time labels; preserve originals."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from pulsetrace.peak_reference import load_peak_reference, window_rate


def evaluate(report, peaks, provenance, *, reference_offset):
    rows = []
    for window in report['windows']:
        reference = window_rate(peaks, window['start_s'], window['end_s'],
                                reference_offset=reference_offset)
        row = dict(start_s=window['start_s'], end_s=window['end_s'],
                   device_reference_bpm=window['reference_bpm'], peak_reference=reference,
                   sources={})
        for source, detail in window['sources'].items():
            row['sources'][source] = {}
            for method, layouts in detail['methods'].items():
                row['sources'][source][method] = {}
                for layout, result in layouts.items():
                    bpm = result['bpm_candidate']
                    row['sources'][source][method][layout] = dict(bpm_candidate=bpm,
                        error_against_external_beats=None if bpm is None or reference['bpm'] is None else bpm-reference['bpm'])
        rows.append(row)
    metrics = {}
    for row in rows:
        for source, methods in row['sources'].items():
            for method, layouts in methods.items():
                for layout, result in layouts.items():
                    key = f'{source}/{method}/{layout}'
                    metrics.setdefault(key, [])
                    if result['error_against_external_beats'] is not None:
                        metrics[key].append(abs(result['error_against_external_beats']))
    return dict(reference_provenance=provenance, reference_offset_s=reference_offset,
                video_sha256=report['input']['video_sha256'],
                aggregation='Time-weighted mean of 60/RR, with complete beat bracketing',
                limitations=['Provenance and clock alignment are supplied externally, not verified by this tool',
                             'No video-dependent peak selection or offset optimization',
                             'Original device-reference reports are not replaced'],
                metrics={key: dict(total_windows=len(rows),
                    reference_valid_windows=sum(r['peak_reference']['bpm'] is not None for r in rows),
                    scorable_windows=len(errors), mae_bpm=float(np.mean(errors)) if errors else None)
                    for key, errors in metrics.items()}, windows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'peaks', 'provenance', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reference-offset', type=float, required=True,
                        help='Reference time = video time + this externally established offset')
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    peaks, provenance = load_peak_reference(args.peaks, args.provenance,
                                            video_sha256=report['input']['video_sha256'])
    result = evaluate(report, peaks, provenance, reference_offset=args.reference_offset)
    result['input_hashes'] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for name, path in (('report', args.report), ('peaks', args.peaks), ('provenance', args.provenance))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
