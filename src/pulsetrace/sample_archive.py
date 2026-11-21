"""Incremental local archives of sampled colors/geometry, never camera images."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from .patches import PATCHES
from .regions import REGIONS
from .sampling import Sample


def encode_number(value):
    value = float(value)
    if np.isnan(value):
        return None
    if np.isposinf(value):
        return 'Infinity'
    if np.isneginf(value):
        return '-Infinity'
    return value


def decode_number(value):
    if value is None:
        return np.nan
    if value in ('Infinity', '-Infinity'):
        return float(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError('Invalid archived numeric value')
    return float(value)


def sample_record(sample):
    result = dict(type='sample', time_s=encode_number(sample.time), reset_reason=sample.reset_reason)
    for field in ('rgb', 'geometry', 'patch_rgb'):
        result[field] = {n:[encode_number(v) for v in values] for n,values in getattr(sample, field).items()}
    for field in ('pixels', 'patch_pixels'):
        result[field] = {n:encode_number(v) for n,v in getattr(sample, field).items()}
    return result


def record_sample(record):
    if not isinstance(record, dict) or record.get('type') != 'sample':
        raise ValueError('Expected an archived sample')
    t = decode_number(record.get('time_s'))
    if not np.isfinite(t):
        raise ValueError('Archived timestamp must be finite')
    fields = {}
    for field, names, width in (('rgb', REGIONS, 3), ('geometry', REGIONS, 5), ('patch_rgb', PATCHES, 3),
                                ('pixels', REGIONS, None), ('patch_pixels', PATCHES, None)):
        raw = record.get(field)
        if not isinstance(raw, dict) or set(raw) != set(names):
            raise ValueError('Missing or unknown archived '+field+' regions')
        fields[field] = {}
        for name,value in raw.items():
            if width is not None:
                if not isinstance(value, list) or len(value) != width:
                    raise ValueError('Invalid archived '+field+' shape')
                fields[field][name] = np.array([decode_number(v) for v in value])
            else:
                number = decode_number(value)
                if not np.isfinite(number) or number < 0:
                    raise ValueError('Invalid archived sampled area')
                fields[field][name] = number
    reason = record.get('reset_reason')
    if reason is not None and not isinstance(reason, str):
        raise ValueError('Invalid archived reset reason')
    return Sample(t, **fields, reset_reason=reason)


def provenance():
    root = Path(__file__).parent
    return dict(versions={n:importlib.metadata.version(n) for n in ('pulsetrace','numpy','scipy','opencv-contrib-python')},
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                       ('signal.py','regional_quality.py','streaming.py','sampling.py','agreement.py',
                        'capture.py','tracking.py')})


class SampleWriter:
    def __init__(self, path, metadata):
        self.path, self.metadata, self.count = Path(path), metadata, 0

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('w')
        try:
            header = dict(type='sample_session', schema_version=1, metadata=self.metadata,
                provenance=provenance(), frames_saved=False,
                values='RGB means, sampled areas and geometry only; null=NaN; Infinity strings preserve infinities',
                scope='Samples consumed by the engine; camera queue drops are represented by timestamp gaps')
            self.file.write(json.dumps(header, allow_nan=False)+'\n')
            self.file.flush()
        except Exception:
            self.file.close()
            raise
        return self

    def write(self, sample):
        self.file.write(json.dumps(sample_record(sample), allow_nan=False)+'\n')
        self.file.flush()
        self.count += 1

    def __exit__(self, *args):
        self.file.close()


class SampleReader:
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.file = self.path.open()
        try:
            self.header = json.loads(self.file.readline())
            if (not isinstance(self.header, dict) or self.header.get('type') != 'sample_session'
                    or self.header.get('schema_version') != 1 or not isinstance(self.header.get('metadata'), dict)):
                raise ValueError('Unsupported sample archive header')
        except Exception:
            self.file.close()
            raise
        return self

    def __iter__(self):
        for line_number,line in enumerate(self.file, 2):
            try:
                yield record_sample(json.loads(line))
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f'Invalid sample archive at line {line_number}: {exc}') from exc

    def __exit__(self, *args):
        self.file.close()
