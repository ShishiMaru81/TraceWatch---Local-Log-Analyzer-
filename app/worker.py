from collections import Counter
from dataclasses import asdict
import json
import logging
import os
import threading
import time
import psutil
from .chunking import pack_next
from .detection import build_candidates, fields, representative, validate_observations
from .model import parse_reply, ReplyError
from .runtime import MODEL_CONFIG
from .prompts import (MAP_SCHEMA, REDUCE_SCHEMA, MEMORY_TOKENS, CONTEXT_SIZE,
                      OUTPUT_TOKENS, SAFETY_TOKENS, PROMPT_VERSION, reduce_messages)

log = logging.getLogger('analyzer')


def memory_usage():
    process = psutil.Process()
    processes = [process] + process.children(recursive=True)
    rss = 0
    for p in processes:
        try:
            rss += p.memory_info().rss
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            pass
    return rss


class Worker:
    def __init__(self, store, model, retry_delay=2):
        self.store, self.model, self.retry_delay = store,model,retry_delay
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.active = None

    def loop(self):
        self.store.recover()
        while not self.stop.is_set():
            job = self.store.next_queued()
            if not job:
                self.wake.wait(1)
                self.wake.clear()
                continue
            self.run_job(job['id'])

    def memory_for(self, job_id, fragments):
        identities = {(fields(f.text).get('client_ip'),fields(f.text).get('host','unknown')) for f in fragments}
        previous = self.store.events(job_id,before=fragments[0].line)
        grouped = {}
        for e in previous:
            if (e['ip'],e['host']) not in identities or e['kind'] == 'request':
                continue
            key = (e['ip'],e['host'],e['account'])
            if key not in grouped:
                grouped[key] = {'ip':e['ip'],'host':e['host'],'account':e['account'],'counts':Counter(),'first_line':e['line'],'last_line':e['line']}
            grouped[key]['counts'][e['kind']] += 1
            grouped[key]['last_line'] = e['line']
        chosen = []
        for row in sorted(grouped.values(),key=lambda x:x['first_line']):
            proposed = json.dumps(chosen+[row],separators=(',',':'))
            if len(self.model.tokenize(proposed)) <= MEMORY_TOKENS:
                chosen.append(row)
        return json.dumps(chosen,separators=(',',':')) if chosen else ''

    def process_one_map(self, job_id):
        call = self.store.pending_call(job_id)
        if not call:
            fragments = self.store.fragments(job_id)
            if not fragments:
                return False
            selected,tokens,_,memory = pack_next(fragments,self.model,lambda fs:self.memory_for(job_id,fs))
            payload = {'tokens':tokens,'fragments':[asdict(f) for f in selected],
                       'memory':memory,'prompt_version':PROMPT_VERSION}
            call = self.store.new_call(job_id,'map',payload)
        if call['stage'] != 'map':
            return False
        return self.execute(call)

    def reduce_call(self, job_id, candidate):
        numbers = candidate['lines']
        # Early, middle, late evidence is present even across distant chunks.
        priorities = representative(numbers,3) + numbers
        source = self.store.source(job_id,numbers)
        evidence = []
        tokens = self.model.prepare(reduce_messages(candidate,evidence))
        limit = CONTEXT_SIZE - OUTPUT_TOKENS - SAFETY_TOKENS
        for n in dict.fromkeys(priorities):
            row = fields(source[n])
            keys = ['time','timestamp','host','client_ip','username','auth_result','method','path','status','message']
            projected = {k:(v[:350]+' [field shortened]' if isinstance(v,str) and len(v)>350 else v)
                         for k,v in row.items() if k in keys}
            item = {'line':n,'data':projected} if projected else {'line':n,'text':source[n][:500],'shortened':len(source[n])>500}
            trial = evidence+[item]
            prepared = self.model.prepare(reduce_messages(candidate,trial))
            if len(prepared) <= limit:
                evidence,tokens = trial,prepared
        if not evidence:
            raise ReplyError('Candidate evidence cannot fit the context; no judgment made')
        required = {numbers[0],numbers[-1]}
        if not required <= {e['line'] for e in evidence}:
            # Never let an unrepresented successful login justify a compromise.
            raise ReplyError('Required early/late evidence did not fit; no judgment made')
        payload = {'tokens':tokens,'evidence':evidence,'candidate':candidate,'prompt_version':PROMPT_VERSION}
        return self.store.new_call(job_id,'reduce',payload,candidate['id'])

    def combined_candidates(self, job_id):
        events = self.store.events(job_id)
        candidates = build_candidates(events)
        observations = self.store.observations(job_id)
        by_line = {}
        for e in events:
            by_line.setdefault(e['line'],[]).append(e)
        for candidate in candidates:
            relevant = []
            for o in observations:
                for e in by_line.get(o['line'],[]):
                    if e['kind']==o['kind'] and e['ip']==candidate['ip'] and e['host']==candidate['host'] and (
                        not candidate['account'] or e['account']==candidate['account']):
                        relevant.append(o)
                        break
            # Only a bounded selection enters the context; all stay in the DB.
            chosen_lines = set(representative([o['line'] for o in relevant],4))
            candidate['model_observations'] = [o for o in relevant if o['line'] in chosen_lines][:4]
            candidate['validated_map_signal_count'] = len(relevant)
        return candidates

    def execute(self, call):
        payload = json.loads(call['payload'])
        last_error = 'Call did not complete'
        for attempt in range(3):
            if self.stop.is_set():
                return False
            start,raw = time.monotonic(),None
            try:
                result = self.model.complete(payload['tokens'],MAP_SCHEMA if call['stage']=='map' else REDUCE_SCHEMA)
                raw = result['content']
                reply = parse_reply(raw)
                observations,rejected,candidate = [],[],None
                if call['stage'] == 'map':
                    source = {}
                    for f in payload['fragments']:
                        source[f['line']] = source.get(f['line'],'') + f['text']
                    observations,rejected = validate_observations(reply,source)
                else:
                    if type(reply.get('supported')) is not bool or not isinstance(reply.get('reason'),str) or not isinstance(reply.get('action'),str):
                        raise ReplyError('Invalid candidate judgment schema')
                    if not reply['reason'].strip() or not reply['action'].strip():
                        raise ReplyError('Candidate judgment is missing its explanation or action')
                    candidate = dict(payload['candidate'],status='accepted' if reply['supported'] else 'rejected',
                                     model_reason=reply['reason'][:500],model_action=reply['action'][:500],
                                     assessed_evidence_lines=[e['line'] for e in payload['evidence']])
                seconds = time.monotonic()-start
                self.store.attempt(call,seconds,None,raw)
                self.store.finish_call(call,result,seconds,observations,rejected,candidate)
                log.info('job=%s call=%s stage=%s input=%s output=%s seconds=%.2f',
                         call['job_id'],call['id'],call['stage'],len(payload['tokens']),result.get('tokens_predicted'),seconds)
                return True
            except Exception as e:
                # No reply is salvaged by inventing missing JSON. Exact payload is retried.
                seconds = time.monotonic()-start
                error = f'{type(e).__name__}: {str(e)[:350]}'
                last_error = error
                self.store.attempt(call,seconds,error,raw)
                log.warning('job=%s call=%s attempt=%s %s',call['job_id'],call['id'],attempt+1,error)
                if attempt < 2:
                    self.stop.wait(self.retry_delay * 2**attempt)
        self.store.fail_call(call,last_error)
        return False

    def run_job(self, job_id):
        self.active = job_id
        start = time.monotonic()
        initial = self.store.job(job_id)
        if not initial:
            return
        try:
            fingerprint = {'model_sha256':MODEL_CONFIG['sha256'],'prompt_version':PROMPT_VERSION,
                           'model_name':MODEL_CONFIG['name'],'quantization':MODEL_CONFIG['quantization']}
            if initial.get('analysis_config'):
                saved = json.loads(initial['analysis_config'])
                if saved.get('model_sha256')!=fingerprint['model_sha256'] or saved.get('prompt_version')!=PROMPT_VERSION:
                    raise ValueError('Model or prompt changed. Upload the file as a new analysis; saved token IDs cannot be reused safely.')
            else:
                self.store.update(job_id,analysis_config=json.dumps(fingerprint))
            self.store.refresh_events(job_id)
            self.store.update(job_id,status='analyzing',error=None)
            while not self.stop.is_set():
                current = self.store.job(job_id)
                rss = memory_usage()
                peak = max(current['peak_rss'],rss)
                self.store.update(job_id,peak_rss=peak,elapsed=initial['elapsed']+time.monotonic()-start)
                if rss > 3 * 1024**3:
                    raise MemoryError('Backend + child processes exceeded 3 GiB RSS; paused to protect the 4 GB machine')
                pending = self.store.pending_call(job_id)
                if (pending and pending['stage']=='map') or current['cursor_line'] <= current['total_lines']:
                    if not self.process_one_map(job_id):
                        return
                    continue
                break
            if self.stop.is_set():
                return
            self.store.update(job_id,status='reducing')
            self.store.save_candidates(job_id,self.combined_candidates(job_id))
            for candidate in self.store.candidates(job_id):
                if candidate['status'] != 'pending':
                    continue
                call = self.store.pending_call(job_id) or self.reduce_call(job_id,candidate)
                if not self.execute(call):
                    return
                self.store.update(job_id,peak_rss=max(self.store.job(job_id)['peak_rss'],memory_usage()),
                                  elapsed=initial['elapsed']+time.monotonic()-start)
            self.store.update(job_id,status='completed',error=None)
        except Exception as e:
            log.exception('job failed: %s',job_id)
            self.store.update(job_id,status='needs_attention',error=f'{type(e).__name__}: {str(e)[:350]}')
        finally:
            self.store.update(job_id,elapsed=initial['elapsed']+time.monotonic()-start)
            self.active = None
