"""Paired independent-background experiments; not natural pulse validation."""
import argparse
from itertools import product
import hashlib
import json
from pathlib import Path

import numpy as np

from compare_extraction import estimate, experiment_provenance, metrics, stress_fixture
from pulsetrace.extraction_experiments import METHODS
from pulsetrace.lighting import build_reference, screen_candidate


def reference_fixture(protocol,time,profile,seed,bpm,mode):
    if mode not in protocol['reference_modes']:raise ValueError('Unknown reference mode')
    if mode=='missing':return None
    p=protocol['reference'];base=np.array(p['base_rgb'],float)
    rgb=np.broadcast_to(base,(len(time),3)).copy()
    if mode!='face_only_light':
        if profile in ('common_light','two_lights'):
            light=protocol['common_light']
            rgb*=1+light['relative_amplitude']*np.sin(2*np.pi*light['frequency_hz']*time)[:,None]
        if profile in ('colored_light','two_lights'):
            light=protocol['colored_light']
            rgb+=base*np.array(p['colored_relative_rgb'])*np.sin(2*np.pi*light['frequency_hz']*time)[:,None]
    if mode=='pulse_leakage' and bpm is not None:
        rgb+=base*np.array(p['pulse_leakage_relative_rgb'])*np.sin(2*np.pi*bpm/60*time)[:,None]
    if profile!='flat':
        rng=np.random.default_rng(seed+p['noise_seed_offset'])
        rgb+=base*protocol['relative_noise_std']*rng.normal(size=rgb.shape)
    return rgb


def score(rows,method,stage):
    present=[r for r in rows if r['injected_bpm'] is not None]
    absent=[r for r in rows if r['injected_bpm'] is None]
    converted=[dict(injected_bpm=r['injected_bpm'],estimates={method:r[stage][method]}) for r in present]
    result=metrics(converted,method)
    result['correct_retained']=sum(r[stage][method]['bpm'] is not None and
        abs(r[stage][method]['bpm']-r['injected_bpm'])<=5 for r in present)
    result['wrong_retained']=result['estimated']-result['correct_retained']
    raw_correct=sum(r['raw'][method]['bpm'] is not None and
        abs(r['raw'][method]['bpm']-r['injected_bpm'])<=5 for r in present)
    raw_wrong=sum(r['raw'][method]['bpm'] is not None and
        abs(r['raw'][method]['bpm']-r['injected_bpm'])>5 for r in present)
    result.update(correct_lost=raw_correct-result['correct_retained'],
        wrong_removed=raw_wrong-result['wrong_retained'],
        pulse_absent_cases=len(absent),
        spurious_candidates=sum(r[stage][method]['bpm'] is not None for r in absent))
    return result


def run(protocol):
    rows=[]
    conditions=list(product(range(len(protocol['base_colors'])),
        range(len(protocol['relative_pulse_colors'])),protocol['rates_bpm'],protocol['fps'],
        protocol['profiles'],protocol['seeds']))
    conditions.extend((base,None,None,fps,profile,seed) for base,fps,profile,seed in
        product(range(len(protocol['base_colors'])),protocol['fps'],protocol['negative_controls'],protocol['seeds']))
    for base,direction,bpm,fps,profile,seed in conditions:
        t,rgb=stress_fixture(protocol,base,direction,bpm,fps,profile,seed)
        raw={m:estimate(t,rgb,m) for m in protocol['methods']}
        for mode in protocol['reference_modes']:
            bg=reference_fixture(protocol,t,profile,seed,bpm,mode)
            reference=build_reference(t,bg)
            screened={m:screen_candidate(raw[m]['bpm'],reference) for m in protocol['methods']}
            digest=None if bg is None else hashlib.sha256(t.tobytes()+bg.tobytes()).hexdigest()
            rows.append(dict(base_color_index=base,pulse_color_index=direction,injected_bpm=bpm,
                fps=fps,profile=profile,seed=seed,reference_mode=mode,
                face_sha256=hashlib.sha256(t.tobytes()+rgb.tobytes()).hexdigest(),
                reference_sha256=digest,reference_status=reference.status,raw=raw,screened=screened))
    summary={}
    for mode in protocol['reference_modes']:
        selected=[r for r in rows if r['reference_mode']==mode]
        summary[mode]={stage:{m:score(selected,m,stage) for m in protocol['methods']}
                       for stage in ('raw','screened')}
    return dict(synthetic=True,fixture_level='Paired RGB means; no video, tracking or natural reference',
                metrics=summary,cases=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,
        default=Path(__file__).parents[1]/'examples/extraction-experiments/lighting-protocol.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();data=args.protocol.read_bytes();protocol=json.loads(data)
    if tuple(protocol['methods'])!=METHODS:raise ValueError('Protocol methods differ from fixed variants')
    expected=dict(band_bpm=[40,200],overlap_half_width_hz=.15,minimum_band_power_fraction=.35)
    if any(protocol['screen'].get(k)!=v for k,v in expected.items()):
        raise ValueError('Protocol screen settings differ from the fixed implementation')
    result=run(protocol)
    from pulsetrace import lighting
    result.update(protocol=protocol,**experiment_provenance(data))
    result['experiment_source_sha256'].update({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__),Path(lighting.__file__))})
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'lighting-benchmark.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result['metrics'],indent=2))


if __name__=='__main__':main()
