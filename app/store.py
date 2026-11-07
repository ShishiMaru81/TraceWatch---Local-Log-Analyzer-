from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
import uuid
from .chunking import Fragment


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, filename TEXT, status TEXT, created REAL,
              bytes INTEGER DEFAULT 0, total_lines INTEGER DEFAULT 0, source_hash TEXT,
              cursor_line INTEGER DEFAULT 1, cursor_offset INTEGER DEFAULT 0,
              map_calls INTEGER DEFAULT 0, elapsed REAL DEFAULT 0,
              peak_rss INTEGER DEFAULT 0, error TEXT, updated REAL,
              facts_version INTEGER DEFAULT 1, analysis_config TEXT);
            CREATE TABLE IF NOT EXISTS lines (
              job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE, n INTEGER, text TEXT,
              PRIMARY KEY(job_id,n));
            CREATE TABLE IF NOT EXISTS events (
              job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE, line INTEGER, kind TEXT, data TEXT,
              PRIMARY KEY(job_id,line,kind));
            CREATE TABLE IF NOT EXISTS calls (
              id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
              stage TEXT, status TEXT, payload TEXT, input_tokens INTEGER,
              output_tokens INTEGER DEFAULT 0, seconds REAL DEFAULT 0, raw_reply TEXT,
              error TEXT, attempts INTEGER DEFAULT 0, observations TEXT, rejected TEXT,
              candidate_id TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS attempts (
              id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
              call_id INTEGER REFERENCES calls(id) ON DELETE CASCADE,
              number INTEGER, seconds REAL, error TEXT, raw_reply TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS candidates (
              job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE, id TEXT, data TEXT,
              PRIMARY KEY(job_id,id));
            CREATE INDEX IF NOT EXISTS events_job_line ON events(job_id,line);
            CREATE INDEX IF NOT EXISTS calls_job_status ON calls(job_id,status);
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(jobs)')}
            for name,definition in [('facts_version','INTEGER DEFAULT 1'),('analysis_config','TEXT')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def query(self, sql, args=()):
        with self.db() as db:
            return [dict(r) for r in db.execute(sql,args).fetchall()]

    def create(self, filename):
        from .detection import FACTS_VERSION
        job_id = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO jobs(id,filename,status,created,updated,facts_version) VALUES(?,?,?,?,?,?)',
                       (job_id,filename,'uploading',time.time(),time.time(),FACTS_VERSION))
        return job_id

    def delete(self, job_id):
        with self.db() as db:
            db.execute('DELETE FROM jobs WHERE id=?',(job_id,))

    def update(self, job_id, **values):
        allowed = {'status','bytes','total_lines','source_hash','cursor_line','cursor_offset','map_calls','elapsed','peak_rss','error','analysis_config','facts_version'}
        if not set(values) <= allowed:
            raise ValueError('Unknown job field')
        values['updated'] = time.time()
        with self.db() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),job_id))

    def job(self, job_id):
        rows = self.query('SELECT * FROM jobs WHERE id=?',(job_id,))
        return rows[0] if rows else None

    def jobs(self):
        return self.query('SELECT * FROM jobs ORDER BY created DESC LIMIT 40')

    def next_queued(self):
        rows = self.query("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1")
        return rows[0] if rows else None

    def append(self, job_id, batch):
        from .detection import extract_events
        with self.db() as db:
            for n,text in batch:
                db.execute('INSERT INTO lines VALUES(?,?,?)',(job_id,n,text))
                for event in extract_events(n,text):
                    db.execute('INSERT INTO events VALUES(?,?,?,?)',(job_id,n,event['kind'],json.dumps(event)))

    def lines(self, job_id, start=1, limit=30):
        return self.query('SELECT n,text FROM lines WHERE job_id=? AND n>=? ORDER BY n LIMIT ?',
                          (job_id,start,min(limit,100)))

    def source(self, job_id, numbers):
        if not numbers:
            return {}
        return {r['n']:r['text'] for r in self.query('SELECT n,text FROM lines WHERE job_id=? AND n IN ('+
                      ','.join('?' for _ in numbers)+')',(job_id,*numbers))}

    def fragments(self, job_id):
        job = self.job(job_id)
        rows = self.lines(job_id,job['cursor_line'],100)
        return [Fragment(r['n'],job['cursor_offset'] if i==0 else 0,
                         r['text'][job['cursor_offset']:] if i==0 else r['text']) for i,r in enumerate(rows)]

    def events(self, job_id, before=None):
        where, args = (' AND line<?',(job_id,before)) if before is not None else ('',(job_id,))
        return [json.loads(r['data']) for r in self.query('SELECT data FROM events WHERE job_id=?'+where+' ORDER BY line',args)]

    def refresh_events(self, job_id):
        from .detection import extract_events,FACTS_VERSION
        if self.job(job_id)['facts_version']==FACTS_VERSION:
            return
        with self.db() as db:
            db.execute('DELETE FROM events WHERE job_id=?',(job_id,))
            rows = db.execute('SELECT n,text FROM lines WHERE job_id=? ORDER BY n',(job_id,))
            for row in rows:
                for event in extract_events(row['n'],row['text']):
                    db.execute('INSERT INTO events VALUES(?,?,?,?)',(job_id,row['n'],event['kind'],json.dumps(event)))
            db.execute('UPDATE jobs SET facts_version=? WHERE id=?',(FACTS_VERSION,job_id))

    def new_call(self, job_id, stage, payload, candidate_id=None):
        with self.db() as db:
            cursor = db.execute('INSERT INTO calls(job_id,stage,status,payload,input_tokens,candidate_id,created) VALUES(?,?,?,?,?,?,?)',
                (job_id,stage,'pending',json.dumps(payload),len(payload['tokens']),candidate_id,time.time()))
            return dict(db.execute('SELECT * FROM calls WHERE id=?',(cursor.lastrowid,)).fetchone())

    def calls(self, job_id):
        return self.query('SELECT * FROM calls WHERE job_id=? ORDER BY id',(job_id,))

    def observations(self, job_id):
        rows = self.query("SELECT observations FROM calls WHERE job_id=? AND stage='map' AND status='completed' ORDER BY id",(job_id,))
        return [item for row in rows for item in json.loads(row['observations'] or '[]')]

    def pending_call(self, job_id):
        rows = self.query("SELECT * FROM calls WHERE job_id=? AND status!='completed' ORDER BY id LIMIT 1",(job_id,))
        return rows[0] if rows else None

    def attempt(self, call, seconds, error, raw):
        with self.db() as db:
            db.execute('UPDATE calls SET attempts=attempts+1,error=? WHERE id=?',(error,call['id']))
            attempts = db.execute('SELECT attempts FROM calls WHERE id=?',(call['id'],)).fetchone()[0]
            db.execute('INSERT INTO attempts(job_id,call_id,number,seconds,error,raw_reply,created) VALUES(?,?,?,?,?,?,?)',
                       (call['job_id'],call['id'],attempts,seconds,error,raw,time.time()))

    def finish_call(self, call, result, seconds, observations=None, rejected=None, candidate=None):
        payload = json.loads(call['payload'])
        with self.db() as db:
            db.execute("UPDATE calls SET status='completed',output_tokens=?,seconds=?,raw_reply=?,observations=?,rejected=?,error=NULL WHERE id=?",
                       (result.get('tokens_predicted',0),seconds,result['content'],json.dumps(observations or []),json.dumps(rejected or []),call['id']))
            if call['stage'] == 'map':
                last = payload['fragments'][-1]
                source_length = db.execute('SELECT length(text) FROM lines WHERE job_id=? AND n=?',(call['job_id'],last['line'])).fetchone()[0]
                end = last['offset'] + len(last['text'])
                cursor_line,cursor_offset = (last['line']+1,0) if end >= source_length else (last['line'],end)
                db.execute('UPDATE jobs SET cursor_line=?,cursor_offset=?,map_calls=map_calls+1,updated=? WHERE id=?',
                           (cursor_line,cursor_offset,time.time(),call['job_id']))
            elif candidate:
                db.execute('UPDATE candidates SET data=? WHERE job_id=? AND id=?',
                           (json.dumps(candidate),call['job_id'],candidate['id']))

    def fail_call(self, call, error):
        with self.db() as db:
            db.execute("UPDATE calls SET status='failed',error=? WHERE id=?",(error,call['id']))
        self.update(call['job_id'],status='needs_attention',error=error)

    def candidates(self, job_id):
        return [json.loads(r['data']) for r in self.query('SELECT data FROM candidates WHERE job_id=? ORDER BY id',(job_id,))]

    def findings(self, job_id):
        return [c for c in self.candidates(job_id) if c['status'] == 'accepted']

    def save_candidates(self, job_id, candidates):
        with self.db() as db:
            for c in candidates:
                db.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?)',(job_id,c['id'],json.dumps(c)))

    def attempts(self, job_id):
        return self.query('SELECT * FROM attempts WHERE job_id=? ORDER BY id',(job_id,))

    def resume(self, job_id):
        with self.db() as db:
            db.execute("UPDATE calls SET status='pending' WHERE job_id=? AND status='failed'",(job_id,))
            db.execute("UPDATE jobs SET status='queued',error=NULL,updated=? WHERE id=? AND status NOT IN ('completed','uploading')",(time.time(),job_id))

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='queued',error='Resuming after backend restart' WHERE status IN ('analyzing','reducing')")
            db.execute("DELETE FROM jobs WHERE status='uploading'")
