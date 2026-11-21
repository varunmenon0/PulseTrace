"""Paired, fixed extraction experiments; natural session outputs remain private."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from pulsetrace.extraction_experiments import METHODS, analyze_variant
from pulsetrace.patches import PATCHES, consensus
from pulsetrace.regional_quality import build_regional_comparison
from pulsetrace.sample_archive import SampleReader, provenance
from pulsetrace.sampling import samples_to_extraction


def fixture(protocol, bpm, fps, profile, timing, seed):
    rng=np.random.default_rng(seed)
    t=np.arange(round(protocol['seconds']*fps))/fps
    if timing=='jitter_drop':
        t[1:-1]+=protocol['jitter_drop']['jitter_seconds']*np.sin(np.arange(len(t)-2))
    phase=rng.uniform(0,2*np.pi)
    scale=protocol.get(profile,{}).get('pulse_scale',1.)
    pulse=np.sin(2*np.pi*bpm/60*t+phase)
    base=np.array(protocol['base_rgb'],float)
    rgb=base+scale*pulse[:,None]*np.array(protocol['pulse_rgb_amplitude'])
    if profile=='common_light':
        p=protocol[profile];rgb*=1+p['relative_amplitude']*np.sin(2*np.pi*p['frequency_hz']*t)[:,None]
    if profile in ('chromatic_drift','chromatic_interference'):
        p=protocol[profile];rgb+=np.sin(2*np.pi*p['frequency_hz']*t)[:,None]*base*np.array(p['relative_rgb'])
    noise=protocol.get(profile,{}).get('noise_std',protocol['noise_std'])
    rgb+=rng.normal(0,noise,rgb.shape)
    if timing=='jitter_drop':
        keep=np.arange(len(t))%protocol['jitter_drop']['drop_every_nth_frame']!=17
        t,rgb=t[keep],rgb[keep]
    return t,rgb


def estimate(t,rgb,method,min_seconds=10.):
    if not len(rgb) or not np.isfinite(rgb).all() or not (rgb>0).all():
        return dict(bpm=None,peak_fraction=None,error='Missing or invalid selected RGB')
    try:r=analyze_variant(t,rgb,method,min_seconds=min_seconds)
    except ValueError as exc:return dict(bpm=None,peak_fraction=None,error=str(exc))
    return dict(bpm=r.bpm,peak_fraction=r.peak_fraction,warnings=r.warnings)


def metrics(rows,method):
    errors=[abs(r['estimates'][method]['bpm']-r['injected_bpm']) for r in rows
            if r['estimates'][method]['bpm'] is not None]
    return dict(cases=len(rows),estimated=len(errors),abstained=len(rows)-len(errors),
                coverage=len(errors)/len(rows) if rows else 0.,
                accepted_mae_bpm=float(np.mean(errors)) if errors else None,
                accepted_max_error_bpm=max(errors) if errors else None,
                accepted_errors_over_5_bpm=sum(e>5 for e in errors))


def synthetic(protocol):
    rows=[]
    for group,seeds in [('development',protocol['development_seeds']),('heldout',protocol['heldout_seeds'])]:
        for seed in seeds:
            for fps in protocol['fps']:
                for bpm in protocol['rates_bpm']:
                    for profile in protocol['profiles']:
                        for timing in protocol['timing']:
                            t,rgb=fixture(protocol,bpm,fps,profile,timing,seed)
                            # Reference BPM is only used by scoring after all methods run.
                            estimates={m:estimate(t,rgb,m) for m in protocol['methods']}
                            digest=hashlib.sha256(t.tobytes()+rgb.tobytes()).hexdigest()
                            rows.append(dict(group=group,seed=seed,fps=fps,injected_bpm=bpm,
                                profile=profile,timing=timing,input_sha256=digest,estimates=estimates))
    summary={}
    for group in ('development','heldout'):
        selected=[r for r in rows if r['group']==group]
        summary[group]=dict(overall={m:metrics(selected,m) for m in protocol['methods']},
            profiles={p:{m:metrics([r for r in selected if r['profile']==p],m) for m in protocol['methods']}
                      for p in protocol['profiles']})
    return dict(synthetic=True,fixture_level='RGB means only; no video decoding or model tracking',
                metrics=summary,cases=rows)


def natural(source,methods):
    with SampleReader(source) as reader:
        header=reader.header;samples=list(reader)
    if any(s.reset_reason is not None for s in samples) or any(b.time-a.time>.25 for a,b in zip(samples,samples[1:])):
        raise ValueError('Extraction comparison currently requires a single session without resets')
    e=samples_to_extraction(samples)
    config=header['metadata']['configuration']
    if config['consensus']!='patch':raise ValueError('This fixed experiment requires patch consensus')
    expected=dict(window_seconds=12.,step_seconds=6.,lookahead_seconds=.5,max_gap_seconds=.25)
    if any(config.get(k)!=v for k,v in expected.items()):
        raise ValueError('Archive timing differs from the fixed comparison protocol')
    report=build_regional_comparison(e,window_policy=config['window_policy'])
    windows=[]
    for row in report['windows']:
        if row['end_s']+.5>e.time[-1]+1e-9:continue  # Same finalization deadlines as live replay.
        if config['window_policy']=='continuous':
            start,end=row['analysis_start_s'],row['analysis_end_s']
            chosen=np.zeros(len(e.time),bool) if start is None else (e.time>=start)&(e.time<=end)
        else:
            chosen=(e.time>=row['start_s'])&(e.time<row['end_s'])
            start=float(e.time[chosen][0]) if chosen.any() else None
            end=float(e.time[chosen][-1]) if chosen.any() else None
        outcomes={}
        for m in methods:
            patches={n:estimate(e.time[chosen],rgb[chosen],m,
                    11.9 if config['window_policy']=='full' else 10.) for n,rgb in e.patch_rgb.items()}
            eligible={n:d['bpm'] if row['usable_regions'][PATCHES[n]] else None for n,d in patches.items()}
            vote=consensus(eligible,PATCHES)
            if m in ('green','pos'):
                original=row['methods'][m]['twelve_patches']['regional_gate']
                if vote!=dict(bpm_candidate=original['bpm_candidate'],support=original['support']):
                    raise ValueError('Original-method paired baseline changed')
            outcomes[m]=dict(patches=patches,consensus=vote)
        windows.append(dict(start_s=row['start_s'],end_s=row['end_s'],analysis_start_s=start,
                            analysis_end_s=end,usable_regions=row['usable_regions'],methods=outcomes))
    return dict(synthetic=header['metadata'].get('synthetic',False),windows=windows,
                available_windows={m:sum(w['methods'][m]['consensus']['bpm_candidate'] is not None for w in windows)
                                   for m in methods},
                reference_status='No per-window independent reference is scored; no preferred method selected',
                archived_configuration=config)


def experiment_provenance(data):
    from pulsetrace import extraction_experiments
    sources=[Path(__file__),Path(extraction_experiments.__file__)]
    return dict(protocol_sha256=hashlib.sha256(data).hexdigest(),provenance=provenance(),
                experiment_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,
        default=Path(__file__).parents[1]/'examples/extraction-experiments/protocol.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=Path,help='Optional private development session')
    args=parser.parse_args();data=args.protocol.read_bytes();protocol=json.loads(data)
    if tuple(protocol['methods'])!=METHODS:raise ValueError('Protocol methods do not match fixed variants')
    if args.samples and args.output.resolve()==args.samples.parent.resolve():
        raise ValueError('Preserve original recording folder; choose separate output')
    args.output.mkdir(parents=True,exist_ok=True)
    result=synthetic(protocol)
    result.update(protocol=protocol,**experiment_provenance(data))
    (args.output/'synthetic-benchmark.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result['metrics'],indent=2),flush=True)
    if args.samples:
        result=natural(args.samples,protocol['methods'])
        result.update(**experiment_provenance(data))
        digest=hashlib.sha256(args.samples.read_bytes()).hexdigest()
        result['source_sha256']=digest
        (args.output/'private-session-comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(json.dumps(dict(private_session_windows=len(result['windows']),available_windows=result['available_windows'])),flush=True)


if __name__=='__main__':main()
