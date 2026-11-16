"""Reproduce real-video decisions and score quality-selected continuous support."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from benchmark_ubfc import load_reference
from evaluate_regional_quality import load_cache
from pulsetrace.regional_quality import write_regional_comparison


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_window(rt, rb, start, end):
    """Same device-reference validity rules, evaluated on actual analyzed support."""
    if start is None or end is None or start < rt[0] or end > rt[-1]:
        return None
    left=max(0,np.searchsorted(rt,start,side='right')-1)
    right=min(len(rt),np.searchsorted(rt,end,side='left')+1)
    if np.any((rb[left:right]<40)|(rb[left:right]>200)) or np.any(np.diff(rt[left:right])>2.5):
        return None
    return float(np.median(np.interp(np.linspace(start,end,361),rt,rb)))


def failure_reason(row, detail, zones):
    if detail['bpm_candidate'] is not None:return None
    if sum(row['usable_regions'].values())<2:return 'quality_exclusions'
    candidates=detail['individual_candidates']
    if len({zones[n] for n,v in candidates.items() if v is not None})<2:
        return 'insufficient_spectral_support'
    return 'no_majority_consensus'


def summarize(records):
    result={}
    for method in ('pos','green'):
        result[method]={}
        for layout in ('three_regions','twelve_patches'):
            d={}
            for policy in ('full','continuous'):
                rows=[w for r in records for w in r['windows']]
                details=[w['policies'][policy]['methods'][method][layout] for w in rows]
                errors=[v['error_bpm'] for v in details if v['error_bpm'] is not None]
                d[policy]=dict(total_windows=len(rows),reference_valid_windows=sum(w['nominal_reference_bpm'] is not None for w in rows),
                    estimated_windows=sum(v['bpm_candidate'] is not None for v in details),scorable_windows=len(errors),
                    mae_against_device_bpm=float(np.mean(np.abs(errors))) if errors else None,
                    max_difference_bpm=float(np.max(np.abs(errors))) if errors else None,
                    rejection_counts=dict(Counter(v['rejection_reason'] for v in details if v['rejection_reason'])),
                    subjects_with_scored_estimates=sum(any(w['policies'][policy]['methods'][method][layout]['error_bpm'] is not None for w in r['windows']) for r in records))
            pairs={'common':[],'new':[],'lost':[]}
            for row in [w for r in records for w in r['windows']]:
                a,b=[row['policies'][p]['methods'][method][layout]['error_bpm'] for p in ('full','continuous')]
                if a is not None and b is not None:pairs['common'].append((a,b))
                elif b is not None:pairs['new'].append(b)
                elif a is not None:pairs['lost'].append(a)
            d['paired']=dict(common_windows=len(pairs['common']),
                full_common_mae=float(np.mean(np.abs(np.array(pairs['common'])[:,0]))) if pairs['common'] else None,
                continuous_common_mae=float(np.mean(np.abs(np.array(pairs['common'])[:,1]))) if pairs['common'] else None,
                newly_scorable_windows=len(pairs['new']),newly_scorable_mae=float(np.mean(np.abs(pairs['new']))) if pairs['new'] else None,
                newly_scorable_errors_bpm=pairs['new'],lost_windows=len(pairs['lost']))
            result[method][layout]=d
    return result


def evaluate(folder, output):
    from pulsetrace.patches import PATCHES
    from pulsetrace.regions import REGIONS
    cache=folder/'extraction.npz'
    benchmark=folder/'benchmark.json'
    if not cache.exists():cache=folder/'benchmark/extraction.npz';benchmark=folder/'benchmark/benchmark.json'
    original=json.loads(benchmark.read_text())
    reference=folder/'ground_truth.txt'
    if digest(reference)!=original['input']['reference_sha256']:raise ValueError('Reference identity differs from extraction benchmark')
    e=load_cache(cache)
    if len(e.time)!=original['input']['decoded_frames'] or not np.isclose(e.time[-1],original['input']['duration_s']):
        raise ValueError('Cache and benchmark timing differ')
    rt,rb=load_reference(reference)
    reports={p:write_regional_comparison(e,output/p,window_policy=p) for p in ('full','continuous')}
    windows=[]
    for a,b in zip(reports['full']['windows'],reports['continuous']['windows']):
        nominal=reference_window(rt,rb,a['start_s'],a['end_s'])
        row=dict(start_s=a['start_s'],end_s=a['end_s'],nominal_reference_bpm=nominal,policies={})
        for policy,source in (('full',a),('continuous',b)):
            start=source.get('analysis_start_s',source['start_s']);end=source.get('analysis_end_s',source['end_s'])
            ref=reference_window(rt,rb,start,end)
            detail=dict(analysis_start_s=start,analysis_end_s=end,reference_bpm=ref,
                usable_regions=source['usable_regions'],sample_loss_regions=source['sample_loss_regions'],methods={})
            for method in ('pos','green'):
                detail['methods'][method]={}
                for layout,zones in (('three_regions',{n:n for n in REGIONS}),('twelve_patches',PATCHES)):
                    decision=source['methods'][method][layout]['regional_gate']
                    value=decision['bpm_candidate']
                    detail['methods'][method][layout]=dict(decision,
                        rejection_reason=failure_reason(source,decision,zones),
                        error_bpm=None if value is None or ref is None or nominal is None else value-ref)
            row['policies'][policy]=detail
        windows.append(row)
    # Reproduce historical baseline votes, rather than trusting a new score alone.
    historical=folder/'regional_comparison.json'
    reproduced=None
    if historical.exists():
        old=json.loads(historical.read_text())['windows']
        if len(old)!=len(reports['full']['windows']):raise ValueError('Historical windows differ')
        for before,after in zip(old,reports['full']['windows']):
            if (before['start_s'],before['end_s'])!=(after['start_s'],after['end_s']):raise ValueError('Historical timing differs')
            for method in ('pos','green'):
                for layout in ('three_regions','twelve_patches'):
                    x=before['methods'][method][layout]['regional_gate']['bpm_candidate']
                    y=after['methods'][method][layout]['regional_gate']['bpm_candidate']
                    if (x is None)!=(y is None) or (x is not None and not np.isclose(x,y,atol=1e-8,rtol=0)):
                        raise ValueError('Historical baseline vote did not reproduce')
        reproduced=True
    record=dict(recording=folder.name,input=original['input'],cache_sha256=digest(cache),
        reference_sha256=digest(reference),sampling=original.get('sampling',{'sampling':'legacy integer landmarks'}),
        historical_baseline_reproduced=reproduced,windows=windows)
    record['metrics']=summarize([record])
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cohort',choices=['development','fresh'],required=True)
    p.add_argument('--protocol',type=Path,default=Path(__file__).resolve().parents[1]/'examples/real-video-recovery/protocol.json')
    args=p.parse_args();protocol=json.loads(args.protocol.read_text())
    records=[];failures=[]
    args.output.mkdir(parents=True,exist_ok=True)
    for subject in protocol[args.cohort+'_subjects']:
        try:
            records.append(evaluate(args.root/subject,args.output/subject))
            print(subject,'completed',flush=True)
        except (ValueError,OSError,KeyError) as error:
            failures.append(dict(recording=subject,error=str(error)));print(subject,str(error),flush=True)
    result=dict(cohort=args.cohort,protocol=protocol,protocol_sha256=digest(args.protocol),records=records,
        versions={n:importlib.metadata.version(n) for n in ('numpy','scipy','opencv-contrib-python','mediapipe')},
        failures=failures,metrics=summarize(records),reference='Stored device labels, assumed elapsed-time offset zero; waveform/device disagreements unresolved',
        comparison='Same nominal windows and quality thresholds; continuous policy scores the exact selected shorter support; accepted subsets and support can differ')
    (args.output/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
