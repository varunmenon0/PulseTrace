"""Summarize matched real-video sampling outcomes and area-flag diagnostics."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from evaluate_regional_quality import load_cache
from pulsetrace.quality import analyze_segments


def compare(integer,fractional):
    if integer['failures'] or fractional['failures']:raise ValueError('Resolve or explicitly report failed records before pooling')
    pairs=[]
    if [r['recording'] for r in integer['records']] != [r['recording'] for r in fractional['records']]:
        raise ValueError('Paired recordings differ')
    for a,b in zip(integer['records'],fractional['records']):
        if a['input']['video_sha256']!=b['input']['video_sha256'] or a['reference_sha256']!=b['reference_sha256']:
            raise ValueError('Paired sources differ')
        if len(a['windows'])!=len(b['windows']):raise ValueError('Paired window counts differ')
        for x,y in zip(a['windows'],b['windows']):
            if (x['start_s'],x['end_s'],x['nominal_reference_bpm'])!=(y['start_s'],y['end_s'],y['nominal_reference_bpm']):
                raise ValueError('Paired window timing/reference differs')
            pairs.append((a['recording'],x,y))
    metrics={}
    for method in ('pos','green'):
        metrics[method]={}
        for layout in ('three_regions','twelve_patches'):
            groups={'common':[],'new':[],'lost':[]}
            for subject,a,b in pairs:
                x,y=[r['policies']['full']['methods'][method][layout]['error_bpm'] for r in (a,b)]
                if x is not None and y is not None:groups['common'].append((x,y))
                elif y is not None:groups['new'].append(dict(recording=subject,start_s=a['start_s'],error_bpm=y))
                elif x is not None:groups['lost'].append(dict(recording=subject,start_s=a['start_s'],error_bpm=x))
            metrics[method][layout]=dict(common_windows=len(groups['common']),
                integer_common_mae=float(np.mean(np.abs(np.array(groups['common'])[:,0]))) if groups['common'] else None,
                fractional_common_mae=float(np.mean(np.abs(np.array(groups['common'])[:,1]))) if groups['common'] else None,
                newly_scorable=groups['new'],lost=groups['lost'])
    return metrics


def plot(integer,fractional,output):
    a,b=[r['metrics']['pos']['twelve_patches']['full'] for r in (integer,fractional)]
    fig,axes=plt.subplots(1,2,figsize=(9,3.8),constrained_layout=True)
    for ax,values,label,title in (
        (axes[0],[a['scorable_windows'],b['scorable_windows']],'Scorable windows','Coverage · 17 reference-valid windows'),
        (axes[1],[a['mae_against_device_bpm'],b['mae_against_device_bpm']],'Mean absolute difference (BPM)','Accepted-set device-label difference')):
        bars=ax.bar(['Integer','Fractional'],values,color=['#ca8742','#377bb5'],width=.55)
        ax.bar_label(bars,labels=[f'{v:g}' if isinstance(v,int) else f'{v:.3f}' for v in values],padding=4)
        ax.set(ylabel=label,title=title,ylim=(0,max(values)*1.25));ax.grid(axis='y',alpha=.2)
    fig.suptitle('PulseTrace · aggregate paired real-video benchmark')
    for suffix in ('png','svg'):fig.savefig(output/('summary.'+suffix),dpi=160)
    plt.close(fig)


def aggregate(result):
    """Public summary contains cohort metrics, without per-record pulse outcomes."""
    import copy
    result=copy.deepcopy(result)
    for methods in result['paired'].values():
        for layout in methods.values():
            for kind in ('newly_scorable','lost'):
                rows=layout.pop(kind)
                errors=[abs(r['error_bpm']) for r in rows]
                layout[kind+'_windows']=len(rows)
                layout[kind+'_mae']=float(np.mean(errors)) if errors else None
                layout[kind+'_max_difference_bpm']=max(errors) if errors else None
    result['quality_events']={sampler:dict(recordings=len(records),raw_flagged_frames={
        cause:sum(r['raw_flagged_frames'][cause] for r in records.values())
        for cause in ('displacement','patch_area','missing')}) for sampler,records in result['quality_events'].items()}
    for key in ('integer_metrics','fractional_metrics'):
        for method in result[key].values():
            for layout in method.values():layout['paired'].pop('newly_scorable_errors_bpm',None)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    integer,fractional=[json.loads((args.root/(s+'-evaluation')/'summary.json').read_text()) for s in ('integer','fractional')]
    result=dict(paired=compare(integer,fractional),quality_events={},
        integer_metrics=integer['metrics'],fractional_metrics=fractional['metrics'])
    for name,report in (('integer',integer),('fractional',fractional)):
        result['quality_events'][name]={}
        for record in report['records']:
            e=load_cache(args.root/name/record['recording']/'extraction.npz')
            quality=analyze_segments(e,min_seconds=1e6)
            result['quality_events'][name][record['recording']]=dict(event_counts=quality['event_counts'],
                raw_flagged_frames={n:c['raw_flagged_frames'] for n,c in quality['exclusion_causes'].items()})
    (args.output/'paired-summary.json').write_text(json.dumps(aggregate(result),indent=2,allow_nan=False)+'\n')
    plot(integer,fractional,args.output)


if __name__=='__main__':main()
