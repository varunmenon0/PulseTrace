"""Score pulse recovery after synthetic face loss, including an unrecovered tail."""
import argparse
import hashlib
import json
from pathlib import Path

from benchmark_motion_recovery import plot, recovery_metrics
from benchmark_pulse_trends import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=Path(__file__).resolve().parents[1]/'examples/tracking-loss/protocol.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.protocol.read_bytes()
    result = run(json.loads(data), args.output)
    result['experiment'] = 'Controlled synthetic face loss and windowed pulse recovery'
    result['protocol_sha256'] = hashlib.sha256(data).hexdigest()
    for record in result['cases']:
        record['recovery'] = recovery_metrics(record)
    (args.output/'benchmark.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    plot(result, args.output, title='PulseTrace · face loss and pulse recovery')


if __name__ == '__main__':
    main()
