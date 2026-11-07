from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import json
import logging
import os
import threading
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from .ingest import Upload, UploadError, MAX_BYTES
from .model import LocalModel
from .prompts import CONTEXT_SIZE, OUTPUT_TOKENS, SAFETY_TOKENS, PROMPT_VERSION
from .runtime import ModelProcess, MODEL_CONFIG
from .store import Store
from .worker import Worker, memory_usage

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)


def create_app(store=None, model=None, background=True):
    store = store or Store(Path(os.environ.get('ANALYZER_DATA_DIR',str(ROOT/'data')))/'state.sqlite3')
    model = model or LocalModel()
    worker = Worker(store,model)
    runtime = ModelProcess() if background else None
    thread = None
    upload_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        nonlocal thread
        if runtime:
            await asyncio.to_thread(runtime.start,model)
            if not runtime.error:
                thread = threading.Thread(target=worker.loop,name='single-analysis-worker',daemon=True)
                thread.start()
        yield
        worker.stop.set()
        worker.wake.set()
        if thread:
            # Close the owned model first to release an in-flight HTTP request.
            runtime.close()
            await asyncio.to_thread(thread.join,10)
        elif runtime:
            runtime.close()
        if hasattr(model,'close'):
            model.close()

    app = FastAPI(title='Tracewatch · Local log analyzer',lifespan=lifespan,
                  docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store,app.state.worker = store,worker
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

    @app.middleware('http')
    async def protection(request,call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS') and origin:
            if urlparse(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail':'Cross-origin writes are blocked'},status_code=403)
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    def get_job(job_id):
        job = store.job(job_id)
        if not job:
            raise HTTPException(404,'Analysis not found')
        return job

    def public_call(call):
        return {k:v for k,v in call.items() if k not in ('payload','raw_reply','observations','rejected')}

    @app.get('/api/status')
    def status():
        return {'model_ready':not (runtime and runtime.error) and model.health(),
                'model':MODEL_CONFIG['name']+' · '+MODEL_CONFIG['quantization'],'model_config':MODEL_CONFIG,
                'runtime':'llama.cpp b12182 · CPU',
                'model_error':runtime.error if runtime else None,'rss_bytes':memory_usage(),
                'ram_limit_bytes':4*1024**3,'context_tokens':CONTEXT_SIZE,
                'output_reserve':OUTPUT_TOKENS,'safety_tokens':SAFETY_TOKENS,'active_job':worker.active}

    @app.get('/api/jobs')
    def jobs():
        return store.jobs()

    @app.post('/api/jobs',status_code=201)
    async def upload(request:Request, filename:str):
        length = request.headers.get('content-length','0')
        if not length.isdigit() or int(length) > MAX_BYTES:
            raise HTTPException(413,'Upload exceeds 5 MiB')
        if upload_lock.locked():
            raise HTTPException(409,'Another upload is in progress; retry shortly')
        up = None
        async with upload_lock:
            try:
                up = Upload(store,filename)
                async for block in request.stream():
                    up.feed(block)
                return up.finish()
            except UploadError as e:
                if up:
                    up.abort()
                raise HTTPException(400,str(e)) from e
            except BaseException:
                if up:
                    up.abort()
                raise

    @app.get('/api/jobs/{job_id}')
    def job_status(job_id:str):
        job = get_job(job_id)
        job['calls'] = [public_call(c) for c in store.calls(job_id)]
        job['findings_count'] = len(store.findings(job_id))
        return job

    @app.post('/api/jobs/{job_id}/start')
    def start(job_id:str):
        job = get_job(job_id)
        if runtime and runtime.error:
            raise HTTPException(503,runtime.error)
        if not model.health():
            raise HTTPException(503,'Local model is not ready; check the runtime log')
        if job['status'] in ('ready','needs_attention'):
            store.resume(job_id)
            worker.wake.set()
        return get_job(job_id)

    @app.get('/api/jobs/{job_id}/lines/{line}')
    def source_line(job_id:str,line:int):
        get_job(job_id)
        source = store.source(job_id,[line])
        if line not in source:
            raise HTTPException(404,'Source line not found')
        return {'line':line,'text':source[line]}

    @app.get('/api/jobs/{job_id}/report')
    def report(job_id:str,download:bool=False):
        job = get_job(job_id)
        candidates = store.candidates(job_id)
        for c in candidates:
            source = store.source(job_id,c['lines'])
            c['evidence'] = [{'line':n,'text':text[:1200],'shortened':len(text)>1200} for n,text in sorted(source.items())]
        calls = store.calls(job_id)
        accepted = [c for c in candidates if c['status']=='accepted']
        order = {'Critical':0,'High':1,'Medium':2,'Low':3}
        accepted.sort(key=lambda c:(order[c['severity']],c['attack_type']))
        data = {'schema_version':1,'prompt_version':PROMPT_VERSION,'job':job,
                'complete':job['status']=='completed','findings':accepted,
                'other_candidates':[c for c in candidates if c['status']!='accepted'],
                'coverage':{'completed_lines':min(job['cursor_line']-1,job['total_lines']),
                    'total_lines':job['total_lines'],'partial_line_offset':job['cursor_offset'],
                    'completed_calls':sum(c['status']=='completed' for c in calls),
                    'failed_calls':sum(c['status']=='failed' for c in calls),
                    'rejected_observations':sum(len(json.loads(c['rejected'] or '[]')) for c in calls)},
                'limits':['Possible attacks require human review. HTTP status does not establish exploitation.',
                          'Small local model plus conservative, source-corroborated rules can miss novel attacks.',
                          'Rate thresholds: 30 requests/60s, or 10 requests/5s with 3+ HTTP 429 responses. Login threshold: 5 failures.',
                          'Evidence is representative; all original lines and call attempts remain in SQLite.',
                          'Findings are not a complete security assessment, even when every chunk is processed.']}
        headers = {'Content-Disposition':f'attachment; filename="tracewatch-{job_id[:8]}.json"'} if download else None
        return JSONResponse(data,headers=headers)

    @app.get('/api/jobs/{job_id}/audit')
    def audit(job_id:str):
        job = get_job(job_id)
        return {'job':job,'calls':store.calls(job_id),'attempts':store.attempts(job_id),
                'candidates':store.candidates(job_id),'prompt_version':PROMPT_VERSION}

    @app.get('/')
    def index():
        return FileResponse(ROOT/'static'/'index.html')

    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
    return app


app = create_app()
