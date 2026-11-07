/* Logs are never interpreted as HTML, code, or URLs. */
const $ = id => document.getElementById(id);
const state = { file: null, jobId: localStorage.getItem('tracewatch.job'), job: null, report: null, severity: 'All', busy: false, ready: false, lastReportKey: '', refreshing: false };
const activeStates = new Set(['queued', 'analyzing', 'reducing']);
const labels = { ready: 'Ready', queued: 'Queued', analyzing: 'Analyzing', reducing: 'Connecting events', completed: 'Complete', needs_attention: 'Needs attention' };
const node = (tag, cls, text) => { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; };
function icon(name, cls = 'icon') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('class', cls); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', '#i-' + name); svg.append(use); return svg;
}
function toast(message) { $('toast').textContent = message; $('toast').classList.remove('hidden'); clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').classList.add('hidden'), 9000); }
async function api(path, options = {}) {
  const response = await fetch(path, options); let data;
  try { data = await response.json(); } catch { throw new Error('Invalid response from the local server. Check the backend log.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Local server request failed.'); return data;
}
function duration(seconds) { if (seconds < 60) return Math.round(seconds) + 's'; return Math.floor(seconds / 60) + 'm ' + Math.round(seconds % 60) + 's'; }
function updateButton() { $('start').disabled = !state.file || state.busy || !state.ready; }
function choose(file) {
  if (!file) return;
  if (!/\.(log|txt)$/i.test(file.name)) return toast('Choose a .log or .txt file.');
  if (!file.size || file.size > 5 * 1024 ** 2) return toast('Choose a nonempty file up to 5 MiB.');
  state.file = file; $('drop-title').textContent = file.name; $('drop-description').textContent = (file.size / 1024).toFixed(1) + ' KiB · Ready for local analysis';
  $('file-pill').textContent = 'FILE SELECTED'; $('file-pill').classList.remove('hidden'); updateButton();
}
$('file').addEventListener('change', e => choose(e.target.files[0]));
for (const event of ['dragenter', 'dragover']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.add('dragging'); });
for (const event of ['dragleave', 'drop']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.remove('dragging'); });
$('dropzone').addEventListener('drop', e => { if (e.dataTransfer.files.length !== 1) return toast('Choose one file at a time.'); choose(e.dataTransfer.files[0]); });
$('new-analysis').addEventListener('click', () => {
  Object.assign(state, { jobId: null, job: null, report: null, lastReportKey: '', file: null }); localStorage.removeItem('tracewatch.job'); $('file').value = '';
  $('drop-title').replaceChildren(document.createTextNode('Drop a log file here, or '), node('span', '', 'browse files')); $('drop-description').textContent = '.log or .txt · Up to 5 MiB'; $('file-pill').classList.add('hidden');
  renderJob(); renderFindings(); refresh(); window.scrollTo({ top: 0, behavior: 'smooth' });
});
$('start').addEventListener('click', async () => {
  if (!state.file || state.busy) return; state.busy = true; $('start').textContent = 'Uploading…'; updateButton();
  try {
    const job = await api('/api/jobs?filename=' + encodeURIComponent(state.file.name), { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: state.file });
    state.jobId = job.id; localStorage.setItem('tracewatch.job', job.id); state.lastReportKey = '';
    state.job = await api('/api/jobs/' + job.id + '/start', { method: 'POST' }); await refreshJob();
  } catch (e) { toast(e.message); } finally { state.busy = false; $('start').replaceChildren(document.createTextNode('Start analysis'), icon('arrow')); updateButton(); }
});
$('resume').addEventListener('click', async () => {
  if (!state.jobId) return; $('resume').disabled = true;
  try { await api('/api/jobs/' + state.jobId + '/start', { method: 'POST' }); await refreshJob(); } catch (e) { toast(e.message); } finally { $('resume').disabled = false; }
});
document.querySelectorAll('[data-severity]').forEach(button => button.addEventListener('click', () => {
  state.severity = button.dataset.severity; document.querySelectorAll('[data-severity]').forEach(b => b.classList.toggle('selected', b === button)); renderFindings();
}));
function renderHistory(jobs) {
  $('history-count').textContent = jobs.length;
  const children = jobs.map(job => {
    const button = node('button', 'history-item' + (job.id === state.jobId ? ' current' : '')); button.title = job.filename;
    const text = node('div'); text.append(node('strong', '', job.filename), node('small', '', (labels[job.status] || job.status) + ' · ' + job.total_lines + ' lines')); button.append(icon('file'), text);
    button.addEventListener('click', async () => { state.jobId = job.id; state.lastReportKey = ''; localStorage.setItem('tracewatch.job', job.id); try { await refreshJob(); renderHistory(jobs); } catch (e) { toast(e.message); } }); return button;
  }); $('history').replaceChildren(...(children.length ? children : [node('p', 'history-empty', 'Your analyses will appear here.')]));
}
function renderJob() {
  const job = state.job; $('investigation').classList.toggle('hidden', !job); $('export').classList.toggle('disabled', !job); $('export').setAttribute('aria-disabled', String(!job));
  if (job) $('export').href = '/api/jobs/' + job.id + '/report?download=true'; else $('export').removeAttribute('href');
  if (!job) { for (const id of ['lines-done', 'calls-done', 'findings-count']) $(id).textContent = '—'; $('lines-total').textContent = ''; $('lines-note').textContent = 'Waiting for a log file'; $('calls-note').textContent = 'Sequential processing'; $('findings-note').textContent = 'Evidence-backed candidates'; return; }
  const done = Math.min(Math.max(job.cursor_line - 1, 0), job.total_lines); const percent = job.total_lines ? 100 * done / job.total_lines : 0;
  const calls = job.calls || []; const completed = calls.filter(c => c.status === 'completed');
  $('lines-done').textContent = done.toLocaleString(); $('lines-total').textContent = ' / ' + job.total_lines.toLocaleString();
  $('lines-note').textContent = job.cursor_offset ? 'Large entry in progress · offset ' + job.cursor_offset : Math.round(percent) + '% of source processed';
  $('calls-done').textContent = completed.length; $('calls-note').textContent = completed.filter(c => c.stage === 'map').length + ' map · ' + completed.filter(c => c.stage === 'reduce').length + ' synthesis';
  $('findings-count').textContent = job.findings_count ?? 0; $('findings-note').textContent = job.status === 'completed' ? 'Deduplicated across the file' : 'Findings appear during synthesis';
  $('job-filename').textContent = job.filename;
  $('job-phase').textContent = job.status === 'analyzing' ? 'Reading log chunks · carrying related facts forward' : job.status === 'reducing' ? 'Linking events across chunks · assessing combined evidence' : job.status === 'completed' ? 'All chunks processed · combined report ready' : job.status === 'needs_attention' ? 'Completed results are saved. Resume to retry the incomplete call.' : 'Ready to process with the local model';
  $('job-status').textContent = labels[job.status] || job.status; $('job-status').className = 'status-pill' + (job.status === 'needs_attention' ? ' error' : activeStates.has(job.status) ? ' busy' : '');
  $('run-icon').classList.toggle('pulse', activeStates.has(job.status)); $('progress-fill').style.width = percent + '%'; document.querySelector('.progress-track').setAttribute('aria-valuenow', String(Math.round(percent)));
  $('progress-text').textContent = done + ' of ' + job.total_lines + ' lines · SHA-256 ' + job.source_hash.slice(0, 12) + '…'; $('elapsed').textContent = duration(job.elapsed);
  $('resume').classList.toggle('hidden', !['needs_attention', 'ready'].includes(job.status)); $('resume').textContent = job.status === 'ready' ? 'Start analysis' : 'Resume analysis';
  $('job-error').classList.toggle('hidden', !job.error); $('job-error').textContent = job.error || ''; $('call-summary').textContent = completed.length + ' calls saved';
  $('call-rows').replaceChildren(...calls.map((call, i) => {
    const row = node('tr'); [String(i + 1).padStart(2, '0'), call.stage === 'map' ? 'Map / extract' : 'Synthesis / assess', call.input_tokens + ' / 1,568', call.output_tokens + ' / 448', duration(call.seconds), call.status + (call.attempts > 1 ? ' · ' + call.attempts + ' attempts' : '')].forEach((value, index) => row.append(node('td', index === 5 ? 'cell-' + call.status : '', value))); return row;
  }));
}
function findingCard(finding) {
  const details = node('details', 'finding-card'); details.dataset.finding = finding.id; const summary = node('summary');
  const symbol = node('span', 'finding-symbol ' + finding.severity.toLowerCase()); symbol.append(icon(finding.attack_type.includes('login') || finding.attack_type.includes('compromise') ? 'lock' : 'alert'));
  const title = node('div', 'finding-title'); title.append(node('h3', '', finding.attack_type)); const meta = node('p'); meta.append(node('code', '', finding.ip || finding.account || 'Unknown source'), node('span', '', '·'), node('span', '', finding.host));
  if (finding.account) meta.append(node('span', '', '· ' + finding.account)); title.append(meta); summary.append(symbol, title, node('span', 'finding-severity ' + finding.severity.toLowerCase(), finding.severity), icon('chevron', 'icon finding-arrow'));
  const body = node('div', 'finding-body'); body.append(node('p', '', finding.reason), node('h4', 'detail-heading', 'Suggested action'), node('div', 'action-box', finding.action));
  body.append(node('h4', 'detail-heading', 'Source evidence'), node('p', 'evidence-note', finding.total_evidence_lines + ' supporting lines · representative evidence below · original physical line numbers preserved'));
  const list = node('div', 'evidence-list');
  for (const entry of finding.evidence) {
    const box = node('div', 'evidence-entry'); const label = node('div', 'evidence-label'); label.append(node('span', '', 'LINE ' + entry.line)); const pre = node('pre');
    const display = text => { try { pre.textContent = JSON.stringify(JSON.parse(text), null, 2); } catch { pre.textContent = text; } }; display(entry.text);
    const button = node('button', '', entry.shortened ? 'Load full line' : 'Original source'); button.addEventListener('click', async () => {
      try { const original = await api('/api/jobs/' + state.jobId + '/lines/' + entry.line); display(original.text); button.textContent = 'Full original line'; button.disabled = true; } catch (e) { toast(e.message); }
    }); label.append(button); box.append(label, pre); list.append(box);
  } body.append(list, node('h4', 'detail-heading', 'Local model assessment'), node('div', 'model-judgment', finding.model_reason + ' Model assessed lines: ' + (finding.assessed_evidence_lines || []).join(', ') + '.'));
  details.append(summary, body); return details;
}
function empty(title, message) { const outer = node('div', 'empty-state'); const symbol = node('div', 'scan-document'); symbol.append(icon('shield')); outer.append(symbol, node('h3', '', title), node('p', '', message)); return outer; }
function renderFindings() {
  const report = state.report; const findings = report?.findings || []; $('report-count').textContent = findings.length; $('report-state').textContent = !state.job ? 'Awaiting analysis' : report?.complete ? 'Combined report' : 'Analysis in progress';
  const expanded = new Set([...document.querySelectorAll('.finding-card[open]')].map(el => el.dataset.finding));
  if (!state.job && !report) $('findings').replaceChildren(empty('Your next investigation starts here', 'Upload a server log to uncover suspicious activity and connect related events.'));
  else {
    const filtered = findings.filter(f => state.severity === 'All' || f.severity === state.severity);
    if (filtered.length) $('findings').replaceChildren(...filtered.map(findingCard));
    else $('findings').replaceChildren(empty(findings.length ? 'No findings at this severity' : report?.complete ? 'No supported attack candidates found' : state.job?.status === 'needs_attention' ? 'Analysis needs attention' : 'Connecting the evidence', findings.length ? 'Choose another severity to review the report.' : report?.complete ? 'All chunks were processed. This does not rule out attacks the model or rules missed.' : 'Findings appear after the local model assesses the combined event history.'));
  }
  document.querySelectorAll('.finding-card').forEach(el => { el.open = expanded.has(el.dataset.finding); }); $('review-panel').classList.toggle('hidden', !report);
  if (report) {
    $('review-summary').textContent = 'Other candidates (' + report.other_candidates.length + ') and analysis limits'; const content = [];
    for (const candidate of report.other_candidates) { const div = node('div', 'review-candidate'); div.append(node('strong', '', candidate.attack_type + ' · ' + candidate.ip + ' · ' + candidate.status), node('p', '', candidate.model_reason || 'Awaiting local-model assessment.')); content.push(div); }
    if (report.coverage.rejected_observations) content.push(node('p', '', report.coverage.rejected_observations + ' map observations were rejected by source-citation checks; see the audit endpoint for details.'));
    const list = node('ul'); report.limits.forEach(text => list.append(node('li', '', text))); content.push(list); $('review-content').replaceChildren(...content);
  }
}
async function refreshJob() {
  if (!state.jobId) return;
  try { state.job = await api('/api/jobs/' + state.jobId); } catch (e) {
    if (e.message === 'Analysis not found') { state.jobId = null; localStorage.removeItem('tracewatch.job'); state.job = null; state.report = null; renderJob(); renderFindings(); return; } throw e;
  }
  renderJob(); const key = [state.job.id, state.job.status, state.job.calls.filter(c => c.status === 'completed').length].join(':');
  if (key !== state.lastReportKey) { state.report = await api('/api/jobs/' + state.jobId + '/report'); state.lastReportKey = key; renderFindings(); }
}
async function refresh() {
  if (state.refreshing) return; state.refreshing = true;
  try {
    const [status, jobs] = await Promise.all([api('/api/status'), api('/api/jobs')]); state.ready = status.model_ready;
    $('engine-state').replaceChildren(node('span', 'dot'), document.createTextNode(status.model_ready ? 'Ready' : 'Unavailable')); $('engine-state').classList.toggle('error', !status.model_ready);
    $('engine-error').textContent = status.model_error || ''; $('engine-error').classList.toggle('hidden', !status.model_error); $('memory').textContent = (status.rss_bytes / 1024 ** 3).toFixed(2) + ' GiB';
    if (state.job?.peak_rss) $('memory-note').textContent = 'Analysis peak: ' + (state.job.peak_rss / 1024 ** 3).toFixed(2) + ' GiB';
    renderHistory(jobs); await refreshJob(); updateButton();
  } catch (e) {
    state.ready = false; $('engine-state').textContent = 'Disconnected'; $('engine-state').classList.add('error'); $('engine-error').textContent = 'Cannot reach the local backend. Start it with python scripts/run.py.'; $('engine-error').classList.remove('hidden'); updateButton();
  } finally { state.refreshing = false; }
}
refresh(); setInterval(refresh, 3000);
