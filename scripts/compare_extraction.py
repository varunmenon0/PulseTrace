"""Paired, fixed extraction experiments; natural session outputs remain private."""
import argparse
import hashlib
import json
from itertools import product
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


def stress_fixture(protocol, base_index, pulse_index, bpm, fps, profile, seed):
    """Arbitrary color directions, including controls with no pulse component."""
    rng=np.random.default_rng(seed)
    t=np.arange(round(protocol['seconds']*fps))/fps
    timing=protocol['timing']
    t[1:-1]+=timing['jitter_seconds']*np.sin(np.arange(len(t)-2))
    base=np.array(protocol['base_colors'][base_index],float)
    rgb=np.broadcast_to(base,(len(t),3)).copy()
    phase=rng.uniform(0,2*np.pi)
    if pulse_index is not None:
        direction=np.array(protocol['relative_pulse_colors'][pulse_index])
        rgb+=base*direction*np.sin(2*np.pi*bpm/60*t+phase)[:,None]
    if profile in ('common_light','two_lights'):
        light=protocol['common_light']
        rgb*=1+light['relative_amplitude']*np.sin(2*np.pi*light['frequency_hz']*t)[:,None]
    if profile in ('colored_light','two_lights'):
        light=protocol['colored_light']
        rgb+=base*np.array(light['relative_rgb'])*np.sin(2*np.pi*light['frequency_hz']*t)[:,None]
    if profile!='flat':
        rgb+=base*protocol['relative_noise_std']*rng.normal(size=rgb.shape)
    keep=np.arange(len(t))%timing['drop_every_nth_frame']!=timing['drop_index_remainder']
    return t[keep],rgb[keep]


def stress_summary(rows, methods):
    present=[r for r in rows if r['injected_bpm'] is not None]
    absent=[r for r in rows if r['injected_bpm'] is None]
    common=[r for r in present if all(r['estimates'][m]['bpm'] is not None for m in methods)]
    controls={}
    for profile in sorted({r['profile'] for r in absent}):
        selected=[r for r in absent if r['profile']==profile]
        controls[profile]={}
        for m in methods:
            count=sum(r['estimates'][m]['bpm'] is not None for r in selected)
            controls[profile][m]=dict(cases=len(selected),spurious_candidates=count,
                                    spurious_candidate_fraction=count/len(selected))
    return dict(pulse_present={m:metrics(present,m) for m in methods},
                common_accepted_set={m:metrics(common,m) for m in methods},
                pulse_present_by_profile={p:{m:metrics([r for r in present if r['profile']==p],m)
                                            for m in methods} for p in sorted({r['profile'] for r in present})},
                pulse_present_by_color_direction={str(i):{m:metrics([r for r in present if r['pulse_color_index']==i],m)
                                                          for m in methods} for i in sorted({r['pulse_color_index'] for r in present})},
                pulse_absent=controls)


def synthetic_stress(protocol):
    rows=[]
    conditions=list(product(range(len(protocol['base_colors'])),
        range(len(protocol['relative_pulse_colors'])),protocol['rates_bpm'],protocol['fps'],
        protocol['profiles'],protocol['seeds']))
    conditions.extend((base,None,None,fps,profile,seed) for base,fps,profile,seed in
        product(range(len(protocol['base_colors'])),protocol['fps'],protocol['negative_controls'],protocol['seeds']))
    for base,direction,bpm,fps,profile,seed in conditions:
        t,rgb=stress_fixture(protocol,base,direction,bpm,fps,profile,seed)
        estimates={m:estimate(t,rgb,m) for m in protocol['methods']}
        rows.append(dict(base_color_index=base,pulse_color_index=direction,injected_bpm=bpm,
                         fps=fps,profile=profile,seed=seed,
                         input_sha256=hashlib.sha256(t.tobytes()+rgb.tobytes()).hexdigest(),estimates=estimates))
    return dict(synthetic=True,fixture_level='RGB stress signals; not skin-tone or natural-video validation',
                metrics=stress_summary(rows,protocol['methods']),cases=rows)


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
    parser.add_argument('--suite',choices=('initial','stress'),default='initial')
    parser.add_argument('--protocol',type=Path,
        help='Defaults to the frozen protocol for the selected suite')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=Path,help='Optional private development session')
    args=parser.parse_args()
    if args.protocol is None:
        args.protocol=Path(__file__).parents[1]/'examples/extraction-experiments'/(
            'stress-protocol.json' if args.suite=='stress' else 'protocol.json')
    data=args.protocol.read_bytes();protocol=json.loads(data)
    if tuple(protocol['methods'])!=METHODS:raise ValueError('Protocol methods do not match fixed variants')
    if (protocol.get('suite')=='color-lighting-stress') != (args.suite=='stress'):
        raise ValueError('Protocol does not match the selected suite')
    if args.samples and args.output.resolve()==args.samples.parent.resolve():
        raise ValueError('Preserve original recording folder; choose separate output')
    args.output.mkdir(parents=True,exist_ok=True)
    result=synthetic_stress(protocol) if args.suite=='stress' else synthetic(protocol)
    result.update(protocol=protocol,**experiment_provenance(data))
    filename='stress-benchmark.json' if args.suite=='stress' else 'synthetic-benchmark.json'
    (args.output/filename).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result['metrics'],indent=2),flush=True)
    if args.samples:
        result=natural(args.samples,protocol['methods'])
        result.update(**experiment_provenance(data))
        digest=hashlib.sha256(args.samples.read_bytes()).hexdigest()
        result['source_sha256']=digest
        (args.output/'private-session-comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(json.dumps(dict(private_session_windows=len(result['windows']),available_windows=result['available_windows'])),flush=True)


if __name__=='__main__':main()
