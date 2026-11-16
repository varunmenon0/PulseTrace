"""Render a private annotated real-video demo with completed-window pulse results.

Requires FFmpeg on PATH. The video and individual pulse measurements are outputs,
never repository assets. Source frames, samples and displayed ROIs share one
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
from pulsetrace.regions import REGIONS
from pulsetrace.signal import analyze
from pulsetrace.subpixel import fractional_masks
from pulsetrace.tracking import FaceTracker
from pulsetrace.video import VideoReader

WIDTH,HEIGHT=1280,720
BG=(23,20,16);PANEL=(43,36,29);TEXT=(238,235,228);MUTED=(171,163,151)
PULSE=(210,214,89);REFERENCE=(79,171,245)


def active_window(windows,time):
    """A rejected latest window must clear the previous successful BPM."""
    complete=[w for w in windows if w['end_s']<=time+1e-9]
    return complete[-1] if complete else None


def put(image,text,xy,scale=.55,color=TEXT,thickness=1):
    cv2.putText(image,str(text),xy,cv2.FONT_HERSHEY_SIMPLEX,scale,color,thickness,cv2.LINE_AA)


def chart(image,x,y,w,h,times,values,bounds,color):
    """Draw finite consecutive values only; missing estimates break the line."""
    lo,hi,low,high=bounds
    previous=None
    for t,v in zip(times,values):
        if v is None or not np.isfinite(v):previous=None;continue
        point=(round(x+(t-lo)/max(hi-lo,1e-9)*w),round(y+h-(np.clip(v,low,high)-low)/max(high-low,1e-9)*h))
        if previous is not None:cv2.line(image,previous,point,color,2,cv2.LINE_AA)
        previous=point


def crop_bounds(recorded,shape):
    valid=[p for p in recorded.points if p is not None]
    if not valid:raise ValueError('No tracked face for demonstration')
    points=np.concatenate(valid)
    low=points.min(axis=0);high=points.max(axis=0);center=(low+high)/2
    width=min(shape[1],max((high[0]-low[0])*1.5,(high[1]-low[1])*1.5*4/3))
    height=min(shape[0],width*3/4)
    x=int(np.clip(center[0]-width/2,0,shape[1]-width));y=int(np.clip(center[1]-height/2,0,shape[0]-height))
    return x,y,round(width),round(height)


def render_frame(bgr,points,time,windows,waves,crop,duration):
    image=np.full((HEIGHT,WIDTH,3),BG,np.uint8)
    put(image,'PulseTrace',(20,40),1.05,TEXT,2)
    put(image,'Heartbeat estimation from real public webcam video',(260,39),.62,MUTED)
    put(image,'12 facial patches | fractional sampling | POS',(20,78),.58,PULSE)
    face=bgr.copy()
    if points is not None:
        for zone,indices in REGIONS.items():
            try:_,patches=fractional_masks(face.shape,points[list(indices)],partition='equal_area')
            except ValueError:continue
            for mask in patches.values():
                if mask.area<30:continue
                contours,_=cv2.findContours((mask.weights>0).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                contours=[c+np.array([[[mask.x,mask.y]]]) for c in contours]
                cv2.drawContours(face,contours,-1,PULSE,1,cv2.LINE_AA)
    x,y,w,h=crop
    image[95:545,20:620]=cv2.resize(face[y:y+h,x:x+w],(600,450))
    put(image,f'Decoded video time: {time:05.2f}s',(35,530),.55,(255,255,255),2)
    row=active_window(windows,time)
    bpm=None if row is None else row['bpm_candidate'];ref=None if row is None else row['reference_bpm']
    for x,title,value,color in ((650,'PulseTrace POS',bpm,PULSE),(965,'Device reference',ref,REFERENCE)):
        cv2.rectangle(image,(x,95),(x+295,235),PANEL,-1)
        put(image,title,(x+18,123),.65,MUTED)
        put(image,'--' if value is None else f'{value:.1f}',(x+18,186),1.8,color,2)
        put(image,'BPM - completed window',(x+18,217),.5,MUTED)
    if row is None:
        label='Collecting the first 12-second window'
    elif row['analysis_start_s'] is None:
        label='No sufficiently long clean section - estimate unavailable'
    else:
        label=f"Analyzed {row['analysis_start_s']:.2f}-{row['analysis_end_s']:.2f}s | available at {row['end_s']:.0f}s"
    put(image,label,(650,265),.48,MUTED)
    cv2.rectangle(image,(650,285),(1260,545),PANEL,-1)
    put(image,'Extracted POS waveform - supported facial patch',(668,311),.52,TEXT)
    if row is not None and row['start_s'] in waves:
        t,pulse=waves[row['start_s']]
        normalized=(pulse-pulse.mean())/max(pulse.std(),1e-12)
        for yy in (350,405,460,515):cv2.line(image,(675,yy),(1235,yy),(65,57,47),1)
        chart(image,675,345,560,170,t,normalized,(t[0],t[-1],-3,3),PULSE)
        put(image,f'{t[0]:.1f}s',(675,537),.42,MUTED);put(image,f'{t[-1]:.1f}s',(1190,537),.42,MUTED)
    else:put(image,'Waveform appears after an accepted window',(680,410),.55,MUTED)
    cv2.rectangle(image,(20,565),(1260,690),PANEL,-1)
    put(image,'Completed-window pulse trend',(35,589),.55,TEXT)
    complete=[w for w in windows if w['end_s']<=time+1e-9]
    centers=[(w['analysis_start_s']+w['analysis_end_s'])/2 if w['analysis_start_s'] is not None else (w['start_s']+w['end_s'])/2 for w in complete]
    values=[w['bpm_candidate'] for w in windows]+[w['reference_bpm'] for w in windows]
    values=[v for v in values if v is not None]
    low,high=(min(values)-5,max(values)+5) if values else (40,200)
    for key,color in (('bpm_candidate',PULSE),('reference_bpm',REFERENCE)):
        chart(image,45,606,1170,65,centers,[w[key] for w in complete],(0,duration,low,high),color)
    put(image,'0s',(40,683),.38,MUTED);put(image,f'{duration:.0f}s',(1195,683),.38,MUTED)
    put(image,'POS estimate',(20,710),.44,PULSE);put(image,'Device reference',(150,710),.44,REFERENCE)
    put(image,'Offline analysis | Original reference labels, assumed zero clock offset',(390,710),.44,MUTED)
    return image


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
