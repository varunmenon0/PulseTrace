"""Conservative motion exclusions and independent segment analysis.

Thresholds are unvalidated engineering heuristics, not heartbeat confidence.
Raw RGB is never modified. Rejected frames are never interpolated or joined.
"""
import json
from pathlib import Path
import numpy as np
from .regions import REGIONS
from .signal import analyze


def analyze_segments(extraction, *, min_seconds=10., buffer_seconds=.5,
                     motion_threshold=.05, area_threshold=.10, max_gap=.25):
    if not np.isfinite([min_seconds,buffer_seconds,motion_threshold,area_threshold,max_gap]).all() or min_seconds<=0 or buffer_seconds<0 or min(motion_threshold,area_threshold,max_gap)<=0:
        raise ValueError('Invalid segment quality settings')
    t=extraction.time
    if len(t)<2 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
        raise ValueError('Need finite increasing timestamps')
    spike=np.zeros(len(t),bool)
    missing=np.zeros(len(t),bool)
    reasons={}
    for name in REGIONS:
        if name not in extraction.geometry:
            raise ValueError('Motion exclusion requires geometry columns; rerun video extraction')
        g=extraction.geometry[name]; pixels=extraction.pixels[name]; rgb=extraction.rgb[name]
        valid=(pixels>0)&np.isfinite(rgb).all(axis=1)&(rgb>0).all(axis=1)
        missing|=~valid
        motion=(g[:,2]>motion_threshold)
        area=np.zeros(len(t),bool)
        pairs=valid[1:]&valid[:-1]&(np.diff(t)<=max_gap)
        change=np.zeros(len(t)-1)
        np.divide(np.abs(np.diff(pixels)),pixels[:-1],out=change,where=pairs)
        area[1:]=pairs&(change>area_threshold)
        spike|=motion|area
        reasons[name]={'motion_spike_frames':int(motion.sum()),'area_spike_frames':int(area.sum())}
    events=spike|missing
    rejected=events.copy()
    for at in t[events]:
        rejected|=(t>=at-buffer_seconds)&(t<=at+buffer_seconds)
    good=np.flatnonzero(~rejected)
    chunks=[] if not len(good) else np.split(good,np.flatnonzero((np.diff(good)>1)|(np.diff(t[good])>max_gap))+1)
    segments=[]
    for c in chunks:
        duration=float(t[c[-1]]-t[c[0]])
        row={'start_s':float(t[c[0]]),'end_s':float(t[c[-1]]),'duration_s':duration,'regions':{},
             'status':'eligible' if duration>=min_seconds else 'too_short'}
        if duration>=min_seconds:
            for name in REGIONS:
                row['regions'][name]={}
                for method in ('pos','green'):
                    try:
                        r=analyze(t[c],extraction.rgb[name][c],method=method,min_seconds=min_seconds,max_gap=max_gap)
                        result={'bpm_candidate':r.bpm,'peak_fraction':r.peak_fraction,'warnings':r.warnings}
                    except ValueError as exc:
                        result={'bpm_candidate':None,'warnings':[str(exc)]}
                    row['regions'][name][method]=result
        segments.append(row)
    # Midpoints describe frame time support, not an exact physiological boundary.
    bounds=np.r_[t[0],(t[:-1]+t[1:])/2,t[-1]]
    bad=np.flatnonzero(rejected)
    bad_chunks=[] if not len(bad) else np.split(bad,np.flatnonzero(np.diff(bad)>1)+1)
    return {'status':'segments_available' if any(s['status']=='eligible' for s in segments) else 'insufficient_usable_footage',
            'configuration':{'min_seconds':min_seconds,'buffer_seconds':buffer_seconds,'motion_threshold':motion_threshold,'area_threshold':area_threshold,'max_gap':max_gap},
            'threshold_status':'unvalidated engineering heuristics',
            'policy':'Any region motion/area spike excludes all regions; missing samples also excluded; no gap bridging',
            'rejected_frame_fraction':float(rejected.mean()),
            'retained_duration_s':float(np.sum(np.diff(bounds)[~rejected])),
            'event_counts':reasons,
            'excluded_intervals':[{'start_s':float(bounds[c[0]]),'end_s':float(bounds[c[-1]+1])} for c in bad_chunks],
            'segments':segments,
            'limitations':['Does not detect all off-face patches, lighting changes or motion artifacts',
                           'No RGB-spike or expected-BPM-based selection; all eligible segments reported',
                           'No clip-level BPM or validated accuracy implied']}


def write_segments(extraction, output, **options):
    report=analyze_segments(extraction,**options)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'segments.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
