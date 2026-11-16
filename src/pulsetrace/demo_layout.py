"""A restrained, light presentation for recorded-video pulse analysis.

This module only draws previously computed results. It never changes pulse
estimates, references, selected support, or availability times.
"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .regions import REGIONS
from .subpixel import fractional_masks

WIDTH,HEIGHT=1440,900
BACKGROUND='#FBFBFD'
INK='#1D1D1F'
SECONDARY='#6E6E73'
RULE='#E5E5EA'
ACCENT='#D92D3A'
REFERENCE='#86868B'


@lru_cache(maxsize=32)
def font(size,bold=False):
    """Use installed native sans-serif fonts; do not redistribute Apple fonts."""
    candidates=(
        '/System/Library/Fonts/SFNS.ttf',
        '/usr/share/fonts/opentype/urw-base35/NimbusSans-'+('Bold' if bold else 'Regular')+'.otf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-'+('Bold' if bold else 'Regular')+'.ttf',
        'C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),
    )
    for path in candidates:
        if Path(path).is_file():return ImageFont.truetype(path,size)
    from matplotlib import get_data_path
    path=Path(get_data_path())/'fonts/ttf'/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
    return ImageFont.truetype(str(path),size)


def text(draw,label,xy,size=18,fill=INK,bold=False,right=False):
    f=font(size,bold)
    x,y=xy
    if right:x-=draw.textlength(str(label),font=f)
    draw.text((x,y),str(label),font=f,fill=fill,anchor='lt')


def active_window(windows,time):
    complete=[w for w in windows if w['end_s']<=time+1e-9]
    return complete[-1] if complete else None


def clock(seconds):
    seconds=max(0,int(seconds))
    return f'{seconds//60:02d}:{seconds%60:02d}'


def line_chart(image,box,times,values,bounds,color,width=2,markers=False,dashed=False):
    """Preserve gaps and reveal only values supplied by the caller."""
    x,y,w,h=box;lo,hi,low,high=bounds
    layer=Image.new('RGBA',(round(w+8)*2,round(h+8)*2),(0,0,0,0));draw=ImageDraw.Draw(layer)
    previous=None
    for t,value in zip(times,values):
        if value is None or not np.isfinite(value):previous=None;continue
        point=(8+(t-lo)/max(hi-lo,1e-9)*w*2,8+h*2-(np.clip(value,low,high)-low)/max(high-low,1e-9)*h*2)
        if previous is not None:
            if dashed:
                distance=float(np.linalg.norm(np.subtract(point,previous)))
                for start in np.arange(0,distance,24):
                    a=start/max(distance,1e-9);b=min(start+12,distance)/max(distance,1e-9)
                    draw.line([tuple(np.array(previous)*(1-a)+np.array(point)*a),
                               tuple(np.array(previous)*(1-b)+np.array(point)*b)],fill=color,width=width*2)
            else:draw.line([previous,point],fill=color,width=width*2)
        if markers:
            px,py=point;draw.ellipse((px-6,py-6,px+6,py+6),fill=color)
        previous=point
    layer=layer.resize((round(w+8),round(h+8)),Image.Resampling.LANCZOS)
    image.paste(layer,(round(x-4),round(y-4)),layer)


def render_frame(bgr,points,time,windows,waves,crop,duration):
    canvas=Image.new('RGB',(WIDTH,HEIGHT),BACKGROUND);draw=ImageDraw.Draw(canvas)
    text(draw,'PulseTrace',(56,42),30,bold=True)
    text(draw,'Heart rate from video',(56,84),17,SECONDARY)
    draw.rounded_rectangle((1220,46,1384,80),radius=17,fill='#F0F0F3')
    text(draw,'Recorded session',(1237,55),15,SECONDARY)
    draw.line((56,121,1384,121),fill=RULE,width=1)

    face=bgr.copy()
    if points is not None:
        for indices in REGIONS.values():
            try:_,patches=fractional_masks(face.shape,points[list(indices)],partition='equal_area')
            except ValueError:continue
            for mask in patches.values():
                if mask.area<30:continue
                contours,_=cv2.findContours((mask.weights>0).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                contours=[c+np.array([[[mask.x,mask.y]]]) for c in contours]
                cv2.drawContours(face,contours,-1,(58,45,217),1,cv2.LINE_AA)
    x,y,w,h=crop
    video=Image.fromarray(cv2.cvtColor(face[y:y+h,x:x+w],cv2.COLOR_BGR2RGB)).resize((640,480),Image.Resampling.LANCZOS)
    mask=Image.new('L',video.size,0);ImageDraw.Draw(mask).rounded_rectangle((0,0,639,479),radius=18,fill=255)
    canvas.paste(video,(56,150),mask)
    draw.rounded_rectangle((76,582,232,614),radius=9,fill='#FFFFFF')
    text(draw,f'{clock(time)} / {clock(duration)}',(89,592),14,INK)
    text(draw,'12 facial patches',(56,650),15,SECONDARY)
    text(draw,'Public webcam recording',(696,650),15,SECONDARY,right=True)

    row=active_window(windows,time)
    bpm=None if row is None else row['bpm_candidate'];reference=None if row is None else row['reference_bpm']
    text(draw,'Heart rate',(760,155),22,SECONDARY)
    number='—' if bpm is None else f'{bpm:.1f}'
    text(draw,number,(752,192),112)
    number_width=draw.textlength(number,font=font(112))
    if bpm is not None:text(draw,'BPM',(min(752+number_width+16,1308),250),25,SECONDARY)
    text(draw,'Sensor reference',(760,331),18,SECONDARY)
    text(draw,'—' if reference is None else f'{reference:.1f} BPM',(1384,331),18,right=True)
    if row is None:label='Measuring the first 12 seconds…'
    elif row['analysis_start_s'] is None:label='Waiting for a clean section'
    elif bpm is None:label='No estimate for this window'
    else:label=f"Completed window  {clock(round(row['analysis_start_s']))}–{clock(round(row['analysis_end_s']))}"
    text(draw,label,(760,369),16,SECONDARY)

    text(draw,'Pulse waveform',(760,419),20,bold=True)
    if row is not None and row['start_s'] in waves:
        t,pulse=waves[row['start_s']];normalized=(pulse-pulse.mean())/max(pulse.std(),1e-12)
        for yy in (463,524,585):draw.line((760,yy,1384,yy),fill=RULE,width=1)
        line_chart(canvas,(760,463,624,122),t,normalized,(t[0],t[-1],-3,3),ACCENT,2)
        text(draw,clock(t[0]),(760,604),14,SECONDARY)
        text(draw,clock(round(t[-1])),(1384,604),14,SECONDARY,right=True)
    else:
        draw.line((760,524,1384,524),fill=RULE,width=1)
        text(draw,'Appears after the first completed window',(760,555),16,SECONDARY)

    draw.line((56,692,1384,692),fill=RULE,width=1)
    text(draw,'Heart rate over time',(56,720),22,bold=True)
    draw.line((1074,730,1098,730),fill=ACCENT,width=3)
    text(draw,'PulseTrace',(1107,721),15,SECONDARY)
    draw.line((1225,730,1232,730),fill=REFERENCE,width=2);draw.line((1238,730,1246,730),fill=REFERENCE,width=2)
    text(draw,'Reference',(1255,721),15,SECONDARY)
    complete=[w for w in windows if w['end_s']<=time+1e-9]
    centers=[(w['analysis_start_s']+w['analysis_end_s'])/2 if w['analysis_start_s'] is not None else (w['start_s']+w['end_s'])/2 for w in complete]
    values=[w[k] for w in windows for k in ('bpm_candidate','reference_bpm') if w[k] is not None]
    low,high=(np.floor((min(values)-5)/5)*5,np.ceil((max(values)+5)/5)*5) if values else (40,200)
    for value in (low,high):
        yy=837-(value-low)/max(high-low,1)*70
        draw.line((95,yy,1384,yy),fill=RULE,width=1)
        text(draw,f'{value:.0f}',(80,yy-7),13,SECONDARY,right=True)
    for key,color,dashed in (('reference_bpm',REFERENCE,True),('bpm_candidate',ACCENT,False)):
        line_chart(canvas,(95,767,1289,70),centers,[w[key] for w in complete],(0,duration,low,high),color,2,True,dashed)
    for at in np.arange(0,duration+1,15):
        xx=95+at/max(duration,1)*1289;text(draw,clock(at),(xx,851),13,SECONDARY)
    text(draw,'12-second analysis windows',(56,882),12,SECONDARY)
    text(draw,'Recorded video · original sensor labels',(1384,882),12,SECONDARY,right=True)
    return cv2.cvtColor(np.asarray(canvas),cv2.COLOR_RGB2BGR)
