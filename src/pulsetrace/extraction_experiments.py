"""Fixed research variants. No live defaults, votes or spectral gates change.

chrom_window uses the CHROM color axes with a single coefficient estimated from
the full completed window. It is not the original overlapping-window algorithm.
pos_bandlimited keeps POS overlap/normalization but uses band-limited color
axes to estimate alpha. Both retain PulseTrace's 40–200 BPM final band.
"""
import numpy as np
from scipy import signal

from .signal import analyze

METHODS = ('green','pos','chrom_window','pos_bandlimited')


def _filtered(rgb, fs):
    sos = signal.butter(4,[40/60,200/60],fs=fs,btype='bandpass',output='sos')
    return signal.sosfiltfilt(sos,rgb,axis=0)


def chrom_window(rgb, fs):
    normalized = rgb/rgb.mean(axis=0)-1
    x = 3*normalized[:,0]-2*normalized[:,1]
    y = 1.5*normalized[:,0]+normalized[:,1]-1.5*normalized[:,2]
    band = _filtered(np.column_stack([x,y]),fs)
    alpha = np.std(band[:,0])/max(np.std(band[:,1]),1e-12)
    return x-alpha*y


def pos_bandlimited(rgb, fs):
    filtered = _filtered(rgb,fs)
    length = max(3,int(round(1.6*fs)))
    if len(rgb)<length:
        raise ValueError('Too few samples for POS window')
    output,weights = np.zeros(len(rgb)),np.zeros(len(rgb))
    for start in range(len(rgb)-length+1):
        chunk=rgb[start:start+length]
        mean=chunk.mean(axis=0)
        normalized=chunk/mean-1
        band=filtered[start:start+length]/mean
        x=normalized[:,1]-normalized[:,2]
        y=normalized[:,1]+normalized[:,2]-2*normalized[:,0]
        bx=band[:,1]-band[:,2]
        by=band[:,1]+band[:,2]-2*band[:,0]
        alpha=np.std(bx)/max(np.std(by),1e-12)
        source=x+alpha*y
        output[start:start+length]+=source-source.mean()
        weights[start:start+length]+=1
    return output/np.maximum(weights,1)


def analyze_variant(time, rgb, method, *, min_seconds=10., max_gap=.25):
    if method not in METHODS:
        raise ValueError('Unknown extraction experiment')
    options=dict(min_seconds=min_seconds,max_gap=max_gap)
    if method in ('pos','green'):
        return analyze(time,rgb,method=method,**options)
    source=chrom_window if method=='chrom_window' else pos_bandlimited
    return analyze(time,rgb,_source=source,**options)
