"""Launch one backend worker; its lifespan owns one CPU model process."""
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn

if __name__ == '__main__':
    uvicorn.run('app.main:app',host=os.environ.get('ANALYZER_HOST','127.0.0.1'),port=8000,
                workers=1,limit_concurrency=16,timeout_keep_alive=5,log_level='info',access_log=False)
