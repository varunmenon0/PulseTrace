import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import download_ubfc_sample as acquisition


def manifest(data):
    return dict(recording='fixture',files={'vid.avi':dict(url='https://example.invalid/video',bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest())})


def test_acquisition_preserves_source_manifest_and_reuses_verified_bytes(tmp_path,monkeypatch):
    data=b'fixture';source=manifest(data);calls=[]
    def get(*args,**kwargs):calls.append(args);return io.BytesIO(data)
    monkeypatch.setattr(acquisition.urllib.request,'urlopen',get)
    acquisition.fetch_manifest(source,tmp_path)
    acquisition.fetch_manifest(source,tmp_path)
    assert len(calls)==1
    assert json.loads((tmp_path/'source.json').read_text())==source


def test_failed_verification_preserves_existing_file_and_removes_partial(tmp_path,monkeypatch):
    (tmp_path/'vid.avi').write_bytes(b'original')
    monkeypatch.setattr(acquisition.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'wrong'))
    with pytest.raises(ValueError):acquisition.fetch_manifest(manifest(b'expected'),tmp_path)
    assert (tmp_path/'vid.avi').read_bytes()==b'original'
    assert not (tmp_path/'vid.avi.part').exists()
    assert not (tmp_path/'source.json').exists()
