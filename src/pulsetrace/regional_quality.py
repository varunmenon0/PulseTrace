"""Experimental local quality exclusions; original global gate stays the default."""
import json
from pathlib import Path

import numpy as np

from .regions import REGIONS
from .patches import PATCHES, consensus
from .quality import analyze_segments


def regional_masks(extraction, *, motion_threshold=.05, area_threshold=.10,
                   buffer_seconds=.5, max_gap=.25, area_policy="strict"):
    """Exclude a region locally; two displaced/unavailable parents exclude all."""
    if not np.isfinite([motion_threshold,area_threshold,buffer_seconds,max_gap]).all() or min(motion_threshold,area_threshold,max_gap)<=0 or buffer_seconds<0:
        raise ValueError("Invalid regional quality settings")
    if area_policy not in ("strict","corroborated"):
        raise ValueError("Unknown area policy")
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
            color=np.zeros_like(rgb[1:],dtype=float)
            np.divide(np.diff(rgb,axis=0),rgb[:-1],out=color,where=np.broadcast_to(pairs[:,None],color.shape))
            broad=np.r_[False,(np.sum(color>.02,axis=1)>=2)|(np.sum(color<-.02,axis=1)>=2)]
            area &= broad | (g[:,3]>.03)
        local[name]=motion|area|~valid
        shared_events.append(motion|~valid)
    shared=np.sum(shared_events,axis=0)>=2
    def buffered(mask):
        out=mask.copy()
        for at in t[mask]:out|=(t>=at-buffer_seconds)&(t<=at+buffer_seconds)
        return out
    global_bad=buffered(shared)
    masks={n:buffered(raw)|global_bad for n,raw in local.items()}
    return masks,global_bad


def gate_candidates(candidates, zones, usable):
    filtered={name:value if usable[zones[name]] else None for name,value in candidates.items()}
    return {"individual_candidates":filtered,**consensus(filtered,zones)}


def write_regional_comparison(extraction, output, *, area_policy="strict"):
    """Compare saved pulse candidates on matching continuous fixed windows."""
    from .signal import analyze
    from .patches import PATCHES
    masks,shared=regional_masks(extraction,area_policy=area_policy)
    global_quality=analyze_segments(extraction)
    t=extraction.time;rows=[]
    for start in np.arange(t[0],t[-1]-12+float(np.median(np.diff(t)))*1.1+1e-9,6):
        end=start+12;chosen=(t>=start)&(t<end)
        usable={n:not bool(m[chosen].any()) for n,m in masks.items()}
        globally_usable=not any(start<i["end_s"] and end>i["start_s"] for i in global_quality["excluded_intervals"])
        row={"start_s":float(start),"end_s":float(end),"usable_regions":usable,
             "shared_motion_or_loss":bool(shared[chosen].any()),"methods":{}}
        for method in ("pos","green"):
            layouts={}
            for label,traces,zones in (("three_regions",extraction.rgb,{n:n for n in REGIONS}),
                                       ("twelve_patches",extraction.patch_rgb,PATCHES)):
                estimates={}
                for name,rgb in traces.items():
                    samples=rgb[chosen];bpm=None
                    if np.isfinite(samples).all() and np.all(samples>0):
                        try:bpm=analyze(t[chosen],samples,method=method,min_seconds=11.9).bpm
                        except ValueError:pass
                    estimates[name]=bpm
                layouts[label]={"global_gate":gate_candidates(estimates,zones,{n:globally_usable for n in REGIONS}),
                                "regional_gate":gate_candidates(estimates,zones,usable)}
            row["methods"][method]=layouts
        rows.append(row)
    report={"policy":"Experimental: region-specific area/displacement/loss; global exclusion when >=2 parent regions are displaced or unavailable",
            "threshold_status":"Unvalidated engineering heuristics",
            "configuration":{"area_policy":area_policy,"motion_threshold":.05,"area_threshold":.10,"buffer_seconds":.5,"window_seconds":12,"step_seconds":6},
            "limitation":"Any excluded frame makes that region unavailable for the complete window; no gap bridging",
            "windows":rows}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/"regional_comparison.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    return report
