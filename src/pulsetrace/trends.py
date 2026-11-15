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
                   available_at_s=end, usable_regions=window['usable_regions'], methods={})
        for method in ('green', 'pos'):
            detail = window['methods'][method]['twelve_patches']['regional_gate']
            row['methods'][method] = dict(bpm_candidate=detail['bpm_candidate'], support=detail['support'],
                supporting_zones=detail.get('supporting_zones', sorted({PATCHES[n] for n in detail['support']})))
        rows.append(row)
    metrics = {m: dict(total_windows=len(rows),
                      estimated_windows=sum(r['methods'][m]['bpm_candidate'] is not None for r in rows))
               for m in ('green', 'pos')}
    return dict(configuration=report['configuration'], timing='Offline window averages, plotted at window centers; available after window end',
                policy='Regional quality gate; missing estimates stay missing', metrics=metrics, windows=rows)


def write_trend(report, output):
    result = build_trend(report)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'pulse_trend.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with (output/'pulse_trend.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['start_s','end_s','center_s','available_at_s','green_bpm','pos_bpm'])
        for row in result['windows']:
            writer.writerow([row[k] for k in ('start_s','end_s','center_s','available_at_s')]+
                            [row['methods'][m]['bpm_candidate'] for m in ('green','pos')])
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
