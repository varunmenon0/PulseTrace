"""Extract integer/fractional RGB from identical decoded real frames and landmarks."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from benchmark_ubfc import sha256_file
from pulsetrace.pipeline import extract_video
from pulsetrace.tracking import FaceTracker


class RecordTracker:
    def __init__(self,tracker):self.tracker=tracker;self.points=[];self.time=[]
    def detect(self,bgr,time):
        points=self.tracker.detect(bgr,time)
        self.points.append(None if points is None else points.copy());self.time.append(time)
        if len(self.time)%500==0:print('tracked',len(self.time),'frames',flush=True)
        return points


class ReplayTracker:
    def __init__(self,recorded):self.recorded=recorded;self.index=0
    def detect(self,bgr,time):
        if self.index>=len(self.recorded.time) or time!=self.recorded.time[self.index]:
            raise ValueError('Frame timing changed during paired sampling')
        points=self.recorded.points[self.index];self.index+=1
        return None if points is None else points.copy()


def save(extraction,folder,reference,source,model):
    folder.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(folder/'extraction.npz',time=extraction.time,
        **{prefix+n:array for prefix,traces in (('rgb_',extraction.rgb),('pixels_',extraction.pixels),
            ('geometry_',extraction.geometry),('patch_rgb_',extraction.patch_rgb),('patch_pixels_',extraction.patch_pixels))
           for n,array in traces.items()})
    shutil.copyfile(reference,folder/'ground_truth.txt')
    metadata=dict(input=dict(video_sha256=source['files']['vid.avi']['sha256'],
        reference_sha256=sha256_file(reference),model_sha256=sha256_file(model),
        decoded_frames=len(extraction.time),duration_s=float(extraction.time[-1])),sampling=extraction.metadata)
    (folder/'benchmark.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('source','model','output'):p.add_argument('--'+arg,type=Path,required=True)
    args=p.parse_args();source=json.loads((args.source/'source.json').read_text());video=args.source/'vid.avi'
    if sha256_file(video)!=source['files']['vid.avi']['sha256']:raise ValueError('Source video hash mismatch')
    if sha256_file(args.source/'ground_truth.txt')!=source['files']['ground_truth.txt']['sha256']:
        raise ValueError('Reference hash mismatch')
    with FaceTracker(args.model) as tracker:
        recorded=RecordTracker(tracker)
        integer=extract_video(video,recorded,patches=True)
    replay=ReplayTracker(recorded)
    fractional=extract_video(video,replay,patches=True,sampling='fractional')
    if not np.array_equal(integer.time,fractional.time) or replay.index!=len(recorded.time):
        raise ValueError('Paired decoding differs')
    for policy,extraction in (('integer',integer),('fractional',fractional)):
        save(extraction,args.output/policy/source['recording'],args.source/'ground_truth.txt',source,args.model)
    print(source['recording'],'paired extraction complete',len(integer.time),flush=True)


if __name__=='__main__':main()
