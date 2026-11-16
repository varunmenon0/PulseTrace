"""Experimental local quality exclusions; original global gate stays the default."""
import json
from pathlib import Path

import numpy as np

from .regions import REGIONS
from .patches import PATCHES, consensus
from .quality import analyze_segments


def broad_color_steps(rgb, pairs, threshold):
    """Same-direction relative steps in at least two valid RGB channels."""
    change = np.zeros_like(rgb[1:], dtype=float)
    np.divide(np.diff(rgb, axis=0), rgb[:-1], out=change,
              where=np.broadcast_to(pairs[:, None], change.shape))
    return np.r_[False, pairs & ((np.sum(change > threshold, axis=1) >= 2) |
                                (np.sum(change < -threshold, axis=1) >= 2))]


def regional_masks(extraction, *, motion_threshold=.05, area_threshold=.10,
                   buffer_seconds=.5, max_gap=.25, area_policy="strict",
                   photometric_threshold=None):
    """Exclude locally; two displaced/unavailable parents exclude all.

    Optional photometric steps reject a region independently of area changes.
    The default None keeps that unvalidated guard disabled.
    """
    if not np.isfinite([motion_threshold,area_threshold,buffer_seconds,max_gap]).all() or min(motion_threshold,area_threshold,max_gap)<=0 or buffer_seconds<0:
        raise ValueError("Invalid regional quality settings")
    if area_policy not in ("strict","corroborated"):
        raise ValueError("Unknown area policy")
    if photometric_threshold is not None and (not np.isfinite(photometric_threshold) or photometric_threshold <= 0):
        raise ValueError("photometric_threshold must be finite and positive")
    t=extraction.time
    if len(t)<2 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
        raise ValueError("Need finite increasing timestamps")
    local={}; shared_events=[]
    for name in REGIONS:
        if name not in extraction.geometry:
            raise ValueError("Regional quality requires geometry")
        g=extraction.geometry[name];rgb=extraction.rgb[name];px=extraction.pixels[name]
        valid=(px>0)&np.isfinite(rgb).all(axis=1)&(rgb>0).all(axis=1)
        motion=g[:,2]>motion_threshold
        pairs=valid[1:]&valid[:-1]&(np.diff(t)<=max_gap)
        delta=np.zeros(len(t)-1)
        np.divide(np.abs(np.diff(px)),px[:-1],out=delta,where=pairs)
        area=np.r_[False,pairs&(delta>area_threshold)]
        if area_policy == "corroborated":
            broad=broad_color_steps(rgb,pairs,.02)
            area &= broad | (g[:,3]>.03)
        photo = np.zeros(len(t), dtype=bool) if photometric_threshold is None else broad_color_steps(rgb,pairs,photometric_threshold)
        local[name]=motion|area|~valid|photo
        shared_events.append(motion|~valid)
    shared=np.sum(shared_events,axis=0)>=2
    def buffered(mask):
        out=mask.copy()
        for at in t[mask]:out|=(t>=at-buffer_seconds)&(t<=at+buffer_seconds)
        return out
    global_bad=buffered(shared)
    masks={n:buffered(raw)|global_bad for n,raw in local.items()}
    return masks,global_bad


def gate_candidates(candidates, zones, usable, *, consensus_policy="patch"):
    if consensus_policy not in ("patch", "zone"):
        raise ValueError("Unknown consensus policy")
    from .zone_consensus import hierarchical_consensus
    filtered={name:value if usable[zones[name]] else None for name,value in candidates.items()}
    choose = hierarchical_consensus if consensus_policy == "zone" else consensus
    return {"individual_candidates":filtered,**choose(filtered,zones)}


def write_regional_comparison(extraction, output, *, area_policy="strict", consensus_policy="patch", max_gap=.25,
                              window_policy="full", continuous_min_seconds=10.):
    """Compare saved pulse candidates on matching continuous fixed windows."""
    from .signal import analyze
    from .patches import PATCHES
    if consensus_policy not in ("patch", "zone"):
        raise ValueError("Unknown consensus policy")
    if window_policy not in ('full', 'continuous'):
        raise ValueError('Unknown window policy')
    if not np.isfinite(continuous_min_seconds) or not 0 < continuous_min_seconds < 12:
        raise ValueError('continuous_min_seconds must be positive and below 12')
    masks,shared=regional_masks(extraction,area_policy=area_policy,max_gap=max_gap)
    global_quality=analyze_segments(extraction,max_gap=max_gap)
    t=extraction.time;rows=[]
    for start in np.arange(t[0],t[-1]-12+float(np.median(np.diff(t)))*1.1+1e-9,6):
        end=start+12;nominal=(t>=start)&(t<end)
        chosen=nominal
        if window_policy == 'continuous':
            from .continuous import select_interval
            indices, _ = select_interval(t,masks,nominal,min_seconds=continuous_min_seconds,max_gap=max_gap)
            chosen=np.zeros(len(t),dtype=bool);chosen[indices]=True
        usable={n:bool(chosen.any()) and not bool(m[chosen].any()) for n,m in masks.items()}
        support_start=float(t[chosen][0]) if chosen.any() else None
        support_end=float(t[chosen][-1]) if chosen.any() else None
        gate_start,gate_end=(start,end) if window_policy == 'full' else (support_start,support_end)
        globally_usable=bool(chosen.any()) and not any(gate_start<i["end_s"] and gate_end>i["start_s"] for i in global_quality["excluded_intervals"])
        row={"start_s":float(start),"end_s":float(end),"usable_regions":usable,
             "sample_loss_regions":sorted(n for n in REGIONS if np.any(
                 (extraction.pixels[n][nominal]<=0) | ~np.isfinite(extraction.rgb[n][nominal]).all(axis=1) |
                 (extraction.rgb[n][nominal]<=0).any(axis=1))),
             "shared_motion_or_loss":bool(shared[nominal].any()),"methods":{}}
        if window_policy == 'continuous':
            row.update(analysis_start_s=support_start,analysis_end_s=support_end,
                       analysis_duration_s=None if support_start is None else support_end-support_start)
        for method in ("pos","green"):
            layouts={}
            for label,traces,zones in (("three_regions",extraction.rgb,{n:n for n in REGIONS}),
                                       ("twelve_patches",extraction.patch_rgb,PATCHES)):
                estimates={}
                for name,rgb in traces.items():
                    samples=rgb[chosen];bpm=None
                    if len(samples) and np.isfinite(samples).all() and np.all(samples>0):
                        try:bpm=analyze(t[chosen],samples,method=method,
                                       min_seconds=11.9 if window_policy=='full' else continuous_min_seconds,max_gap=max_gap).bpm
                        except ValueError:pass
                    estimates[name]=bpm
                policy = consensus_policy if label == "twelve_patches" else "patch"
                layouts[label]={"global_gate":gate_candidates(estimates,zones,{n:globally_usable for n in REGIONS},consensus_policy=policy),
                                "regional_gate":gate_candidates(estimates,zones,usable,consensus_policy=policy)}
            row["methods"][method]=layouts
        rows.append(row)
    report={"policy":"Experimental: region-specific area/displacement/loss; global exclusion when >=2 parent regions are displaced or unavailable",
            "threshold_status":"Unvalidated engineering heuristics",
            "configuration":{"area_policy":area_policy,"consensus_policy":consensus_policy,"max_gap_seconds":max_gap,"motion_threshold":.05,"area_threshold":.10,"buffer_seconds":.5,"window_seconds":12,"step_seconds":6},
            "limitation":"Any excluded frame makes that region unavailable for the complete window; no gap bridging",
            "windows":rows}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if window_policy == 'continuous':
        report['configuration'].update(window_policy=window_policy,continuous_min_seconds=continuous_min_seconds)
        report['limitation']='Analyze only the selected contiguous clean support, never bridge exclusions; nominal window may include unused artifacts'
    filename='regional_comparison.json' if window_policy=='full' else 'continuous_comparison.json'
    (output/filename).write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    return report
