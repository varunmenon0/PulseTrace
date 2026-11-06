"""Observational diagnostics. Flags are heuristics, never authenticity verdicts."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .regions import REGIONS
from .pipeline import Extraction
from .signal import analyze

GEOMETRY_COLUMNS = ('center_x_px', 'center_y_px', 'displacement_face_units',
                    'shape_change_face_units', 'face_scale_px')
DEFAULT_THRESHOLDS = {'area_step_fraction': .10, 'rgb_step_fraction': .02,
                      'motion_face_units': .05, 'shape_face_units': .03,
                      'band_edge_margin_bpm': 6.0}


def load_rgb_csv(path):
    """Read old or new rgb.csv without loading MediaPipe or accessing a video."""
    data = np.genfromtxt(path, delimiter=',', names=True, ndmin=1)
    required = ['time_s'] + [f'{n}_{c}' for n in REGIONS for c in ('r','g','b','pixels')]
    if not data.dtype.names or not set(required).issubset(data.dtype.names):
        raise ValueError('RGB CSV is missing required time/channel/pixel columns')
    time = np.asarray(data['time_s'], float)
    if len(time) < 2 or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError('RGB CSV needs at least two strictly increasing finite timestamps')
    rgb = {n: np.column_stack([data[f'{n}_{c}'] for c in 'rgb']) for n in REGIONS}
    pixels = {n: np.asarray(data[f'{n}_pixels'], float) for n in REGIONS}
    for n in REGIONS:
        if not np.isfinite(pixels[n]).all() or np.any(pixels[n] < 0):
            raise ValueError('Pixel counts must be finite and nonnegative')
    geometry = {}
    for n in REGIONS:
        keys = [f'{n}_{c}' for c in GEOMETRY_COLUMNS]
        if set(keys).issubset(data.dtype.names):
            geometry[n] = np.column_stack([data[k] for k in keys])
    return Extraction(time, rgb, pixels, None, {}, {'source': 'RGB CSV'}, geometry)


def geometry_sample(landmarks, indices, previous, scale):
    """Track region translation and shape separately, normalized by face scale."""
    points = np.asarray(landmarks)[list(indices)]
    center = points.mean(axis=0)
    translation = shape = np.nan
    if previous is not None and scale > 0:
        old_center = previous.mean(axis=0)
        translation = np.linalg.norm(center-old_center)/scale
        shape = np.sqrt(np.mean(np.sum(((points-center)-(previous-old_center))**2, axis=1)))/scale
    return np.array([*center, translation, shape, scale])


def window_estimates(time, rgb, *, method, window_seconds=12., step_seconds=6., max_gap=.25):
    if not np.isfinite([window_seconds, step_seconds]).all() or window_seconds < 10 or step_seconds <= 0:
        raise ValueError('Window must be >=10 seconds and step must be positive')
    rows = []
    # End-exclusive windows cover a full requested interval up to one frame tolerance.
    tolerance = float(np.median(np.diff(time))) * 1.1
    for start in np.arange(time[0], time[-1]-window_seconds+tolerance+1e-9, step_seconds):
        end = start+window_seconds
        chosen = (time >= start) & (time < end)
        row = {'start_s': float(start), 'end_s': float(end), 'center_s': float(start+window_seconds/2),
               'bpm_candidate': None, 'unvalidated_peak_bpm': None, 'peak_fraction': None,
               'segment_start_s': None, 'segment_end_s': None, 'warnings': []}
        try:
            result = analyze(time[chosen], rgb[chosen], method=method,
                             min_seconds=window_seconds-tolerance, max_gap=max_gap)
        except ValueError as exc:
            row['warnings'] = [str(exc)]
        else:
            band = (result.frequencies >= 40/60) & (result.frequencies <= 200/60)
            power = result.power[band]
            peak = None if power.sum() < 1e-16 else float(result.frequencies[band][np.argmax(power)]*60)
            row.update(bpm_candidate=result.bpm, unvalidated_peak_bpm=peak,
                       peak_fraction=result.peak_fraction, segment_start_s=float(result.time[0]),
                       segment_end_s=float(result.time[-1]), warnings=result.warnings)
        rows.append(row)
    return rows


def inspect_extraction(extraction, *, window_seconds=12., step_seconds=6., max_gap=.25):
    t = extraction.time
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Diagnostics require finite increasing timestamps')
    output = {'thresholds': DEFAULT_THRESHOLDS, 'threshold_status': 'unvalidated engineering heuristics',
              'regions': {}, 'limitations': [
                  'Patch geometry and RGB changes cannot establish artifact cause',
                  'Motion metrics unavailable for legacy CSVs without geometry columns',
                  'Spectral peaks and accepted candidates are not validated heartbeats']}
    traces = {}
    for name in REGIONS:
        rgb, pixels = extraction.rgb[name], extraction.pixels[name]
        valid = np.isfinite(rgb).all(axis=1) & (rgb > 0).all(axis=1) & (pixels > 0)
        pairs = valid[1:] & valid[:-1] & (np.diff(t) <= max_gap)
        area = np.full(len(t), np.nan)
        brightness = np.full(len(t), np.nan)
        relative_rgb = np.full_like(rgb, np.nan, dtype=float)
        if valid.any():
            relative_rgb[valid] = rgb[valid]/rgb[valid].mean(axis=0)-1
        # Steps are fractional changes relative to the previous observation.
        area[1:][pairs] = np.abs(np.diff(pixels)[pairs])/pixels[:-1][pairs]
        change = np.full((len(t)-1,3),np.nan)
        change[pairs] = np.diff(rgb,axis=0)[pairs]/rgb[:-1][pairs]
        brightness[1:][pairs] = np.max(np.abs(change[pairs]),axis=1)
        broad = np.zeros(len(t),bool)
        broad[1:] = ((np.sum(change > DEFAULT_THRESHOLDS['rgb_step_fraction'],axis=1) >= 2) |
                     (np.sum(change < -DEFAULT_THRESHOLDS['rgb_step_fraction'],axis=1) >= 2)) & pairs
        area_flags = area > DEFAULT_THRESHOLDS['area_step_fraction']
        geometry = extraction.geometry.get(name)
        motion_flags = np.zeros(len(t),bool)
        if geometry is not None:
            motion_flags = ((geometry[:,2] > DEFAULT_THRESHOLDS['motion_face_units']) |
                            (geometry[:,3] > DEFAULT_THRESHOLDS['shape_face_units'])) & valid
        events = [{'time_s':float(t[i]), 'area_step_fraction':float(area[i]) if np.isfinite(area[i]) else None,
                   'max_rgb_step_fraction':float(brightness[i]) if np.isfinite(brightness[i]) else None,
                   'flags':[label for condition,label in [(area_flags[i],'area_jump'),(broad[i],'broad_rgb_jump'),
                                                         (motion_flags[i],'landmark_motion')] if condition]}
                  for i in np.flatnonzero(area_flags | broad | motion_flags)]
        pos_pixels = pixels[valid]
        result = {'valid_frame_fraction':float(np.mean(valid)),
                  'pixel_count_range': [float(pos_pixels.min()),float(pos_pixels.max())] if len(pos_pixels) else None,
                  'max_area_step_fraction':float(np.nanmax(area)) if pairs.any() else None,
                  'max_rgb_step_fraction':float(np.nanmax(brightness)) if pairs.any() else None,
                  'motion_available':geometry is not None, 'events':events, 'methods':{}}
        for method in ('green','pos'):
            windows = window_estimates(t,rgb,method=method,window_seconds=window_seconds,
                                       step_seconds=step_seconds,max_gap=max_gap)
            for row in windows:
                interval = (t >= row['start_s']) & (t < row['end_s'])
                row['artifact_event_count'] = sum(interval[np.flatnonzero(area_flags | broad | motion_flags)])
                # Python int needed for strict JSON.
                row['artifact_event_count'] = int(row['artifact_event_count'])
                peak = row['unvalidated_peak_bpm']
                row['near_band_edge'] = peak is not None and min(peak-40,200-peak) <= 6
            accepted = [r['bpm_candidate'] for r in windows if r['bpm_candidate'] is not None]
            result['methods'][method] = {'windows':windows, 'accepted_window_fraction':
                len(accepted)/len(windows) if windows else 0.,
                'accepted_bpm_range': [min(accepted),max(accepted)] if accepted else None}
        output['regions'][name] = result
        traces[name] = (relative_rgb, area, brightness, geometry)
    return output, traces


def write_diagnostics(extraction, output, **options):
    output = Path(output); output.mkdir(parents=True,exist_ok=True)
    report, traces = inspect_extraction(extraction, **options)
    (output/'diagnostics.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    rows = []
    for name, region in report['regions'].items():
        for method, results in region['methods'].items():
            rows.extend({'region':name,'method':method,**r} for r in results['windows'])
    fields = ('region','method','start_s','end_s','center_s','bpm_candidate','unvalidated_peak_bpm',
              'peak_fraction','segment_start_s','segment_end_s','artifact_event_count','near_band_edge')
    with (output/'windows.csv').open('w',newline='') as file:
        writer = csv.DictWriter(file,fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    fig, axes = plt.subplots(3,3,figsize=(15,10),constrained_layout=True)
    for i,name in enumerate(REGIONS):
        relative,area,brightness,geometry = traces[name]
        for j,c in enumerate('RGB'):
            axes[i,0].plot(extraction.time,100*relative[:,j],label=c,linewidth=.8)
        axes[i,0].set_title(name+' normalized RGB'); axes[i,0].set_ylabel('Change from mean (%)'); axes[i,0].legend()
        axes[i,1].plot(extraction.time,extraction.pixels[name],label='Patch pixels')
        axes[i,1].set_title('Patch area; red = diagnostic event'); axes[i,1].set_ylabel('Pixels')
        for event in report['regions'][name]['events']:
            axes[i,1].axvline(event['time_s'],color='red',alpha=.15)
        for method,results in report['regions'][name]['methods'].items():
            w=results['windows']; x=[r['center_s'] for r in w]
            axes[i,2].plot(x,[r['unvalidated_peak_bpm'] if r['unvalidated_peak_bpm'] is not None else np.nan for r in w],
                           '--',label=method+' spectral peak',alpha=.6)
            axes[i,2].scatter(x,[r['bpm_candidate'] if r['bpm_candidate'] is not None else np.nan for r in w],label=method+' candidate')
        axes[i,2].set_ylim(30,210); axes[i,2].set_title(f'{options.get("window_seconds",12):g} s windows: unvalidated peaks'); axes[i,2].set_ylabel('BPM'); axes[i,2].legend(fontsize=8)
        for ax in axes[i]: ax.set_xlabel('Time (s)')
    fig.savefig(output/'diagnostics.png',dpi=140); plt.close(fig)
    if extraction.geometry:
        fig,axes=plt.subplots(3,1,figsize=(10,8),constrained_layout=True)
        for ax,name in zip(axes,REGIONS):
            g=extraction.geometry.get(name)
            if g is not None:
                ax.plot(extraction.time,g[:,2],label='Center displacement / face scale')
                ax.plot(extraction.time,g[:,3],label='Shape change / face scale')
            ax.set_title(name); ax.set_xlabel('Time (s)'); ax.legend()
        fig.savefig(output/'tracking.png',dpi=140); plt.close(fig)
    else:
        (output/'tracking.png').unlink(missing_ok=True)
    return report
