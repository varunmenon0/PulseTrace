"""Render an annotated real-video demo with completed-window pulse results.

Requires FFmpeg on PATH. Raw recordings and detailed measurement reports remain
local; a curated demo may be included in documentation when requested.
Source frames, samples and displayed ROIs share one
recorded landmark pass. Reference data enter only after signal estimation.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np

from benchmark_real_sampling import RecordTracker, save
from benchmark_ubfc import load_reference, sha256_file
from evaluate_real_recovery import reference_window
from pulsetrace.pipeline import extract_video
from pulsetrace.regional_quality import write_regional_comparison
from pulsetrace.signal import analyze
from pulsetrace.tracking import FaceTracker
from pulsetrace.video import VideoReader

from pulsetrace.demo_layout import WIDTH, HEIGHT, active_window, render_frame


def crop_bounds(recorded,shape):
    valid=[p for p in recorded.points if p is not None]
    if not valid:raise ValueError('No tracked face for demonstration')
    points=np.concatenate(valid)
    low=points.min(axis=0);high=points.max(axis=0);center=(low+high)/2
    width=min(shape[1],max((high[0]-low[0])*1.5,(high[1]-low[1])*1.5*4/3))
    height=min(shape[0],width*3/4)
    x=int(np.clip(center[0]-width/2,0,shape[1]-width));y=int(np.clip(center[1]-height/2,0,shape[0]-height))
    return x,y,round(width),round(height)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','model','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--fps',type=int,default=15)
    args=p.parse_args()
    if not 1<=args.fps<=30:raise ValueError('Presentation FPS must be between 1 and 30')
    encoder=shutil.which('ffmpeg')
    if encoder is None:raise ValueError('Install FFmpeg to encode the annotated presentation')
    source=json.loads((args.source/'source.json').read_text());video=args.source/'vid.avi';reference=args.source/'ground_truth.txt'
    if sha256_file(video)!=source['files']['vid.avi']['sha256'] or sha256_file(reference)!=source['files']['ground_truth.txt']['sha256']:
        raise ValueError('Demo inputs do not match source manifest')
    args.output.mkdir(parents=True,exist_ok=True)
    with FaceTracker(args.model) as tracker:
        recorded=RecordTracker(tracker)
        extraction=extract_video(video,recorded,sampling='fractional',patches=True)
    save(extraction,args.output/'extraction',reference,source,args.model)
    regional=write_regional_comparison(extraction,args.output,window_policy='continuous')
    rt,rb=load_reference(reference);windows=[];waves={}
    for w in regional['windows']:
        decision=w['methods']['pos']['twelve_patches']['regional_gate']
        start,end=w['analysis_start_s'],w['analysis_end_s']
        nominal=reference_window(rt,rb,w['start_s'],w['end_s'])
        ref=reference_window(rt,rb,start,end) if nominal is not None else None
        row=dict(start_s=w['start_s'],end_s=w['end_s'],analysis_start_s=start,analysis_end_s=end,
                 bpm_candidate=decision['bpm_candidate'],reference_bpm=ref)
        windows.append(row)
        if decision['bpm_candidate'] is not None:
            patch=decision['support'][0];chosen=(extraction.time>=start)&(extraction.time<=end)
            result=analyze(extraction.time[chosen],extraction.patch_rgb[patch][chosen],min_seconds=10)
            waves[w['start_s']]=(result.time,result.pulse)
    errors=[abs(w['bpm_candidate']-w['reference_bpm']) for w in windows if w['bpm_candidate'] is not None and w['reference_bpm'] is not None]
    if not windows or len(errors)/len(windows)<.8 or np.mean(errors)>5:
        raise ValueError('Selected demo does not meet the fixed coverage/reference-agreement rule')
    result=dict(synthetic=False,source=source,windows=windows,scorable_windows=len(errors),total_windows=len(windows),
        mae_against_device_labels=float(np.mean(errors)),presentation='Offline completed-window estimates; known assumed zero offset',
        output_fps=args.fps,video_sha256=sha256_file(video),reference_sha256=sha256_file(reference))
    (args.output/'private-demo-results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    output=args.output/'PulseTrace-Real-Video-Demo.mp4'
    temporary=args.output/'demo.partial.mp4'
    command=[encoder,'-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s',f'{WIDTH}x{HEIGHT}',
             '-r',str(args.fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    frames=0;next_time=0.;crop=None
    try:
        with VideoReader(video) as reader:
            for frame in reader:
                if frame.index>=len(recorded.time) or frame.time!=recorded.time[frame.index]:
                    raise ValueError('Presentation frame timestamps differ from extraction')
                if frame.time+1e-9<next_time:continue
                if crop is None:crop=crop_bounds(recorded,frame.bgr.shape)
                canvas=render_frame(frame.bgr,recorded.points[frame.index],frame.time,windows,waves,crop,float(extraction.time[-1]))
                process.stdin.write(canvas.tobytes());frames+=1;next_time=frames/args.fps
                if frames==round(args.fps*36):cv2.imwrite(str(args.output/'preview.png'),canvas)
        process.stdin.close()
        if process.wait()!=0:raise ValueError('FFmpeg presentation encoding failed')
        temporary.replace(output)
    finally:
        if process.poll() is None:process.kill();process.wait()
        temporary.unlink(missing_ok=True)
    print(json.dumps(dict(output=str(output),rendered_frames=frames,scorable_windows=len(errors),total_windows=len(windows)),indent=2))


if __name__=='__main__':main()
