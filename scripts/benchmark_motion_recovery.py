"""Measure decoded synthetic motion exclusions and subsequent pulse recovery."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from benchmark_pulse_trends import run


def recovery_metrics(record):
    """Score decisions after estimation; event truth never selects candidates."""
    event = record['fixture'].get('motion', {}).get('event_interval_s')
    result = {}
    for method in ('green', 'pos'):
        rows = record['windows']
        excluded = [r for r in rows if r['shared_motion_or_loss']]
        result[method] = dict(shared_motion_windows=len(excluded),
            shared_motion_windows_with_estimate=sum(r['methods'][method]['bpm_candidate'] is not None for r in excluded))
        if event:
            after = [r for r in rows if r['start_s'] >= event[1] and r['methods'][method]['bpm_candidate'] is not None]
            first = after[0] if after else None
            result[method].update(first_recovered_window_start_s=first['start_s'] if first else None,
                first_recovered_estimate_available_at_s=first['available_at_s'] if first else None,
                availability_delay_after_event_s=first['available_at_s']-event[1] if first else None)
    return result


def plot(result, output):
    fig, axes = plt.subplots(len(result['cases']), 1, figsize=(9, 2.3*len(result['cases'])),
                             constrained_layout=True, squeeze=False)
    axes = axes[:, 0]
    for ax, record in zip(axes, result['cases']):
        ax.axhline(record['case']['start_bpm'], color='.5', linestyle='--', label='Injected rate')
        event = record['fixture'].get('motion', {}).get('event_interval_s')
        if event:
            ax.axvspan(*event, color='#e69536', alpha=.3, label='Rendered motion burst')
        for row in record['windows']:
            if row['shared_motion_or_loss']:
                ax.plot(row['center_s'], record['case']['start_bpm']-2.5, 'x', color='#bd3737', markersize=8)
        for method, color, marker in (('green', '#48a868', 'x'), ('pos', '#377bb5', 'o')):
            ax.plot([r['center_s'] for r in record['windows']],
                [r['methods'][method]['bpm_candidate'] if r['methods'][method]['bpm_candidate'] is not None else np.nan for r in record['windows']],
                marker+'-', color=color, label=method.upper(), fillstyle='none')
        ax.set(title=record['case']['name'].replace('_', ' ').title(), ylabel='BPM',
               ylim=(record['case']['start_bpm']-3, record['case']['end_bpm']+3),
               xlim=(0, record['case']['seconds']))
        ax.grid(alpha=.2)
        ax.legend(loc='upper right', fontsize=8, ncol=3)
    axes[-1].set_xlabel('Window center (seconds); red crosses mark excluded windows')
    fig.suptitle('PulseTrace · controlled motion and recovery')
    for suffix in ('png', 'svg'):
        fig.savefig(output/('summary.'+suffix), dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=Path(__file__).resolve().parents[1]/'examples/motion-recovery/protocol.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.protocol.read_bytes()
    result = run(json.loads(data), args.output)
    result['experiment'] = 'Controlled synthetic translation, burst rejection, and recovery'
    result['protocol_sha256'] = hashlib.sha256(data).hexdigest()
    for record in result['cases']:
        record['recovery'] = recovery_metrics(record)
    (args.output/'benchmark.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    plot(result, args.output)


if __name__ == '__main__':
    main()
