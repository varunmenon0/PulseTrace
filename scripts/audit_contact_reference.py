"""Independent contact-PPG diagnostics; never replace or choose reference labels to fit video."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy import signal


def audit(path):
    a=np.loadtxt(path)
    if a.ndim!=2 or a.shape[0]!=3 or not np.isfinite(a).all() or np.any(np.diff(a[2])<0):
        raise ValueError('Expected finite UBFC2 waveform/BPM/time rows')
    rt,inverse=np.unique(a[2],return_inverse=True)
    if len(rt)<2:raise ValueError('Need multiple reference timestamps')
    waveform=np.bincount(inverse,weights=a[0])/np.bincount(inverse)
    device=np.bincount(inverse,weights=a[1])/np.bincount(inverse)
    rows=[]
    for start in np.arange(0,rt[-1]-12+1e-8,6):
        end=start+12;row={'start_s':float(start),'end_s':float(end)}
        if start < rt[0]:
            row['warning']='Reference does not cover window start';rows.append(row);continue
        left=max(0,np.searchsorted(rt,start,side='right')-1);right=min(len(rt),np.searchsorted(rt,end)+1)
        if np.any(np.diff(rt[left:right])>2.5):
            row['warning']='Reference gap';rows.append(row);continue
        grid=np.arange(start,end,1/30);x=np.interp(grid,rt,waveform)
        bpm=float(np.median(np.interp(grid,rt,device)));row['device_median_bpm']=bpm
        if np.std(x)<1e-8:
            row['warning']='Flat reference waveform';rows.append(row);continue
        x=signal.sosfiltfilt(signal.butter(3,[40/60,200/60],btype='bandpass',fs=30,output='sos'),signal.detrend(x))[30:-30]
        f,p=signal.welch(x,fs=30,nperseg=300,nfft=1200);band=(f>=40/60)&(f<=200/60);f,p=f[band],p[band]
        peak=f[np.argmax(p)]*60;peaks,_=signal.find_peaks(x,distance=9,prominence=.5*np.std(x));rr=np.diff(peaks)/30
        ibi=float(60/np.median(rr)) if len(rr)>=3 else None
        row.update(ppg_spectral_bpm=float(peak),ppg_interbeat_bpm=ibi,
                   spectral_peak_fraction=float(p[np.abs(f*60-peak)<=9].sum()/max(p.sum(),1e-30)),
                   interbeat_cv=float(np.std(rr)/np.mean(rr)) if len(rr) else None,
                   device_ppg_difference_bpm=float(bpm-peak),
                   device_ppg_disagreement_over_10_bpm=bool(abs(bpm-peak)>10),
                   ppg_methods_disagree_over_6_bpm=ibi is None or bool(abs(ibi-peak)>6))
        rows.append(row)
    return {'method':'Contact-only PSD peak and independently detected interbeat intervals',
            'limitations':['Exploratory, not a validated PPG reference extractor','Device BPM may be averaged or misaligned; no cause established',
                           'Video estimates are never used to choose PPG peaks or reference labels'], 'windows':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reference',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    r=audit(args.reference);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
