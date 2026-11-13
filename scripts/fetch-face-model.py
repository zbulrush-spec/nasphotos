"""Download buffalo_l at image build time, then verify and install all five files."""
import hashlib
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

URL='https://github.com/kqstone/mt-photos-insightface-unofficial/releases/download/models/buffalo_l.zip'
# Filled from the upstream release archive and checked on every build.
SHA256='80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f'
FILES={'1k3d68.onnx','2d106det.onnx','det_10g.onnx','genderage.onnx','w600k_r50.onnx'}

def install(destination,archive=None):
    with tempfile.TemporaryDirectory() as temp:
        source=Path(archive) if archive else Path(temp)/'buffalo_l.zip'
        if not archive:
            last=None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(URL,timeout=120) as response,source.open('wb') as output:shutil.copyfileobj(response,output)
                    last=None;break
                except Exception as error:last=error
            if last:raise last
        with source.open('rb') as input: digest=hashlib.file_digest(input,'sha256').hexdigest()
        if digest!=SHA256:raise RuntimeError(f'buffalo_l checksum mismatch: {digest}')
        destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(source) as archive:
            members={Path(n).name:n for n in archive.namelist() if Path(n).name in FILES}
            if set(members)!=FILES:raise RuntimeError('Incomplete buffalo_l model archive')
            for name,member in members.items():
                with archive.open(member) as input,(destination/name).open('wb') as output:shutil.copyfileobj(input,output)
        print('Verified and installed buffalo_l:',digest)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('destination');parser.add_argument('--archive');args=parser.parse_args()
    install(args.destination,args.archive)
