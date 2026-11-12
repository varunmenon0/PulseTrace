"""Download one mirrored UBFC-rPPG recording (1.43 GB); verify recorded hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('outputs/ubfc-subject1'))
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((Path(__file__).parents[1]/'examples/ubfc-subject1/source.json').read_text())
    for name,meta in manifest['files'].items():
        target=args.output/name
        temp=target.with_suffix(target.suffix+'.part')
        h=hashlib.sha256()
        with urllib.request.urlopen(meta['url'],timeout=60) as response, temp.open('wb') as file:
            while chunk:=response.read(4*1024*1024):
                file.write(chunk);h.update(chunk)
        if h.hexdigest()!=meta['sha256'] or temp.stat().st_size!=meta['bytes']:
            temp.unlink(missing_ok=True)
            raise ValueError('Downloaded data do not match source manifest: '+name)
        temp.replace(target)
        print(target,flush=True)


if __name__=='__main__':main()
