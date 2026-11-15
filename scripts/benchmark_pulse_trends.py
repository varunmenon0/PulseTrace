"""Score rolling estimates on phase-continuous, controlled synthetic pulse ramps."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from pulsetrace.controlled import make_controlled_video, ControlledTracker
from pulsetrace.pipeline import extract_video
from pulsetrace.regional_quality import write_regional_comparison
from pulsetrace.trends import write_trend


def score_windows(trend, case):
    rows=[]
    for row in trend['windows']:
        reference=case['start_bpm']+(case['end_bpm']-case['start_bpm'])*row['center_s']/case['seconds']
        errors={m:None if row['methods'][m]['bpm_candidate'] is None else row['methods'][m]['bpm_candidate']-reference
                for m in ('green','pos')}
        rows.append(dict(row, injected_window_mean_bpm=reference, errors_bpm=errors))
    return rows


def summarize(rows):
    result={}
    for method in ('green','pos'):
        errors=[abs(r['errors_bpm'][method]) for r in rows if r['errors_bpm'][method] is not None]
        result[method]=dict(total_windows=len(rows),estimated_windows=len(errors),
            coverage=len(errors)/len(rows) if rows else 0.,
            mae_against_injected_window_mean=float(np.mean(errors)) if errors else None,
            max_error_bpm=float(max(errors)) if errors else None)
    return result


def run(protocol, output):
    if protocol['window_seconds']!=12 or protocol['step_seconds']!=6 or protocol['codec']!='FFV1':
        raise ValueError('Protocol must match fixed 12-second/6-second windows and FFV1 encoding')
    names=[c['name'] for c in protocol['cases']]
    if not names or len(set(names))!=len(names) or any(Path(n).name!=n or n in ('.','..') for n in names):
        raise ValueError('Need unique simple case names')
    output.mkdir(parents=True,exist_ok=True)
    cases=[]
    for case in protocol['cases']:
        folder=output/case['name'];folder.mkdir(exist_ok=True)
        video=folder/'synthetic.avi'
        metadata=make_controlled_video(video,bpm=case['start_bpm'],end_bpm=case['end_bpm'],
            seconds=case['seconds'],fps=case['fps'],seed=protocol['seed'],profile=protocol['profile'])
        extraction=extract_video(video,ControlledTracker(),patches=True)
        if len(extraction.time)!=metadata['encoded_frames']:
            raise ValueError('Decoded frame count differs from fixture truth')
        regional=write_regional_comparison(extraction,folder,consensus_policy=protocol['consensus_policy'])
        trend=write_trend(regional,folder)
        # Fixture truth is consulted only after signal estimation and exclusions.
        rows=score_windows(trend,case)
        cases.append(dict(case=case,fixture=metadata,decoded_frames=len(extraction.time),
            video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
            patch_valid_frame_fraction={n:float(np.mean(v>0)) for n,v in extraction.patch_pixels.items()},
            metrics=summarize(rows),windows=rows))
    return dict(experiment='Controlled synthetic windowed pulse tracking',protocol=protocol,
                cases=cases,metrics=summarize([w for case in cases for w in case['windows']]),
                versions={n:importlib.metadata.version(n) for n in ('numpy','scipy','opencv-contrib-python')},
                timing='Offline 12-second window estimates at centers; available at ends',
                reference='Analytic mean of the injected linear rate; not supplied to the estimator')


def plot_summary(result, output):
    fig,axes=plt.subplots(1,len(result['cases']),figsize=(12,3.8),constrained_layout=True,squeeze=False)
    for ax,record in zip(axes[0],result['cases']):
        case=record['case'];t=np.linspace(0,case['seconds'],200)
        truth=case['start_bpm']+(case['end_bpm']-case['start_bpm'])*t/case['seconds']
        ax.plot(t,truth,'--',color='.5',label='Injected rate')
        for method,marker,color in (('green','x','#48a868'),('pos','o','#377bb5')):
            centers=[r['center_s'] for r in record['windows']]
            bpm=[np.nan if r['methods'][method]['bpm_candidate'] is None else r['methods'][method]['bpm_candidate'] for r in record['windows']]
            ax.plot(centers,bpm,marker+'-',color=color,label=method.upper(),markersize=4,fillstyle='none')
        ax.set(xlabel='Window center (seconds)',ylabel='BPM',
               ylim=(min(case['start_bpm'],case['end_bpm'])-5,max(case['start_bpm'],case['end_bpm'])+5),
               title=f"{case['name'].replace('_',' ').title()} · {case['fps']} FPS input")
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('PulseTrace · tracking a controlled changing pulse',fontsize=13)
    for suffix in ('png','svg'):fig.savefig(output/('summary.'+suffix),dpi=160)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=Path(__file__).resolve().parents[1]/'examples/pulse-trends/protocol.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();data=args.protocol.read_bytes()
    result=run(json.loads(data),args.output)
    result['protocol_sha256']=hashlib.sha256(data).hexdigest()
    (args.output/'benchmark.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    plot_summary(result,args.output)


if __name__=='__main__':main()
