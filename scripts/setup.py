"""One-time, hash-verified CPU runtime and model download. No runtime network."""
from pathlib import Path
import hashlib
import json
import os
import platform
import time
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'b12182'
CONFIG = json.loads((ROOT / 'model_config.json').read_text())
REVISION = CONFIG['revision']
MODEL_NAME = CONFIG['filename']
MODEL_SHA = CONFIG['sha256']
RUNTIMES = {
    'Windows': ('win-cpu-x64.zip', 'e068c483e2ea97bf09121ec0bbe085bd43470bb67d9062c7c66162164aea5834'),
    'Linux': ('ubuntu-x64.tar.gz', 'c1dbfdb9cbef7ee50b6ab08142d6424184d68b242906837770439ed118c57d99'),
}


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def download(url, target, expected, size=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(target) == expected:
        print(f'Verified {target.name}', flush=True)
        return
    partial = target.with_suffix(target.suffix + '.part')
    print(f'Downloading {target.name}', flush=True)
    if size:
        # Bounded ranged requests avoid long, silent CDN transfers. Each retry
        # rewrites only its own range; the final complete file is hash verified.
        chunk_size = 16 * 1024 * 1024
        with partial.open('wb') as out:
            for offset in range(0,size,chunk_size):
                end = min(size,offset+chunk_size)-1
                for attempt in range(3):
                    try:
                        request = urllib.request.Request(url+f'?download=true&chunk={offset}',
                                                         headers={'Range':f'bytes={offset}-{end}'})
                        with urllib.request.urlopen(request,timeout=60) as response:
                            if response.status!=206 or response.headers.get('Content-Range','').split('/')[0] != f'bytes {offset}-{end}':
                                raise RuntimeError('CDN did not return the requested byte range')
                            out.seek(offset)
                            remaining = end-offset+1
                            while remaining:
                                block = response.read(min(1024*1024,remaining))
                                if not block:
                                    raise RuntimeError('Incomplete model download range')
                                out.write(block)
                                remaining -= len(block)
                        break
                    except Exception:
                        if attempt==2:
                            raise
                        time.sleep(attempt+1)
                if offset % (64*1024*1024)==0:
                    print(f'Model download: {min(size,end+1)//(1024*1024)} / {size//(1024*1024)} MiB',flush=True)
    else:
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as out:
            while block := response.read(1024 * 1024):
                out.write(block)
    actual = sha256(partial)
    if actual != expected:
        raise RuntimeError(f'SHA256 mismatch for {target.name}: {actual}')
    os.replace(partial, target)
    print(f'Verified {target.name}: {expected}', flush=True)


def main():
    system = platform.system()
    if platform.machine().lower() not in ('amd64', 'x86_64') or system not in RUNTIMES:
        raise SystemExit('Pinned binaries support Windows/Linux x64. See README for other platforms.')
    suffix, expected = RUNTIMES[system]
    archive = ROOT / 'runtime' / f'llama-{TAG}-bin-{suffix}'
    download(f'https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{archive.name}', archive, expected)
    destination = ROOT / 'runtime' / 'llama'
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / 'runtime' / 'manifest.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    executable = 'llama-server.exe' if system == 'Windows' else 'llama-server'
    installed = previous.get('runtime_sha256') == expected and any(destination.rglob(executable))
    if installed:
        print('Pinned CPU runtime already installed', flush=True)
    elif system == 'Windows':
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if not (destination / member.filename).resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError('Unsafe archive path')
            z.extractall(destination)
    else:
        with tarfile.open(archive) as t:
            t.extractall(destination, filter='data')
    model = ROOT / 'models' / MODEL_NAME
    download(f"https://huggingface.co/{CONFIG['repository']}/resolve/{REVISION}/{MODEL_NAME}", model, MODEL_SHA,CONFIG.get('size_bytes'))
    manifest = {'runtime': TAG, 'runtime_sha256': expected, 'model': MODEL_NAME,
                'model_revision': REVISION, 'model_sha256': MODEL_SHA, 'platform': system}
    (ROOT / 'runtime' / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Ready. Run: python scripts/run.py', flush=True)


if __name__ == '__main__':
    main()
