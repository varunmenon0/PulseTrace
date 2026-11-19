"""Fixed synthetic replay scenarios; never a live-camera accuracy benchmark."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from pulsetrace.controlled import ControlledTracker, make_controlled_video
from pulsetrace.live import replay


def run(protocol, output):
    if (protocol['window_seconds'], protocol['step_seconds'], protocol['lookahead_seconds']) != (12, 6, .5):
        raise ValueError('Protocol must match the fixed streaming timing')
    cases = []
    for case in protocol['cases']:
        folder = output/case['name']
        folder.mkdir(parents=True, exist_ok=True)
        video = folder/'synthetic.avi'
        make_controlled_video(video, bpm=case['start_bpm'], end_bpm=case['end_bpm'],
            seconds=case['seconds'], fps=protocol['fps'], seed=protocol['seed'], profile=case['profile'])
        summary = replay(video, ControlledTracker(profile=case['profile']), folder,
            sampling=protocol['sampling'], method=protocol['method'], consensus=protocol['consensus'],
            window_policy=protocol['window_policy'], verify=True, synthetic=True)
        rows = [json.loads(line) for line in (folder/'stream.jsonl').read_text().splitlines()]
        rows = [r for r in rows if r['type'] == 'window']
        errors = []
        for row in rows:
            if row['bpm'] is None:
                continue
            center = (row['analysis_start_s']+row['analysis_end_s'])/2
            expected = case['start_bpm']+(case['end_bpm']-case['start_bpm'])*center/case['seconds']
            errors.append(abs(row['bpm']-expected))
        cases.append(dict(name=case['name'], source_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
            frames=summary['frames'], finalized_windows=len(rows), estimated_windows=len(errors),
            unavailable_windows=len(rows)-len(errors), batch_parity=summary['batch_parity'],
            mae_against_injected_support_mean_bpm=float(np.mean(errors)) if errors else None,
            maximum_error_bpm=max(errors) if errors else None,
            windows=[{k:r[k] for k in ('start_s','end_s','available_at_s','observed_at_s',
                                      'analysis_start_s','analysis_end_s','bpm','status','unavailable_reason')}
                     for r in rows]))
    return dict(synthetic=True, protocol=protocol, cases=cases,
        total_frames=sum(c['frames'] for c in cases),
        total_finalized_windows=sum(c['finalized_windows'] for c in cases),
        total_estimated_windows=sum(c['estimated_windows'] for c in cases),
        versions={n:importlib.metadata.version(n) for n in ('numpy','scipy','opencv-contrib-python')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path,
                        default=Path(__file__).resolve().parents[1]/'examples/streaming/protocol.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.protocol.read_bytes()
    result = run(json.loads(data), args.output)
    result['protocol_sha256'] = hashlib.sha256(data).hexdigest()
    (args.output/'benchmark.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('total_frames','total_finalized_windows','total_estimated_windows')}, indent=2))


if __name__ == '__main__':
    main()
