"""Submit a file to the running local app and wait, emitting compact status."""
import argparse
import json
from pathlib import Path
import time
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file',type=Path)
    parser.add_argument('--output',type=Path,default=Path('artifacts/report.json'))
    args = parser.parse_args()
    with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=30) as client:
        with args.file.open('rb') as source:
            response = client.post('/api/jobs',params={'filename':args.file.name},content=source)
        response.raise_for_status()
        job = response.json()
        job_id = job['id']
        response = client.post(f'/api/jobs/{job_id}/start')
        response.raise_for_status()
        print(f'Analysis {job_id}',flush=True)
        previous = None
        while True:
            response = client.get(f'/api/jobs/{job_id}')
            response.raise_for_status()
            job = response.json()
            current = job['status'],job['cursor_line'],len(job['calls'])
            if current!=previous:
                print(f"{job['status']}: {min(job['cursor_line']-1,job['total_lines'])}/{job['total_lines']} lines; "
                      f"{job['map_calls']} map calls; peak RSS {job['peak_rss']/1024**2:.1f} MiB",flush=True)
                previous = current
            if job['status'] in ('completed','needs_attention'):
                report = client.get(f'/api/jobs/{job_id}/report').json()
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
                print(f'Report: {args.output.resolve()}',flush=True)
                if job['status']!='completed':
                    raise SystemExit(f"Incomplete: {job['error']}. Resume in the dashboard.")
                break
            time.sleep(3)


if __name__=='__main__':
    main()
