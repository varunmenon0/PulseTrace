"""Generate, decode, and score the fixed synthetic-video proof-of-concept suite."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from pulsetrace.controlled import make_controlled_video, ControlledTracker, evaluate_controlled
from pulsetrace.pipeline import extract_video


def summarize(records):
    result = {}
    for group in sorted({r['case']['group'] for r in records}):
        selected = [r for r in records if r['case']['group'] == group]
        result[group] = dict(cases=len(selected), decoded_frames=sum(r['decoded_frames'] for r in selected),
                            shared_lighting_cue_cases=sum(r['estimates']['method_agreement']['shared_lighting_cue'] for r in selected),
                            methods={})
        for method in ('green', 'pos'):
            errors = [abs(r['errors_bpm'][method]) for r in selected if r['errors_bpm'][method] is not None]
            result[group]['methods'][method] = dict(estimated_cases=len(errors), total_cases=len(selected),
                coverage=len(errors)/len(selected),
                mae_against_injected_bpm=float(np.mean(errors)) if errors else None,
                max_error_bpm=float(max(errors)) if errors else None)
    return result


def benchmark(protocol, output):
    if protocol['codec'] != 'FFV1' or protocol['agreement_tolerance_bpm'] != 5:
        raise ValueError('Expected lossless encoding and the fixed 5 BPM agreement rule')
    names = [c['name'] for c in protocol['cases']]
    if not names or len(set(names)) != len(names) or any(Path(n).name != n or n in ('.', '..') for n in names):
        raise ValueError('Need unique, simple case names')
    records = []
    output.mkdir(parents=True, exist_ok=True)
    for case in protocol['cases']:
        video = output/(case['name']+'.avi')
        metadata = make_controlled_video(video, bpm=case['bpm'], fps=case['fps'],
            seconds=protocol['seconds'], seed=protocol['seed'], profile=case['profile'])
        tracker = ControlledTracker()
        extraction = extract_video(video, tracker, patches=True)
        if len(extraction.time) != metadata['encoded_frames']:
            raise ValueError('Decoded frame count does not match fixture truth')
        check = evaluate_controlled(extraction, tracker.background_rgb,
                                    consensus_policy=protocol['consensus_policy'])
        errors = {method: None if check['methods'][method]['patch_consensus']['bpm_candidate'] is None else
                  check['methods'][method]['patch_consensus']['bpm_candidate']-case['bpm']
                  for method in ('green', 'pos')}
        times = np.arange(metadata['encoded_frames'])/case['fps']
        np.savetxt(output/(case['name']+'_truth.csv'), np.column_stack([times, np.full(len(times), case['bpm'])]),
                   delimiter=',', header='time_s,injected_bpm', comments='')
        records.append(dict(case=case, fixture=metadata, decoded_frames=len(extraction.time),
            timing=dict(source_fps=extraction.metadata['source_fps'], timestamp_fallbacks=extraction.metadata['timestamp_fallbacks']),
            valid_frame_fraction={n: float(np.mean(v>0)) for n, v in extraction.pixels.items()},
            valid_patch_frame_fraction={n: float(np.mean(v>0)) for n, v in extraction.patch_pixels.items()},
            video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(), estimates=check, errors_bpm=errors))
    return dict(experiment='Encoded synthetic-video proof of concept with known rendered geometry',
                protocol=protocol, records=records, summary=summarize(records),
                versions={n: importlib.metadata.version(n) for n in ('numpy','scipy','opencv-contrib-python')},
                scoring='Injected BPM is used only after independent signal estimation',
                tracking='Known fixture coordinates; no model inference is measured')


def plot_summary(report, output):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), constrained_layout=True)
    first = output/(report['records'][0]['case']['name']+'.avi')
    capture = cv2.VideoCapture(str(first))
    try:
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise ValueError('Cannot read fixture preview')
    from pulsetrace.regions import extract_regions
    _, _, masks = extract_regions(frame, ControlledTracker().detect(frame, 0))
    yy, xx = np.indices(frame.shape[:2])
    for mask in masks.values():
        x, y, w, h = cv2.boundingRect(mask)
        left, top = xx < x+w/2, yy < y+h/2
        for selected in (left & top, ~left & top, left & ~top, ~left & ~top):
            contours, _ = cv2.findContours(((mask>0)&selected).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(frame,contours,-1,(0,230,240),1)
    axes[0].imshow(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    axes[0].axis('off')
    axes[0].set_title('Rendered face · 12 sampled patches', fontsize=10)
    clean = [r for r in report['records'] if r['case']['group']=='clean']
    axes[1].plot([40,190],[40,190],color='.7',linestyle='--',label='Injected BPM')
    for method, marker in (('green','x'),('pos','o')):
        values=[(r['case']['bpm'],r['estimates']['methods'][method]['patch_consensus']['bpm_candidate']) for r in clean]
        values=[v for v in values if v[1] is not None]
        if values:
            style=dict(facecolors='none',edgecolors='#377bb5') if marker=='o' else dict(color='#48a868')
            axes[1].scatter(*np.asarray(values).T,marker=marker,label=method.upper(),s=45,
                            **style)
    axes[1].set(xlabel='Injected BPM',ylabel='Estimated BPM',title=f'Clean controls · {len(clean)} clips')
    axes[1].legend(fontsize=8)
    challenge=next(r for r in report['records'] if r['case']['group']=='lighting_challenge')
    rates=[challenge['case']['bpm']]+[challenge['estimates']['methods'][m]['patch_consensus']['bpm_candidate'] for m in ('green','pos')]+[challenge['estimates']['background']['bpm_candidate']]
    heights=[v if v is not None else 0 for v in rates]
    axes[2].bar(['Injected','Green','POS','Background'],heights,color=['.6','#48a868','#377bb5','#db9b2c'])
    for i, value in enumerate(rates):
        axes[2].text(i,heights[i]+2,'None' if value is None else f'{value:.1f}',ha='center',fontsize=8)
    axes[2].set(ylabel='BPM',ylim=(0,max(heights)+20),title='Isolated periodic-lighting challenge')
    axes[2].tick_params(axis='x',labelsize=8)
    fig.suptitle('PulseTrace · controlled synthetic-video proof of concept',fontsize=13)
    for suffix in ('png','svg'):
        fig.savefig(output/('summary.'+suffix),dpi=160)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=Path(__file__).resolve().parents[1]/'examples/controlled-video/protocol.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=args.protocol.read_bytes()
    result=benchmark(json.loads(data),args.output)
    result['protocol_sha256']=hashlib.sha256(data).hexdigest()
    (args.output/'benchmark.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    plot_summary(result,args.output)


if __name__=='__main__':main()
