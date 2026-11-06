"""Download the versioned official model atomically; verify its SHA256."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('models/face_landmarker.task'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.task.partial')
    try:
        with urllib.request.urlopen(URL, timeout=60) as response, temporary.open('wb') as file:
            while block := response.read(1024 * 1024):
                file.write(block)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if digest != EXPECTED_SHA256:
            raise ValueError(f'Model SHA256 mismatch: {digest}')
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'{args.output} SHA256={digest}')


EXPECTED_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
if __name__ == '__main__':
    main()
