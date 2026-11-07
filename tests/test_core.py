import json
import pytest

from app.chunking import Fragment, pack_next
from app.prompts import OUTPUT_TOKENS, SAFETY_TOKENS, CONTEXT_SIZE
from app.model import parse_reply, ReplyError
from app.detection import extract_events, build_candidates, validate_observations


class Tokenizer:
    """Deliberately expensive tokenizer to exercise boundary conditions."""
    def prepare(self, messages):
        return list(json.dumps(messages, ensure_ascii=False).encode('utf-8'))


def test_chunk_budget_covers_oversized_unicode_without_loss():
    source = [Fragment(1, 0, 'first entry'), Fragment(2, 0, '漢字🙂' * 700), Fragment(3, 0, 'last')]
    rest = source
    seen = []
    while rest:
        selected, tokens, rest, memory = pack_next(rest, Tokenizer(), lambda _: '')
        assert len(tokens) + OUTPUT_TOKENS + SAFETY_TOKENS <= CONTEXT_SIZE
        assert selected
        seen.extend(selected)
    for entry in source:
        pieces = [p for p in seen if p.line == entry.line]
        assert ''.join(p.text for p in pieces) == entry.text
        assert [p.offset for p in pieces] == [sum(len(q.text) for q in pieces[:i]) for i in range(len(pieces))]


def test_entries_stay_whole_when_they_fit():
    source = [Fragment(i, 0, 'entry ' + str(i)) for i in range(1, 4)]
    selected, _, rest, _ = pack_next(source, Tokenizer(), lambda _: '')
    assert selected == source and not rest


def test_broken_json_is_not_silently_accepted():
    assert parse_reply('```json\n{"observations": []}\n```')['observations'] == []
    for raw in ['{"observations":[', 'prose {"observations":[]} junk', '{"a":NaN}']:
        with pytest.raises(ReplyError):
            parse_reply(raw)


def logline(ip='203.0.113.5', host='one', username='admin', result='invalid_password', **extra):
    return json.dumps(dict(client_ip=ip, host=host, username=username, auth_result=result,
                           time='2026-01-01T00:00:00Z', path='/login', status=401, **extra))


def test_login_chain_links_distant_parts_and_deduplicates():
    events = []
    for line in [1, 70, 150, 200, 270]:
        events.extend(extract_events(line, logline()))
    events.extend(extract_events(900, logline(result='success')))
    candidates = build_candidates(events)
    chain = [c for c in candidates if c['attack_type'] == 'Possible account compromise']
    assert len(chain) == 1
    assert {1, 270, 900} <= set(chain[0]['lines'])
    assert not any(c['attack_type'] == 'Repeated login attempts' for c in candidates)


def test_does_not_join_hosts_accounts_or_success_before_failures():
    events = extract_events(1, logline(result='success'))
    for line in range(2, 7):
        events += extract_events(line, logline())
    events += extract_events(8, logline(host='two', result='success'))
    events += extract_events(9, logline(username='someone', result='success'))
    assert not any(c['attack_type'] == 'Possible account compromise' for c in build_candidates(events))


def test_errors_and_health_checks_do_not_become_attacks():
    events = extract_events(1, '{"level":"ERROR","message":"Database command timed out"}')
    for i in range(2, 90):
        events += extract_events(i, json.dumps(dict(client_ip='192.0.2.10', path='/health', status=200,
                                                    time='2026-01-01T00:00:00Z')))
    assert build_candidates(events) == []


def test_model_citations_require_current_source_and_real_signals():
    source = {1: logline(), 2: '{"message":"Database timeout"}'}
    reply = {'observations': [{'kind':'auth_failure','lines':[1]},
                               {'kind':'sql_injection','lines':[2]},
                               {'kind':'scan','lines':[999]}]}
    valid, rejected = validate_observations(reply, source)
    assert len(valid) == 1
    assert len(rejected) == 2


def test_encoded_injection_is_evidence_but_not_confirmed_exploitation():
    events = extract_events(9, json.dumps(dict(client_ip='192.0.2.50', host='app',
                            path='/search?q=%27%20OR%201%3D1--', status=403)))
    findings = build_candidates(events)
    assert len(findings) == 1
    assert findings[0]['attack_type'] == 'SQL injection attempt'
    assert findings[0]['severity'] == 'Medium'


def test_short_rate_limited_burst_is_detected_without_flagging_normal_assets():
    from datetime import datetime,timedelta,timezone
    events = []
    normal = []
    start = datetime(2026,1,1,tzinfo=timezone.utc)
    for i in range(12):
        row = dict(client_ip='192.0.2.88',host='api',path='/weather',
                   time=(start+timedelta(milliseconds=i*200)).isoformat(),status=429 if i>=3 else 200)
        events += extract_events(i+1,json.dumps(row))
        normal += extract_events(i+1,json.dumps(dict(row,status=200,path=f'/assets/{i}.js')))
    candidates = build_candidates(events)
    assert len(candidates) == 1
    assert candidates[0]['attack_type'] == 'Unusual request rate'
    assert candidates[0]['counts']['rate_limited_responses'] == 9
    assert not build_candidates(normal)


def test_syslog_hosts_are_kept_separate():
    events = []
    for line in range(1,6):
        events += extract_events(line,'Nov  1 08:00:00 host-a sshd[12]: Failed password for admin from 203.0.113.4 port 2222 ssh2')
    events += extract_events(6,'Nov  1 08:00:01 host-b sshd[14]: Accepted password for admin from 203.0.113.4 port 2222 ssh2')
    assert {e['host'] for e in events} == {'host-a','host-b'}
    assert not any(c['attack_type']=='Possible account compromise' for c in build_candidates(events))


def test_larger_ordinary_burst_does_not_hide_smaller_rate_limited_burst():
    from datetime import datetime,timedelta,timezone
    start = datetime(2026,1,1,tzinfo=timezone.utc)
    events = []
    for i in range(25):
        seconds = i/10 if i<15 else 20+(i-15)/10
        row = dict(client_ip='192.0.2.1',host='api',path='/api/data',
                   time=(start+timedelta(seconds=seconds)).isoformat(),status=429 if i>=22 else 200)
        events += extract_events(i+1,json.dumps(row))
    candidates = build_candidates(events)
    assert len(candidates)==1
    assert candidates[0]['counts']['requests_in_window']==10
    assert candidates[0]['counts']['rate_limited_responses']==3


def test_multiline_entry_moves_to_next_chunk_when_whole_entry_can_fit():
    source = [Fragment(1,0,'x'*360), Fragment(2,0,'2026-01-01 error '+'A'*140),
              Fragment(3,0,'  at function '+'B'*140),Fragment(4,0,'  at caller '+'C'*140)]
    selected,_,rest,_ = pack_next(source,Tokenizer(),lambda _: '')
    assert selected == [source[0]]
    selected,_,rest,_ = pack_next(rest,Tokenizer(),lambda _: '')
    assert selected == source[1:] and not rest


def test_duplicate_event_ids_do_not_inflate_failed_login_counts():
    events = []
    for line in range(1,7):
        events += extract_events(line,logline(event_id='same-event',request_id='same-request'))
    assert build_candidates(events) == []


def test_numeric_syslog_host_does_not_replace_remote_client():
    line = 'Nov 7 12:00:00 10.0.0.1 sshd: Failed password for admin from 203.0.113.4 port 2222 ssh2'
    events = extract_events(1,line)
    assert events[0]['host']=='10.0.0.1'
    assert events[0]['ip']=='203.0.113.4'


def test_later_valid_success_is_checked_after_out_of_order_timestamps():
    events = []
    for line in range(1,6):
        row = json.loads(logline())
        row['time']='2026-01-02T00:00:00Z' if line==1 else '2026-01-01T00:00:00Z'
        events += extract_events(line,json.dumps(row))
    for line,ts in [(6,'2026-01-01T12:00:00Z'),(7,'2026-01-03T00:00:00Z')]:
        row = json.loads(logline(result='success'));row['time']=ts
        events += extract_events(line,json.dumps(row))
    findings = build_candidates(events)
    assert findings[0]['attack_type']=='Possible account compromise'
    assert findings[0]['counts']['later_success_line']==7
