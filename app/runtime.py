"""Own exactly one local CPU model process. No auto-download at runtime."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIG = json.loads((ROOT/'model_config.json').read_text())


class ModelProcess:
    def __init__(self, port=8091):
        self.port = port
        self.process = None
        self.logs = []
        self.error = None

    def start(self, model):
        executable = 'llama-server.exe' if os.name == 'nt' else 'llama-server'
        matches = list((ROOT/'runtime'/'llama').rglob(executable))
        weights = ROOT/'models'/MODEL_CONFIG['filename']
        if not matches or not weights.exists():
            self.error = 'Local model not installed. Run python scripts/setup.py once while online.'
            return
        with weights.open('rb') as f:
            digest = hashlib.file_digest(f,'sha256').hexdigest()
        if digest != MODEL_CONFIG['sha256']:
            self.error = 'Model SHA256 mismatch. Re-run setup; refusing unknown weights.'
            return
        if model.health():
            self.error = f'Port {self.port} is occupied. Stop the existing model server before launching this app.'
            return
        folder = ROOT/'runtime'
        self.logs = [(folder/'model.stdout.log').open('ab'),(folder/'model.stderr.log').open('ab')]
        args = [str(matches[0]),'-m',str(weights),'--host','127.0.0.1','--port',str(self.port),
                '-c','2048','-np','1','-t','2','-tb','2','-ngl','0','-b','128','-ub','128',
                '--cache-ram','0','--no-context-shift','--no-webui','--threads-http','2']
        try:
            self.process = subprocess.Popen(args, stdout=self.logs[0], stderr=self.logs[1],
                cwd=matches[0].parent, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            for _ in range(180):
                if self.process.poll() is not None:
                    self.error = 'llama.cpp exited during startup; inspect runtime/model.stderr.log'
                    return
                if model.health():
                    return
                time.sleep(0.5)
            self.error = 'Local model did not become ready within 90 seconds'
        except OSError as e:
            self.error = f'Cannot start CPU runtime: {e}'

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in self.logs:
            stream.close()
