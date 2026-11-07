"""Source corroboration and full-file correlation, independent of LLM memory."""
from collections import defaultdict
from datetime import datetime
import hashlib
import ipaddress
import json
import re
from urllib.parse import unquote

SQL = re.compile(r"(?:\bunion\s+(?:all\s+)?select\b|\bor\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+|\b(?:sleep|benchmark|extractvalue)\s*\(|;\s*(?:drop|select)\b)", re.I)
PROBE = re.compile(r'(?:/\.env(?:[/?]|$)|/\.git(?:/|$)|/wp-(?:admin|login)|/xmlrpc\.php|/phpmyadmin|/etc/passwd|/actuator|/server-status|\.\./)', re.I)
IP = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
AUTH_PATH = re.compile(r'(?:login|sign[-_]?in|authenticate|/auth/)', re.I)
FACTS_VERSION = 2


def fields(text):
    try:
        row = json.loads(text)
        if isinstance(row, dict):
            return row
    except (ValueError, TypeError):
        pass
    # Conservative support for common access and auth text logs.
    row = {}
    syslog = re.match(r'^(?:<\d{1,3}>)?(?:[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}|(?:1\s+)?\d{4}-\d{2}-\d{2}T\S+)\s+([\w.-]+)\s+', text)
    if syslog:
        row['host'] = syslog[1]
    remote = re.search(r'\bfrom\s+([0-9a-fA-F:.]+)(?:\s|$)',text) if 'sshd' in text else None
    found = remote or IP.search(text)
    if found:
        row['client_ip'] = found[1] if remote else found.group()
    request = re.search(r'"(?:GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+(\S+)\s+HTTP/[\d.]+"\s+(\d{3})', text)
    if request:
        row.update(path=request[1], status=int(request[2]))
    user = re.search(r'(?:user(?:name)?[=: ]+|for (?:invalid user )?)([\w.@-]+)', text, re.I)
    if user:
        row['username'] = user[1]
    if re.search(r'failed password|authentication fail|invalid password', text, re.I):
        row['auth_result'] = 'invalid_password'
    if re.search(r'accepted (?:password|publickey)|login success', text, re.I):
        row['auth_result'] = 'success'
    iso = re.search(r'\d{4}-\d\d-\d\d[T ][\d:.]+(?:Z|[+-]\d\d:\d\d)?', text)
    if iso:
        row['time'] = iso[0]
    common = re.search(r'\[(\d\d/\w+/\d{4}:\d\d:\d\d:\d\d [+-]\d{4})\]', text)
    if common:
        try:
            row['time'] = datetime.strptime(common[1], '%d/%b/%Y:%H:%M:%S %z').isoformat()
        except ValueError:
            pass
    return row


def extract_events(line, text):
    row = fields(text)
    ip = str(row.get('client_ip') or row.get('remote_addr') or row.get('ip') or '')[:100]
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        ip = ''
    account = str(row.get('username') or row.get('user') or '')[:120]
    if not ip and not account:
        return []
    host = str(row.get('host') or row.get('server_name') or 'unknown')[:200]
    path = str(row.get('path') or row.get('request_uri') or '')[:12000]
    decoded = unquote(unquote(path))
    try:
        status = int(row.get('status', 0))
    except (TypeError, ValueError):
        status = 0
    timestamp = str(row.get('time') or row.get('timestamp') or '')[:80]
    base = dict(line=line, ip=ip, host=host, account=account, time=timestamp, path=path, status=status,
                event_id=str(row.get('event_id') or '')[:160],request_id=str(row.get('request_id') or '')[:160])
    kinds = []
    result = str(row.get('auth_result', '')).lower()
    auth = bool(result) or bool(AUTH_PATH.search(path))
    if result in ('invalid_password','failed','failure','denied') or (auth and status == 401):
        kinds.append('auth_failure')
    if result in ('success','accepted','authenticated'):
        kinds.append('auth_success')
    if SQL.search(decoded):
        kinds.append('sql_injection')
    if PROBE.search(decoded):
        kinds.append('scan')
    if status in (401,403) and not auth:
        kinds.append('unauthorized')
    if path and timestamp and not (path.split('?')[0] in ('/health','/ready','/healthz','/livez') and 200 <= status < 300):
        kinds.append('request')
    return [dict(base, kind=kind) for kind in kinds]


def validate_observations(reply, source):
    observations = reply.get('observations')
    if not isinstance(observations, list) or len(observations) > 12:
        from .model import ReplyError
        raise ReplyError('Missing or invalid observations array')
    accepted, rejected = [], []
    for item in observations:
        if not isinstance(item, dict) or not isinstance(item.get('lines'), list) or not item['lines'] or len(item['lines']) > 12:
            rejected.append({'proposal':item, 'reason':'Invalid observation schema'})
            continue
        kind = item.get('kind')
        for line in item['lines']:
            if type(line) is not int or line not in source:
                rejected.append({'proposal':item, 'reason':'Citation outside current chunk'})
                continue
            supported = [e for e in extract_events(line, source[line]) if e['kind'] == ('request' if kind == 'rate' else kind)]
            if supported:
                accepted.append({'kind':kind,'line':line})
            else:
                rejected.append({'proposal':item, 'reason':f'Line {line}: no corroborating source signal'})
    return accepted, rejected


def epoch(value):
    try:
        date = datetime.fromisoformat(value.replace('Z','+00:00'))
        return date.timestamp() if date.tzinfo else None
    except (ValueError, AttributeError):
        return None


def representative(lines, limit=9):
    unique = sorted(set(lines))
    if len(unique) <= limit:
        return unique
    return [unique[round(i * (len(unique)-1)/(limit-1))] for i in range(limit)]


def build_candidates(events):
    auth, groups = defaultdict(list), defaultdict(list)
    seen = set()
    for e in events:
        identifier = e.get('event_id') or e.get('request_id')
        if identifier:
            identity = (e['host'],e['kind'],identifier,e['ip'],e['account'],e['time'],e['path'],e['status'])
            if identity in seen:
                continue
            seen.add(identity)
        if e['kind'] in ('auth_failure','auth_success'):
            auth[(e['ip'],e['host'],e['account'])].append(e)
        else:
            groups[(e['ip'],e['host'],e['kind'])].append(e)
    result = []

    def add(attack, severity, ip, host, account, rows, counts, reason, action):
        identity = json.dumps([attack,ip,host,account], separators=(',',':'))
        all_lines = sorted(set(e['line'] for e in rows))
        result.append(dict(id=hashlib.sha256(identity.encode()).hexdigest()[:20], attack_type=attack,
                           severity=severity, ip=ip, host=host, account=account,
                           lines=representative(all_lines), total_evidence_lines=len(all_lines),
                           counts=counts, reason=reason, action=action, status='pending'))

    for (ip,host,account), rows in sorted(auth.items()):
        rows.sort(key=lambda e:e['line'])
        failures = [e for e in rows if e['kind'] == 'auth_failure']
        if len(failures) < 5:
            continue
        successes = [e for e in rows if e['kind'] == 'auth_success' and e['line'] > failures[4]['line']]
        # Prefer timestamps; if absent, explicitly use source-file order.
        successes = [s for s in successes if epoch(s['time']) is None or epoch(failures[4]['time']) is None
                     or epoch(s['time']) >= epoch(failures[4]['time'])]
        linked = False
        for success in successes:
            prior = [e for e in failures if e['line'] < success['line'] and
                     (epoch(e['time']) is None or epoch(success['time']) is None or epoch(e['time']) <= epoch(success['time']))]
            if len(prior) >= 5:
                add('Possible account compromise','High',ip,host,account,prior+[success],
                    {'failed_logins':len(prior),'later_success_line':success['line']},
                    f'{len(prior)} failed logins followed by success for the same IP, host and account. This suggests possible brute force followed by compromise; success alone does not prove unauthorized control.',
                    'Verify the login with the account owner; revoke suspicious sessions, rotate credentials and require MFA. Review subsequent actions.')
                linked = True
                break
        if linked:
            continue
        add('Repeated login attempts','Medium',ip,host,account,failures,{'failed_logins':len(failures)},
            f'{len(failures)} failed logins for one scoped identity; repeated attempts warrant investigation.',
            'Review authentication history; apply per-account/IP throttling and require MFA.')

    for (ip,host,kind), rows in sorted(groups.items()):
        if kind == 'sql_injection':
            add('SQL injection attempt','Medium',ip,host,'',rows,{'payload_requests':len(rows)},
                f'{len(rows)} requests contain SQL injection syntax. HTTP status does not prove SQL execution.',
                'Review application and database audit logs; use parameterized queries and validate input. Apply temporary rate limits if appropriate.')
        if kind == 'scan' and len(set(e['path'].split('?')[0] for e in rows)) >= 3:
            add('Endpoint scanning','Medium',ip,host,'',rows,{'probe_requests':len(rows),'distinct_paths':len(set(e['path'] for e in rows))},
                'One IP probed several sensitive or unrelated administrative paths; this is consistent with scanning.',
                'Verify whether this is an authorized scanner; restrict sensitive endpoints and investigate successful responses.')
        if kind == 'unauthorized' and len(rows) >= 3:
            add('Repeated unauthorized access','Medium',ip,host,'',rows,{'denied_requests':len(rows)},
                f'{len(rows)} non-login requests returned 401/403. These are denied attempts, not evidence of a successful bypass.',
                'Review requested resources and authorization policy; investigate whether the client has legitimate access needs.')
        if kind == 'request':
            timed = sorted((epoch(e['time']),e['line'],e) for e in rows if epoch(e['time']) is not None)
            def busiest(window, minimum_limited=0):
                left, best_start, best_end, limited_count = 0, 0, 0, 0
                for right, (ts,_,_) in enumerate(timed):
                    limited_count += timed[right][2]['status']==429
                    while timed[left][0] < ts - window:
                        limited_count -= timed[left][2]['status']==429
                        left += 1
                    if limited_count>=minimum_limited and right-left+1 > best_end-best_start:
                        best_start,best_end = left,right+1
                return [x[2] for x in timed[best_start:best_end]]
            minute,burst = busiest(60),busiest(5,minimum_limited=3)
            limited = sum(e['status']==429 for e in burst)
            best,window = (burst,5) if len(burst)>=10 and limited>=3 else (minute,60)
            if (window==5) or len(best) >= 30:
                counts = {'requests_in_window':len(best),'window_seconds':window,
                          'rate_limited_responses':sum(e['status']==429 for e in best)}
                add('Unusual request rate','Medium',ip,host,'',best,counts,
                    f"{len(best)} requests from one IP/host within {window} seconds, with {counts['rate_limited_responses']} HTTP 429 responses. This is an investigation signal, not proof of denial of service.",
                    'Compare against expected client traffic, inspect affected endpoints and apply measured rate limits if abuse is verified.')
    return result
