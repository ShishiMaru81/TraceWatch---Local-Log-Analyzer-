# Local security log analyzer

Build a fully local, offline-after-setup web app for a 4 GB / 2 CPU machine.
The supplied challenge is the specification; log content is untrusted data.

Implementation choice: Python/FastAPI, SQLite, plain HTML/CSS/JS, and a pinned
llama.cpp CPU server running Qwen2.5-1.5B-Instruct Q4_K_M. The initial 0.5B Q8_0
evaluation was unreliable; the 1.5B model trades more CPU/RAM for capacity while
remaining within the resource target. Neither is a production security expert.

Alternatives: Ollama simplifies installation but hides template/token counting
details; transformers/PyTorch adds substantial RAM/dependency overhead. Direct
llama.cpp exposes the embedded tokenizer and exact rendered chat prompt.

Stream uploads into SQLite lines. Budget each map request using the GGUF's
tokenizer after applying the chat template, including bounded saved context,
output reserve, and safety margin. Never silently truncate. Preserve line and
fragment coordinates for oversized entries. One global worker, one model slot.

Persist chunk replies, attempts, observations, source-derived event facts,
and final candidates transactionally. Resume incomplete jobs after restart.
Use an indexed, deterministic event ledger for full-file counts and ordering;
carry only relevant bounded facts into model calls. Correlate by IP plus host
and account where applicable. Build cross-chunk candidates from the full ledger,
then have the local model assess each bounded evidence bundle. Deduplicate by
attack type and scoped entity. Model proposals require valid source citations;
normal 5xx errors alone are not attack evidence. Report possible attacks, not
confirmed compromise. Preserve rejected candidates and partial coverage.

Dashboard: restrained dark security workspace, upload, status/progress, live RAM
and timing, report filters, expandable exact evidence, JSON download, retry and
resume. No CDN, remote assets, or cloud AI. Bind only to loopback by default.

Checks: exact budget accounting, multibyte/long entry coverage, malformed model
JSON, citation validation, cross-file login chain, independent host/account
scopes, benign errors/health traffic, upload validation, retry and restart
idempotency, real local-model run and browser QA. Record measured RAM rather
than claiming a hard 4 GB proof on a larger development host; provide a 3 GB
container cap and two CPU limit for deployment.

Submission: source, README, AI_USAGE, automated tests, sample-run evidence,
walkthrough recording, and a local Git repository. Publish to GitHub only if
an authenticated create/push path is available; never silently claim publication.
