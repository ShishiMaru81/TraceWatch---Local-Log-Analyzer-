"""Read-only audit of source coverage and exact inference token budgets."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-id')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts'/'verification.json')
    args = parser.parse_args()
    db = sqlite3.connect(f'file:{ROOT / "data" / "state.sqlite3"}?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    job = dict(db.execute('SELECT * FROM jobs WHERE id=?',(args.job_id,)).fetchone()) if args.job_id else dict(db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 1').fetchone())
    calls = [dict(r) for r in db.execute('SELECT * FROM calls WHERE job_id=? ORDER BY id',(job['id'],))]
    cursor_line,cursor_offset = 1,0
    errors = []
    signal_counts = collections.Counter()
    for call in calls:
        payload = json.loads(call['payload'])
        if len(payload['tokens']) != call['input_tokens']:
            errors.append(f'Call {call["id"]}: token count inconsistent')
        if call['input_tokens']+448+32 > 2048 or call['input_tokens']+call['output_tokens']>2048:
            errors.append(f'Call {call["id"]}: budget violation')
        signal_counts.update(o['kind'] for o in json.loads(call['observations'] or '[]'))
        if call['stage']!='map' or call['status']!='completed':
            continue
        for fragment in payload['fragments']:
            if (fragment['line'],fragment['offset']) != (cursor_line,cursor_offset):
                errors.append(f'Call {call["id"]}: gap/overlap at {cursor_line}:{cursor_offset}')
            source = db.execute('SELECT text FROM lines WHERE job_id=? AND n=?',(job['id'],fragment['line'])).fetchone()[0]
            if source[fragment['offset']:fragment['offset']+len(fragment['text'])]!=fragment['text']:
                errors.append(f'Call {call["id"]}: source mismatch at line {fragment["line"]}')
            cursor_offset = fragment['offset']+len(fragment['text'])
            if cursor_offset == len(source):
                cursor_line,cursor_offset = fragment['line']+1,0
    if job['status']=='completed' and (cursor_line,cursor_offset)!=(job['total_lines']+1,0):
        errors.append('Completed report has incomplete map coverage')
    candidates = [json.loads(r[0]) for r in db.execute('SELECT data FROM candidates WHERE job_id=?',(job['id'],))]
    summary = {'job_id':job['id'],'filename':job['filename'],'source_sha256':job['source_hash'],
        'status':job['status'],'total_lines':job['total_lines'],'bytes':job['bytes'],
        'analysis_config':json.loads(job['analysis_config']) if job.get('analysis_config') else None,
        'facts_version':job.get('facts_version'),
        'completed_lines':cursor_line-1,'map_calls':sum(c['stage']=='map' for c in calls),
        'reduce_calls':sum(c['stage']=='reduce' for c in calls),'failed_calls':sum(c['status']=='failed' for c in calls),
        'incomplete_calls':sum(c['status']!='completed' for c in calls),
        'max_input_tokens':max((c['input_tokens'] for c in calls),default=0),
        'max_input_plus_reserved_output_and_margin':max((c['input_tokens']+448+32 for c in calls),default=0),
        'max_actual_input_plus_output':max((c['input_tokens']+c['output_tokens'] for c in calls),default=0),
        'output_reserve':448,'safety_margin':32,'context_limit':2048,
        'elapsed_seconds':round(job['elapsed'],2),'elapsed_note':'Persisted active analysis time; excludes downtime and uncommitted interrupted-call time.',
        'peak_backend_and_model_rss_bytes':job['peak_rss'],
        'validated_model_observations':dict(signal_counts),
        'rejected_model_observations':sum(len(json.loads(c['rejected'] or '[]')) for c in calls),
        'findings':[{k:c[k] for k in ['attack_type','severity','ip','host','account','lines','counts','status']} for c in candidates],
        'coverage_errors':errors,'browser_qa':'Not performed: localhost browser permission denied',
        'resource_limit_note':'RSS sampled on development host; not a full 4 GB VM or cgroup peak-memory proof.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(summary,indent=2))
    if errors or job['status']!='completed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
