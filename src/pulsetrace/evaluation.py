"""Compare diagnostic windows with synchronized reference BPM, no extrapolation."""
import json
from pathlib import Path
import numpy as np
from .diagnostics import inspect_extraction


def evaluate_reference(extraction, reference_time, reference_bpm, *, reference_offset,
                       max_reference_gap=2.5, **diagnostic_options):
    """reference_time = video_time + reference_offset; offset must be supplied."""
    rt,rb=np.asarray(reference_time,float),np.asarray(reference_bpm,float)
    if rt.ndim!=1 or rb.shape!=rt.shape or len(rt)<2:
        raise ValueError('Reference requires matching time and BPM vectors with >=2 samples')
    if not np.isfinite(rt).all() or not np.isfinite(rb).all() or np.any(np.diff(rt)<=0) or np.any(rb<=0):
        raise ValueError('Reference timestamps must increase and BPM must be finite and positive')
    if not np.isfinite([reference_offset,max_reference_gap]).all() or max_reference_gap<=0:
        raise ValueError('Offset must be finite and reference gap positive')
    diagnostics,_=inspect_extraction(extraction,**diagnostic_options)
    output={'reference_offset_s':float(reference_offset),
            'offset_convention':'reference_time = video_time + reference_offset',
            'reference_method':'median interpolated reference BPM over each analyzed segment',
            'limitations':['Overlapping windows are not independent observations',
                           'MAE/RMSE include accepted candidates only; always inspect coverage',
                           'Diagnostic flags are retained and do not silently exclude estimates'],
            'regions':{}}
    for name,region in diagnostics['regions'].items():
        output['regions'][name]={}
        for method,detail in region['methods'].items():
            rows=[]; errors=[]; eligible=0
            for w in detail['windows']:
                row=dict(w); row.update(reference_bpm=None,error_bpm=None,reference_warning=None)
                start=w['segment_start_s'] if w['segment_start_s'] is not None else w['start_s']
                end=w['segment_end_s'] if w['segment_end_s'] is not None else w['end_s']
                a,b=start+reference_offset,end+reference_offset
                if a<rt[0] or b>rt[-1]:
                    row['reference_warning']='Reference does not cover the complete segment'
                else:
                    left=max(0,np.searchsorted(rt,a,side='right')-1)
                    right=min(len(rt),np.searchsorted(rt,b,side='left')+1)
                    if np.any(np.diff(rt[left:right])>max_reference_gap):
                        row['reference_warning']='Reference contains an excessive gap'
                    else:
                        eligible+=1
                        grid=np.linspace(a,b,max(2,int((b-a)*30)+1))
                        reference=float(np.median(np.interp(grid,rt,rb)))
                        row['reference_bpm']=reference
                        if w['bpm_candidate'] is not None:
                            row['error_bpm']=w['bpm_candidate']-reference
                            errors.append(row['error_bpm'])
                rows.append(row)
            output['regions'][name][method]={
                'total_windows':len(rows),'reference_covered_windows':eligible,'compared_windows':len(errors),
                'candidate_coverage':len(errors)/eligible if eligible else 0.,
                'mae_bpm':float(np.mean(np.abs(errors))) if errors else None,
                'rmse_bpm':float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
                'windows':rows}
    return output


def evaluate_csv(extraction, reference_path, output, **options):
    d=np.genfromtxt(reference_path,delimiter=',',names=True,ndmin=1)
    if not d.dtype.names or not {'time_s','bpm'}.issubset(d.dtype.names):
        raise ValueError('Reference CSV must contain time_s,bpm columns')
    result=evaluate_reference(extraction,d['time_s'],d['bpm'],**options)
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    (output/'evaluation.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result
