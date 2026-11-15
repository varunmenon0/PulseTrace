"""Replay fixed zone-voting rules against checksummed, saved patch candidates."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from pulsetrace.patches import PATCHES, consensus
from pulsetrace.zone_consensus import hierarchical_consensus


CONFIGURATION = dict(tolerance_bpm=5, minimum_patch_support_per_zone=2,
                     minimum_zone_support=2,
                     cluster_rule='Unique largest strict-majority cluster at each level')


def _same(a, b):
    return a is None and b is None or (a is not None and b is not None and
                                       math.isclose(a, b, rel_tol=0, abs_tol=1e-8))


def replay_report(report, report_format):
    rows = []
    for window in report['windows']:
        for method in ('pos', 'green'):
            if report_format == 'regional':
                policies = window['methods'][method]['twelve_patches']
            elif report_format == 'sources':
                policies = {name: detail['methods'][method]['twelve_patches']
                            for name, detail in window['sources'].items()}
            else:
                raise ValueError('Unknown report format')
            for policy, detail in policies.items():
                candidates = detail['individual_candidates']
                legacy = consensus(candidates, PATCHES)
                if not _same(legacy['bpm_candidate'], detail['bpm_candidate']):
                    raise ValueError('Saved legacy consensus does not reproduce')
                new = hierarchical_consensus(candidates, PATCHES)
                reference = window['reference_bpm']
                error = lambda bpm: None if bpm is None or reference is None else bpm-reference
                rows.append(dict(start_s=window['start_s'], end_s=window['end_s'], method=method,
                    policy=policy, reference_bpm=reference, reference_warning=window.get('reference_warning'),
                    legacy=legacy, zone=new, legacy_error_bpm=error(legacy['bpm_candidate']),
                    zone_error_bpm=error(new['bpm_candidate'])))
    return rows


def summarize(rows):
    result = {}
    for method, policy in sorted({(r['method'], r['policy']) for r in rows}):
        chosen = [r for r in rows if r['method'] == method and r['policy'] == policy]
        metrics = dict(total_windows=len(chosen),
                       reference_valid_windows=sum(r['reference_bpm'] is not None for r in chosen))
        for name in ('legacy', 'zone'):
            errors = [abs(r[name+'_error_bpm']) for r in chosen if r[name+'_error_bpm'] is not None]
            metrics[name] = dict(candidate_windows=sum(r[name]['bpm_candidate'] is not None for r in chosen),
                scorable_windows=len(errors),
                mae_against_device_bpm=float(np.mean(errors)) if errors else None,
                max_difference_bpm=float(max(errors)) if errors else None)
        common = [r for r in chosen if r['legacy_error_bpm'] is not None and r['zone_error_bpm'] is not None]
        added = [abs(r['zone_error_bpm']) for r in chosen if r['legacy_error_bpm'] is None and r['zone_error_bpm'] is not None]
        lost = [abs(r['legacy_error_bpm']) for r in chosen if r['zone_error_bpm'] is None and r['legacy_error_bpm'] is not None]
        metrics['paired'] = dict(common_windows=len(common),
            legacy_common_mae=float(np.mean([abs(r['legacy_error_bpm']) for r in common])) if common else None,
            zone_common_mae=float(np.mean([abs(r['zone_error_bpm']) for r in common])) if common else None,
            changed_common_bpm=sum(not _same(r['legacy']['bpm_candidate'], r['zone']['bpm_candidate']) for r in common),
            newly_scorable_windows=len(added), lost_windows=len(lost),
            newly_scorable_mae=float(np.mean(added)) if added else None,
            newly_scorable_max_difference=float(max(added)) if added else None,
            lost_window_device_difference_mean=float(np.mean(lost)) if lost else None)
        metrics['zone_rejections'] = {reason: sum(r['zone']['rejection_reason'] == reason for r in chosen)
                                     for reason in ('insufficient_zone_support', 'zone_disagreement')}
        result[f'{method}/{policy}'] = metrics
    return result


def replay_protocol(protocol, root):
    if protocol['configuration'] != CONFIGURATION:
        raise ValueError('Protocol does not match the implemented fixed rules')
    groups = []
    for group in protocol['groups']:
        records, combined, seen = [], [], set()
        for entry in group['reports']:
            path = (root / entry['path']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Source reports must be inside the repository')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Source report checksum mismatch')
            report = json.loads(data)
            identity = report['input']['video_sha256']
            if identity in seen:
                raise ValueError('Duplicate recording in a replay group')
            seen.add(identity)
            rows = replay_report(report, group['format'])
            records.append(dict(source_report=entry['path'], source_sha256=entry['sha256'],
                                video_sha256=identity, metrics=summarize(rows), windows=rows))
            combined.extend(rows)
        groups.append(dict(name=group['name'], metrics=summarize(combined), recordings=records))
    return dict(configuration=CONFIGURATION, groups=groups,
                experiment='Candidate-only development replay; source frames, spectra, and exclusions unchanged',
                reference='Original stored device BPM, with original invalid windows preserved',
                notes=['Every legacy candidate result reproduced before comparison',
                       'Sampling and gating groups are summarized separately',
                       'Previously used subjects, not a new held-out cohort',
                       'Zone voting does not independently verify a pulse or reject common lighting artifacts'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--protocol', type=Path, default=root/'examples/zone-consensus/protocol.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.protocol.read_bytes()
    result = replay_protocol(json.loads(data), root)
    result['protocol_sha256'] = hashlib.sha256(data).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
