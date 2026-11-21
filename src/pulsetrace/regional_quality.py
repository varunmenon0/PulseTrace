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
                   photometric_threshold=None, return_details=False):
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
    local={}; shared_events=[]; details={}
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
        if return_details:
            details[name] = dict(motion=motion, area_change=area, missing_samples=~valid,
                                 photometric_step=photo, displacement=g[:,2],
                                 area_change_fraction=np.r_[np.nan, np.where(pairs, delta, np.nan)])
    shared=np.sum(shared_events,axis=0)>=2
    def buffered(mask):
        out=mask.copy()
        for at in t[mask]:out|=(t>=at-buffer_seconds)&(t<=at+buffer_seconds)
        return out
    global_bad=buffered(shared)
    masks={n:buffered(raw)|global_bad for n,raw in local.items()}
    if return_details:
        causes = {name: {cause: buffered(d[cause]) for cause in
                        ('motion', 'area_change', 'missing_samples', 'photometric_step')}
                  for name, d in details.items()}
        return masks, global_bad, dict(raw=details, buffered=causes, shared_raw=shared,
            thresholds=dict(motion_face_units=motion_threshold, area_step_fraction=area_threshold,
                            buffer_seconds=buffer_seconds, max_gap_seconds=max_gap,
                            area_policy=area_policy, photometric_threshold=photometric_threshold))
    return masks,global_bad


def gate_candidates(candidates, zones, usable, *, consensus_policy="patch"):
    if consensus_policy not in ("patch", "zone"):
        raise ValueError("Unknown consensus policy")
    from .zone_consensus import hierarchical_consensus
    filtered={name:value if usable[zones[name]] else None for name,value in candidates.items()}
    choose = hierarchical_consensus if consensus_policy == "zone" else consensus
    return {"individual_candidates":filtered,**choose(filtered,zones)}


def build_regional_comparison(extraction, *, area_policy="strict", consensus_policy="patch", max_gap=.25,
                              window_policy="full", continuous_min_seconds=10., window_starts=None,
                              include_diagnostics=False):
    """Compare saved pulse candidates on matching continuous fixed windows."""
    from .signal import analyze
    from .patches import PATCHES
    if consensus_policy not in ("patch", "zone"):
        raise ValueError("Unknown consensus policy")
    if window_policy not in ('full', 'continuous'):
        raise ValueError('Unknown window policy')
    if not np.isfinite(continuous_min_seconds) or not 0 < continuous_min_seconds < 12:
        raise ValueError('continuous_min_seconds must be positive and below 12')
    mask_result=regional_masks(extraction,area_policy=area_policy,max_gap=max_gap,
                               return_details=include_diagnostics)
    masks,shared=mask_result[:2]
    global_quality=analyze_segments(extraction,max_gap=max_gap)
    t=extraction.time;rows=[]
    starts = np.arange(t[0],t[-1]-12+float(np.median(np.diff(t)))*1.1+1e-9,6) if window_starts is None else window_starts
    for start in starts:
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
        if include_diagnostics:
            from .stream_diagnostics import window_quality
            row['quality'] = window_quality(extraction, nominal, masks, shared, mask_result[2],
                                           min_seconds=continuous_min_seconds, max_gap=max_gap)
            row['quality'].update(window_policy=window_policy,
                                  usable_regions_on_selected_support=usable.copy(),
                                  selected_support_start_s=support_start, selected_support_end_s=support_end)
        for method in ("pos","green"):
            layouts={}
            for label,traces,zones in (("three_regions",extraction.rgb,{n:n for n in REGIONS}),
                                       ("twelve_patches",extraction.patch_rgb,PATCHES)):
                estimates={}; patch_details={}
                for name,rgb in traces.items():
                    samples=rgb[chosen];bpm=None
                    detail = dict(signal_status='no_selected_support' if not len(samples) else 'missing_samples',
                                  candidate_bpm=None, warnings=[])
                    if len(samples) and np.isfinite(samples).all() and np.all(samples>0):
                        try:
                            result=analyze(t[chosen],samples,method=method,
                                min_seconds=11.9 if window_policy=='full' else continuous_min_seconds,max_gap=max_gap)
                            bpm=result.bpm
                            if include_diagnostics and label == 'twelve_patches':
                                from .patch_diagnostics import signal_detail
                                detail=signal_detail(result)
                        except ValueError as exc:
                            detail.update(signal_status='analysis_error', warnings=[str(exc)])
                    estimates[name]=bpm
                    if include_diagnostics and label == 'twelve_patches':
                        detail.update(parent_region=zones[name], region_usable=usable[zones[name]],
                                      eligible_bpm=bpm if usable[zones[name]] else None,
                                      selected_samples=len(samples),
                                      valid_sample_fraction=float(np.mean(np.isfinite(samples).all(axis=1) &
                                                                         (samples>0).all(axis=1))) if len(samples) else None)
                        patch_details[name]=detail
                policy = consensus_policy if label == "twelve_patches" else "patch"
                layouts[label]={"global_gate":gate_candidates(estimates,zones,{n:globally_usable for n in REGIONS},consensus_policy=policy),
                                "regional_gate":gate_candidates(estimates,zones,usable,consensus_policy=policy)}
                if include_diagnostics and label == 'twelve_patches':
                    from .patch_diagnostics import consensus_detail
                    row['quality'].setdefault('pulse_methods', {})[method] = dict(patches=patch_details,
                        consensus=consensus_detail(layouts[label]['regional_gate'], zones, usable, policy))
            row["methods"][method]=layouts
        rows.append(row)
    report={"policy":"Experimental: region-specific area/displacement/loss; global exclusion when >=2 parent regions are displaced or unavailable",
            "threshold_status":"Unvalidated engineering heuristics",
            "configuration":{"area_policy":area_policy,"consensus_policy":consensus_policy,"max_gap_seconds":max_gap,"motion_threshold":.05,"area_threshold":.10,"buffer_seconds":.5,"window_seconds":12,"step_seconds":6},
            "limitation":"Any excluded frame makes that region unavailable for the complete window; no gap bridging",
            "windows":rows}
    if window_policy == 'continuous':
        report['configuration'].update(window_policy=window_policy,continuous_min_seconds=continuous_min_seconds)
        report['limitation']='Analyze only the selected contiguous clean support, never bridge exclusions; nominal window may include unused artifacts'
    return report


def write_regional_comparison(extraction, output, **options):
    report = build_regional_comparison(extraction, **options)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    filename = 'continuous_comparison.json' if options.get('window_policy') == 'continuous' else 'regional_comparison.json'
    (output/filename).write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return report
