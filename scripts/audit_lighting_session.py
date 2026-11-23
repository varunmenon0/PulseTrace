"""Observe experimental lighting overlap on saved windows; never alter live logs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

from audit_stream_session import canonical_windows
from pulsetrace.live import replay_samples
from pulsetrace.lighting import build_reference, screen_candidate
from pulsetrace.sample_archive import SampleReader, provenance


def run(source,events,output):
    source,events,output=Path(source),Path(events),Path(output)
    if output.resolve() in (source.parent.resolve(),events.parent.resolve()):
        raise ValueError('Choose a separate output folder to preserve the original session')
    with SampleReader(source) as reader:
        header=reader.header;samples=list(reader)
    original=[json.loads(line) for line in events.read_text().splitlines()]
    replay_samples(source,output/'face-replay')
    replayed=[json.loads(line) for line in (output/'face-replay/stream.jsonl').read_text().splitlines()]
    windows=canonical_windows([r for r in original if r.get('type')=='window'])
    if windows!=canonical_windows([r for r in replayed if r.get('type')=='window']):
        raise ValueError('Original window events do not match same-sample face replay; audit stopped')
    t=np.array([s.time for s in samples]);rows=[]
    for window in windows:
        start,end=window['analysis_start_s'],window['analysis_end_s']
        selected=[] if start is None else [s for s,keep in zip(samples,(t>=start)&(t<=end)) if keep]
        counts=Counter('not_recorded' if s.background is None else
                       s.background['reason'] or 'available' for s in selected)
        bg=None
        if selected and counts.get('available')==len(selected):
            bg=np.array([s.background['rgb'] for s in selected])
        reference=build_reference([s.time for s in selected],bg)
        decision=screen_candidate(window['bpm'],reference)
        rows.append(dict(start_s=window['start_s'],end_s=window['end_s'],
            analysis_start_s=start,analysis_end_s=end,session=window['session'],
            original_status=window['status'],original_bpm=window['bpm'],
            raw_bpm=window.get('raw_bpm',window['bpm']),
            background_sample_status_counts=dict(counts),reference_status=reference.status,
            reference_reason=reference.reason,screen=decision))
    import pulsetrace.background as background_module
    import pulsetrace.lighting as lighting_module
    report=dict(type='experimental_lighting_audit',frames_saved=False,face_replay_identical=True,
        background_configuration=header['metadata'].get('background_reference'),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        events_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),provenance=provenance(),
        audit_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             (Path(__file__),Path(background_module.__file__),Path(lighting_module.__file__))},
        window_status_counts=dict(Counter(row['screen']['status'] for row in rows)),windows=rows,
        limitation='Post-hoc ambiguity observation only; no pulse-reference accuracy scoring or live decision changes')
    (output/'lighting-audit.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples',type=Path)
    parser.add_argument('--events',type=Path,help='Defaults to stream.jsonl beside samples')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.samples,args.events or args.samples.parent/'stream.jsonl',args.output)
    print(json.dumps(dict(face_replay_identical=report['face_replay_identical'],
                         window_status_counts=report['window_status_counts']),indent=2))


if __name__=='__main__':main()
