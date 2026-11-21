"""Private, observational audit of saved session spectra and existing votes.

No thresholds or estimates are changed. No expected BPM or reference range is
accepted. Session measurements and generated figures belong in local outputs/.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from pulsetrace.live import replay_samples
from pulsetrace.patches import PATCHES, consensus
from pulsetrace.regional_quality import build_regional_comparison
from pulsetrace.sample_archive import SampleReader
from pulsetrace.sampling import samples_to_extraction
from pulsetrace.signal import analyze
from pulsetrace.zone_consensus import hierarchical_consensus


def cluster_audit(candidates, zones, tolerance=5.):
    """Enumerate the existing patch policy's qualifying groups, including ties."""
    valid = sorted((value, name) for name,value in candidates.items() if value is not None)
    groups = [[name for value,name in valid[i:] if value <= low+tolerance]
              for i,(low,_) in enumerate(valid)]
    qualifying = [g for g in groups if len(g) >= 2 and len(g) > len(valid)/2
                  and len({zones[n] for n in g}) >= 2]
    best_size = max(map(len, qualifying), default=0)
    best = [g for g in qualifying if len(g) == best_size]
    decision = consensus(candidates, zones, tolerance=tolerance)
    reason = None if decision['bpm_candidate'] is not None else (
        'tied_largest_majorities' if len(best) > 1 else 'no_strict_cross_region_majority')
    return dict(valid_candidates=len(valid), largest_qualifying_group=best_size,
                equally_large_groups=len(best), groups=best, rejection_reason=reason,
                shared_patches_in_all_best_groups=sorted(set.intersection(*(set(g) for g in best))) if best else [],
                decision=decision)


def peak_summary(frequencies, power):
    band = (frequencies >= 40/60) & (frequencies <= 200/60)
    f, p = frequencies[band], power[band]
    if not len(p) or float(p.sum()) < 1e-16:
        return []
    indices = list(signal.find_peaks(p)[0])
    if len(p) == 1 or p[0] > p[1]: indices.append(0)
    if len(p) > 1 and p[-1] > p[-2]: indices.append(len(p)-1)
    indices = sorted(indices, key=lambda i:p[i], reverse=True)[:3]
    return [dict(bpm=float(f[i]*60), relative_peak_power=float(p[i]/p.max())) for i in indices]


def power_near(frequencies, power, bpm):
    if bpm is None:
        return None
    band = (frequencies >= 40/60) & (frequencies <= 200/60)
    total = float(power[band].sum())
    return float(power[band & (np.abs(frequencies-bpm/60) <= .15)].sum()/total) if total > 1e-16 else None


def scalar_spectrum(time, values, grid, fs):
    """Same band/trim/Welch setup for nuisance observations, never a pulse vote."""
    if not np.isfinite(values).all() or len(values) < 2 or np.any(np.diff(time) > .25):
        return None
    uniform = np.interp(grid, time, values)
    if np.std(uniform) < 1e-12:
        return dict(frequencies=np.array([]), power=np.array([]), peaks=[], std=0.)
    sos = signal.butter(4, [40/60,200/60], fs=fs, btype='bandpass', output='sos')
    filtered = signal.sosfiltfilt(sos, signal.detrend(uniform))
    trim = int(fs)
    central = filtered[trim:-trim]
    n = min(len(central), max(8,int(10*fs)))
    f,p = signal.welch(central,fs=fs,nperseg=n,nfft=max(n,4*n))
    return dict(frequencies=f,power=p,peaks=peak_summary(f,p),std=float(np.std(filtered)))


def event_windows(path):
    return [r for line in path.read_text().splitlines() if (r:=json.loads(line))['type']=='window']


def plot_spectra(number, record, curves, output):
    fig,axes = plt.subplots(3,2,figsize=(13,9),sharex=True,sharey=True,constrained_layout=True)
    colors = dict(tl='#377bb5',tr='#d97732',bl='#6e9a43',br='#9767a8')
    for i,zone in enumerate(('forehead','left_cheek','right_cheek')):
        for j,method in enumerate(('pos','green')):
            ax=axes[i,j]
            for quadrant,color in colors.items():
                result = curves.get((method,zone+'_'+quadrant))
                if result is not None:
                    band=(result.frequencies>=40/60)&(result.frequencies<=200/60)
                    p=result.power[band];maximum=float(p.max())
                    ax.plot(result.frequencies[band]*60,p/maximum if maximum else p,
                            color=color,lw=1.2,label=quadrant)
            parent=curves.get((method,zone))
            if parent is not None:
                band=(parent.frequencies>=40/60)&(parent.frequencies<=200/60)
                p=parent.power[band];maximum=float(p.max())
                ax.plot(parent.frequencies[band]*60,p/maximum if maximum else p,color='#222222',lw=2,label='parent ROI')
            for vote_method,color in (('pos','#ce3144'),('green','#24856b')):
                bpm=record['methods'][vote_method]['original_bpm']
                if bpm is not None:
                    ax.axvline(bpm,color=color,ls='--',lw=1,label=f'{vote_method.upper()} vote {bpm:.1f}')
            ax.set(title=f'{zone.replace("_"," ").title()} · {method.upper()}',xlim=(40,200),ylim=(0,1.08))
            ax.grid(alpha=.15)
            if i==2:ax.set_xlabel('Frequency expressed as BPM')
            if j==0:ax.set_ylabel('Power / own maximum')
            if i==0 and j==0:ax.legend(fontsize=7,ncol=2)
    fig.suptitle(f'Window {number}: {record["analysis_start_s"]:.2f}–{record["analysis_end_s"]:.2f}s\n'
                 'Separately normalized spectra; dashed lines are algorithm votes, not a pulse reference',fontsize=12)
    fig.savefig(output/f'window-{number}-spectra.png',dpi=160)
    plt.close(fig)


def run(source, events, output):
    source,events,output=Path(source),Path(events),Path(output)
    if output.resolve() == source.parent.resolve():
        raise ValueError('Use a separate output directory; preserve the original session')
    output.mkdir(parents=True,exist_ok=True)
    # Explicit full-session audit; its output remains private.
    replay = replay_samples(source,output/'verified-replay',verify=True)
    original=event_windows(events)
    reproduced=event_windows(output/'verified-replay/stream.jsonl')
    comparable=[{k:v for k,v in r.items() if k not in ('emitted_at_s','computation_seconds')} for r in original]
    if comparable != reproduced:
        raise ValueError('Original live events do not match the archived-sample replay')
    with SampleReader(source) as reader:
        header=reader.header
        samples=list(reader)
    if replay['resets']:
        raise ValueError('This detailed spectral audit currently requires a single uninterrupted session')
    e=samples_to_extraction(samples)
    config=header['metadata']['configuration']
    batch=build_regional_comparison(e,window_policy=config['window_policy'],
                                   consensus_policy=config['consensus'],window_starts=[r['start_s'] for r in original])
    records=[];plot_curves={}
    spectrum_file=(output/'spectra.csv').open('w',newline='')
    try:
        writer=csv.writer(spectrum_file);writer.writerow(['window','method','signal','frequency_hz','power'])
        for index,(live,row) in enumerate(zip(original,batch['windows']),1):
            start,end=live['analysis_start_s'],live['analysis_end_s']
            record=dict(window=index,start_s=live['start_s'],end_s=live['end_s'],
                        analysis_start_s=start,analysis_end_s=end,
                        usable_regions=live["quality"]["usable_regions_on_selected_support"],
                        methods={},signals={},nuisances={})
            for method in ('pos','green'):
                decision=live['quality']['pulse_methods'][method]['consensus']
                candidates=decision['eligible_candidates']
                record['methods'][method]=dict(original_bpm=decision['bpm_candidate'],
                    original_reason=decision['rejection_reason'], support=decision['support'],
                    cluster_audit=cluster_audit(candidates,PATCHES),
                    zone_policy=hierarchical_consensus(candidates,PATCHES),
                    parent_roi_policy=row['methods'][method]['three_regions']['regional_gate'])
            p,g=[record['methods'][m]['original_bpm'] for m in ('pos','green')]
            record['method_difference_bpm']=abs(p-g) if p is not None and g is not None else None
            curves={}
            if start is not None:
                chosen=(e.time>=start)&(e.time<=end)
                for method in ('pos','green'):
                    for name,values in {**e.rgb,**e.patch_rgb}.items():
                        rgb=values[chosen]
                        if not len(rgb) or not np.isfinite(rgb).all() or not (rgb>0).all():
                            continue
                        try:r=analyze(e.time[chosen],rgb,method=method,
                                      min_seconds=11.9 if config['window_policy']=='full' else 10.)
                        except ValueError:continue
                        curves[method,name]=r
                        record['signals'].setdefault(method,{})[name]=dict(bpm_candidate=r.bpm,
                            peak_fraction=r.peak_fraction, peaks=peak_summary(r.frequencies,r.power),
                            power_near_pos_vote=power_near(r.frequencies,r.power,p),
                            power_near_green_vote=power_near(r.frequencies,r.power,g),warnings=r.warnings)
                        for f,power in zip(r.frequencies,r.power):
                            if 40/60<=f<=200/60:writer.writerow([index,method,name,float(f),float(power)])
                        if method=='pos' and name in PATCHES:
                            zone=PATCHES[name]
                            nuisance_values=dict(patch_area=e.patch_pixels[name],
                                mean_brightness=values.mean(axis=1),
                                parent_center_x=e.geometry[zone][:,0],parent_center_y=e.geometry[zone][:,1])
                            for key,trace in nuisance_values.items():
                                nuisance=scalar_spectrum(e.time[chosen],trace[chosen],r.time,r.sample_rate)
                                if nuisance is not None:
                                    record['nuisances'].setdefault(name,{})[key]=dict(peaks=nuisance['peaks'],
                                        filtered_std=nuisance['std'],
                                        power_near_pos_vote=power_near(nuisance['frequencies'],nuisance['power'],p),
                                        power_near_green_vote=power_near(nuisance['frequencies'],nuisance['power'],g))
            records.append(record);plot_curves[index]=curves
    finally:
        spectrum_file.close()
    conflicts=sorted((r for r in records if r['method_difference_bpm'] is not None),
                     key=lambda r:r['method_difference_bpm'],reverse=True)
    for record in conflicts[:2]:plot_spectra(record['window'],record,plot_curves[record['window']],output)
    result=dict(source_sha256=replay['source_sha256'],events_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),
                exact_live_replay=True,batch_parity=replay['batch_parity'],configuration=config,windows=records,
                limitations=['No synchronized independent pulse reference; correctness of candidates is unknown',
                    'Existing alternative policies are paired observations, not selected improvements',
                    'Nuisance spectral overlap is association, not proof of lighting or motion artifacts',
                    'No thresholds, signal rules or live estimator decisions were changed'])
    (output/'audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (output/'window-summary.csv').open('w',newline='') as file:
        writer=csv.writer(file);writer.writerow(['window','start_s','end_s','pos_bpm','green_bpm','difference_bpm',
                                                'pos_cluster_reason','green_cluster_reason'])
        for r in records:writer.writerow([r['window'],r['start_s'],r['end_s'],r['methods']['pos']['original_bpm'],
            r['methods']['green']['original_bpm'],r['method_difference_bpm'],
            r['methods']['pos']['cluster_audit']['rejection_reason'],r['methods']['green']['cluster_audit']['rejection_reason']])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=Path,required=True)
    parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.samples,args.events,args.output)
    print(json.dumps(dict(windows=len(result['windows']),exact_live_replay=result['exact_live_replay'],
                          output=str(args.output)),indent=2))


if __name__=='__main__':main()
