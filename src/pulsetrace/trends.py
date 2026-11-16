"""Export rolling pulse trends from existing quality-gated window decisions."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from .patches import PATCHES


def build_trend(report):
    rows, previous = [], -np.inf
    for window in report['windows']:
        start, end = window['start_s'], window['end_s']
        if not np.isfinite([start, end]).all() or end <= start or start <= previous:
            raise ValueError('Need ordered, finite, positive-duration windows')
        previous = start
        row = dict(start_s=start, end_s=end, center_s=(start+end)/2,
                   available_at_s=end, usable_regions=window['usable_regions'],
                   shared_motion_or_loss=window.get('shared_motion_or_loss', False),
                   excluded_regions=sorted(n for n, usable in window['usable_regions'].items() if not usable),
                   sample_loss_regions=window.get('sample_loss_regions', []),
                   methods={})
        if 'analysis_start_s' in window:
            row.update({k:window[k] for k in ('analysis_start_s','analysis_end_s','analysis_duration_s')})
            if window['analysis_start_s'] is not None:
                row['center_s']=(window['analysis_start_s']+window['analysis_end_s'])/2
        for method in ('green', 'pos'):
            detail = window['methods'][method]['twelve_patches']['regional_gate']
            row['methods'][method] = dict(bpm_candidate=detail['bpm_candidate'], support=detail['support'],
                unavailable_reason=None if detail['bpm_candidate'] is not None else
                    ('quality_exclusion' if sum(row['usable_regions'].values()) < 2 else 'insufficient_pulse_support'),
                supporting_zones=detail.get('supporting_zones', sorted({PATCHES[n] for n in detail['support']})))
        rows.append(row)
    metrics = {m: dict(total_windows=len(rows),
                      estimated_windows=sum(r['methods'][m]['bpm_candidate'] is not None for r in rows))
               for m in ('green', 'pos')}
    return dict(configuration=report['configuration'], timing='Offline estimates at analyzed-support centers; available after nominal window end',
                policy='Regional quality gate; missing estimates stay missing', metrics=metrics, windows=rows)


def write_trend(report, output):
    result = build_trend(report)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'pulse_trend.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with (output/'pulse_trend.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['start_s','end_s','center_s','available_at_s','green_bpm','pos_bpm',
                         'shared_motion_or_loss','excluded_regions','sample_loss_regions',
                         'green_unavailable_reason','pos_unavailable_reason',
                         'analysis_start_s','analysis_end_s','analysis_duration_s'])
        for row in result['windows']:
            writer.writerow([row[k] for k in ('start_s','end_s','center_s','available_at_s')]+
                            [row['methods'][m]['bpm_candidate'] for m in ('green','pos')]+
                            [row['shared_motion_or_loss'], ';'.join(row['excluded_regions']),
                             ';'.join(row['sample_loss_regions'])]+
                            [row['methods'][m]['unavailable_reason'] for m in ('green','pos')]+
                            [row.get(k) for k in ('analysis_start_s','analysis_end_s','analysis_duration_s')])
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    for method, color in (('green','#48a868'), ('pos','#377bb5')):
        centers = [r['center_s'] for r in result['windows']]
        values = [np.nan if r['methods'][method]['bpm_candidate'] is None else r['methods'][method]['bpm_candidate'] for r in result['windows']]
        ax.plot(centers,values,'o-',color=color,label=method.upper(),markersize=4)
    ax.set(xlabel='Window center (seconds)',ylabel='Estimated BPM',title='PulseTrace · windowed pulse trend')
    ax.legend()
    ax.grid(alpha=.2)
    fig.savefig(output/'pulse_trend.png',dpi=160)
    plt.close(fig)
    return result
