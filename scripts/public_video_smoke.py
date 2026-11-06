"""Exploratory raw-video check, not a synchronized reference-error benchmark.

Run from the repository root:
python scripts/public_video_smoke.py --model models/face_landmarker.task
Downloaded data stay in --data-dir and are not included in the source package.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import cv2
import numpy as np
from scipy import signal
from pulsetrace.tracking import FaceTracker
from pulsetrace.pipeline import extract_video, analyze_extraction
from pulsetrace.report import write_report
from pulsetrace.diagnostics import write_diagnostics

BASE = 'https://raw.githubusercontent.com/vladostan/Dataset-for-video-based-pulse-detection/master/data/'
EXPECTED = {'Video/p1_normal.MP4':'9e4e2873c45859b5eb04b9268e8a77c974776c5874b23bd2f5267f30daa259d4', 'ECG/p1_normal.txt':'b7c0c2d0e5fe0e4a2b540eed210cf4e356c5dbcecd210a973a74fbca1f7f2789'}


def rough_reference(path):
    text=path.read_text()
    fs=float(text.split('ADC Sampling rate (Hz):')[1].splitlines()[1])
    if fs!=100:
        raise ValueError('Unexpected reference sampling rate')
    values=np.fromstring(text.split('#II[uV]')[1].split('#')[0],sep=' ')
    filtered=signal.sosfiltfilt(signal.butter(3,[5,20],btype='bandpass',fs=fs,output='sos'),values)
    energy=np.convolve(filtered**2,np.ones(12)/12,mode='same')
    peaks,_=signal.find_peaks(energy,distance=30,prominence=float(energy.max())*.08)
    if len(peaks)<3:
        raise ValueError('Insufficient peaks for exploratory ECG summary')
    return {'method':'unvalidated lead-II QRS-energy peak finder; whole-record median RR',
            'sampling_rate_hz':fs, 'duration_s':float((len(values)-1)/fs),
            'detected_peaks':int(len(peaks)), 'median_rr_bpm':float(60/np.median(np.diff(peaks)/fs))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('outputs/public-data'))
    parser.add_argument('--output',type=Path,default=Path('outputs/public-smoke'))
    args=parser.parse_args()
    args.data_dir.mkdir(parents=True,exist_ok=True)
    for relative,expected in EXPECTED.items():
        dest=args.data_dir/Path(relative).name
        if not dest.exists():
            temporary=dest.with_suffix(dest.suffix+'.partial')
            try:
                with urllib.request.urlopen(BASE+relative,timeout=60) as source,temporary.open('wb') as out:
                    while block:=source.read(1024*1024):out.write(block)
                if hashlib.sha256(temporary.read_bytes()).hexdigest()!=expected:
                    raise ValueError('Upstream public fixture changed; review before use')
                temporary.replace(dest)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=expected:
            raise ValueError('Public fixture checksum mismatch')
    original=args.data_dir/'p1_normal.MP4'; resized=args.data_dir/'p1_normal_640.avi'
    capture=cv2.VideoCapture(str(original)); fps=float(capture.get(cv2.CAP_PROP_FPS))
    writer=cv2.VideoWriter(str(resized),cv2.VideoWriter_fourcc(*'MJPG'),fps,(640,360))
    if not capture.isOpened() or not writer.isOpened():
        capture.release();writer.release();raise ValueError('Public fixture decoder/encoder unavailable')
    try:
        while True:
            ok,frame=capture.read()
            if not ok:break
            writer.write(cv2.resize(frame,(640,360),interpolation=cv2.INTER_AREA))
    finally:
        capture.release();writer.release()
    with FaceTracker(args.model) as tracker:
        extraction=extract_video(resized,tracker)
    results,failures=analyze_extraction(extraction,method='pos')
    extraction.metadata.update({'public_fixture':True, 'source_url':BASE+'Video/p1_normal.MP4',
                                'preprocessing':'resized to 640x360 with INTER_AREA; MJPG at source FPS'})
    summary=write_report(extraction,results,failures,args.output,'pos')
    write_diagnostics(extraction,args.output)
    check={'dataset':BASE,'sha256':EXPECTED,'reference':rough_reference(args.data_dir/'p1_normal.txt'),
           'pos_candidates':{n:r['bpm_candidate'] for n,r in summary['regions'].items()},
           'limitations':['Exact video/ECG time alignment is not documented in inspected README',
                          'No synchronized MAE or RMSE is reported',
                          'ECG peak finder is an exploratory summary, not a validated reference extractor',
                          'One resized clip is not a robustness benchmark']}
    (args.output/'public_check.json').write_text(json.dumps(check,indent=2)+'\n')
    print(json.dumps(check,indent=2))


if __name__=='__main__':main()
