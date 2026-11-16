"""Download one mirrored UBFC-rPPG recording (1.43 GB); verify recorded hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def matches(path,meta):
    if not path.is_file() or path.stat().st_size!=meta['bytes']:return False
    h=hashlib.sha256()
    with path.open('rb') as file:
        while chunk:=file.read(4*1024*1024):h.update(chunk)
    return h.hexdigest()==meta['sha256']


def fetch_manifest(manifest,output):
    """Keep acquisition identity beside verified files; reuse complete downloads."""
    output.mkdir(parents=True,exist_ok=True)
    for name,meta in manifest['files'].items():
        if Path(name).name!=name or name in ('.','..','source.json'):
            raise ValueError('Expected a simple recording filename')
        target=output/name
        if matches(target,meta):
            print(target,'already verified',flush=True);continue
        temp=target.with_suffix(target.suffix+'.part')
        try:
            with urllib.request.urlopen(meta['url'],timeout=60) as response,temp.open('wb') as file:
                while chunk:=response.read(4*1024*1024):file.write(chunk)
            if not matches(temp,meta):raise ValueError('Downloaded data do not match source manifest: '+name)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        print(target,flush=True)
    (output/'source.json').write_text(json.dumps(manifest,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('outputs/ubfc-subject1'))
    p.add_argument('--manifest',type=Path,default=Path(__file__).parents[1]/'examples/ubfc-subject1/source.json')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(args.manifest.read_text())
    fetch_manifest(manifest,args.output)


if __name__=='__main__':main()
