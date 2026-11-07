# Tracewatch

A local AI security log analyzer for a 4 GB, two CPU machine. Upload a `.log`
or `.txt` file, watch sequential model calls, and review one deduplicated report
with original line evidence. No cloud AI, telemetry, CDN, or remote assets.

## Run locally

Requires Windows x64 or Linux x64 and Python 3.12+. Setup needs internet; normal
operation does not. About 2 GB of free disk is needed for the model, runtime,
and environment. Use a recent x64 CPU supported by the official CPU binary.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup.py
.\.venv\Scripts\python.exe scripts/run.py
```

Linux:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/setup.py
.venv/bin/python scripts/run.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Choose a UTF-8 log, then
**Start analysis**. The backend starts its own model server on loopback port
8091. Keep exactly one backend process. Do not use `--reload` or multiple
Uvicorn workers: they would each try to own a model.

If startup fails, inspect `runtime/model.stderr.log`. Ports 8000 and 8091 must
be free. Setup verifies downloads against pinned SHA-256 hashes and is safe
to repeat. It never runs during analysis. The provided challenge log is kept
unchanged locally and excluded from Git; upload your own copy.

## Local model and resource limits

- **Qwen2.5-1.5B-Instruct, Q4_K_M GGUF**, 1,117,320,736 bytes, Apache 2.0.
- Official model: [Qwen model repository](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF).
- Exact revision, filename and hash: [`model_config.json`](model_config.json).
- **llama.cpp b12182**, official CPU binary with pinned archive hashes in
  `scripts/setup.py`. [Runtime documentation](https://github.com/ggml-org/llama.cpp/tree/b12182/tools/server).
- 2 generation threads, 2 batch threads, 0 GPU layers, 1 inference slot,
  2,048-token context, 128-token batch/microbatch, context shifting disabled.
- One global analysis worker handles the FIFO job queue. Multiple uploaded
  jobs share that worker and never load additional models.
- A 3 GiB combined-RSS guard pauses jobs before the next map call. The UI shows
  live backend + owned-model RSS and a sampled analysis peak. RSS is not total
  system memory and the guard is not an OS-enforced allocation limit.

For an enforced service cap, the optional Docker configuration uses **3 GiB**
and **2 CPUs**, leaving roughly 1 GB of the challenge machine for its OS. Build
online, then start with its internal network, which has no external route:

```sh
docker compose build
docker compose up -d
docker compose logs -f analyzer
```

Docker deployment is provided but was not exercised in this Windows session.
Native inference was measured; see [`artifacts/verification.json`](artifacts/verification.json)
for the actual run, limitations and token/coverage audit. A full 4 GB VM/cgroup
stress test has not been performed. Timings depend on CPU and disk.

## How a file becomes one report

```text
stream upload -> SQLite source lines + event ledger
                       |
             exact-token chunk packer
                       |
          local map call -> validate citations -> checkpoint
                       |                |
                       +-- bounded prior facts --+ (next chunk)
                       |
       full-file event correlation + validated map observations
                       |
          local candidate assessment calls -> merged report
```

1. **Stream ingestion.** The HTTP request body is streamed directly into a
   line table. The browser sends the file without reading a second string
   copy. The backend validates UTF-8 incrementally and computes the original
   file's SHA-256. Limits: 5 MiB, 30,000 physical lines, 256 Ki characters per
   physical line. Binary/control bytes, invalid extensions and empty files
   fail clearly. CRLF is normalized for display; source line numbers remain
   1-based. The hash covers the original uploaded bytes.
2. **Chunking.** Whole physical lines are packed where possible. Indented
   stack-trace continuations move with their parent entry when they fit.
   Oversized entries split first at line boundaries, then at Unicode-safe
   character boundaries. Each fragment retains its physical line and character
   offset. Nothing is silently dropped; verification checks every coordinate.
3. **Exact budget.** llama.cpp applies the GGUF chat template, then the model's
   embedded tokenizer counts that rendered prompt. The completion endpoint
   receives those **same token IDs**, avoiding a second, different template.

   ```text
   rendered prompt + source + saved facts <= 1,568 tokens
   maximum generated JSON                 =   448 tokens
   unused safety margin                   =    32 tokens
   total ceiling                          = 2,048 tokens
   ```

   Up to 160 tokens of relevant prior facts are included within the 1,568,
   not added on top. The remaining source budget is measured dynamically.
   A final candidate call follows the same calculation and must include
   early and late evidence. Inference is refused when the budget cannot fit.
4. **Map calls.** The model extracts potential security observations. Replies
   use a constrained JSON schema. Every observation must cite a line actually
   present in that call and pass a conservative source-signal check. Invented
   or mismatched citations are rejected and retained in the audit.
5. **Durable memory.** All source event facts and validated map observations
   stay in SQLite; they are never compressed into a lossy model summary. Only
   relevant, bounded facts from earlier lines enter the next prompt. The full
   event ledger remains available for final correlation even when the context
   cannot hold all identities.
6. **Combination.** The ledger correlates authentication by IP, host and account,
   with source order and timestamps checked. Five failures followed by explicit
   success becomes one possible-compromise candidate instead of separate chunk
   reports. Reliable event/request IDs deduplicate identical event facts. The
   final model sees aggregate counts, early/middle/late evidence, and validated
   map observations. Only locally supported candidates enter the main report;
   rejected/pending candidates remain visible separately. Each finding has an
   attack type, severity, identity, reason, action and exact source references.

This is deliberately a **hybrid** analyzer. Source parsing, thresholds and
correlation are deterministic; extraction and final candidate assessment use
the downloaded model. A model observation alone does not establish an attack.
The model does not invent new supported attack categories outside the current
rules. This favors auditable known patterns over open-ended detection.

## Detection policy

- Repeated login attempts: at least five failures per IP/host/account.
- Possible account compromise: at least five temporally prior failures then an
  explicit authentication success in that scope. It is not confirmed takeover.
- SQL injection attempts: recognizable request payloads after up to two URL
  decodes. A blocked request still supports an attempt; execution is unproven.
- Scanning: at least three distinct sensitive/probe paths in one IP/host scope.
- Unauthorized access: at least three non-login HTTP 401/403 responses; not a
  successful authorization bypass.
- Unusual rate: 30 requests in 60 seconds, or 10 in five seconds accompanied by
  at least three HTTP 429 responses. Successful health endpoints are excluded.

High is used for the correlated possible-compromise chain; current other rules
use Medium. The report schema supports Low, Medium, High and Critical, but the
app does not escalate severity without stronger evidence. Thresholds live in
`app/detection.py`; they are policy choices, not learned baselines.

## Reliability and security boundaries

- Exact request payloads are saved before inference. After each successful call,
  its reply, observations and cursor commit in one SQLite transaction.
- Timeouts, transport errors, invalid schemas, invalid JSON and token-limited
  replies retry up to three times, with 2s/4s backoff. No fabricated JSON repair.
  A complete JSON code fence is accepted; truncated JSON is not.
- Retry exhaustion marks **Needs attention**. Completed calls and findings stay
  saved; **Resume analysis** retries the same incomplete call. Restart recovery
  automatically requeues interrupted jobs. A model/prompt fingerprint prevents
  resuming saved token IDs under a changed model or prompt.
- Source facts can be reindexed from immutable source lines when the fact schema
  changes. This does not discard completed map calls.
- Log strings are untrusted: no tools, shell, command execution or outbound
  requests are exposed to the model. Prompt data is JSON-encoded; literal ChatML
  delimiters are escaped. UI evidence uses `textContent`, never HTML injection.
- Loopback binding, origin-write checks, trusted Host checks, CSP, no remote
  assets. This is a single-user local tool, without authentication or encryption
  at rest. Do not expose it directly to a shared network. SQLite contains raw
  logs and model replies; protect the local data directory.

## API and diagnostics

| Route | Purpose |
| --- | --- |
| `POST /api/jobs?filename=x.log` | Raw streamed file body; returns a job ID |
| `POST /api/jobs/{id}/start` | Start or resume an analysis |
| `GET /api/jobs/{id}` | Progress and per-call timing/token counts |
| `GET /api/jobs/{id}/report` | One combined JSON report, including coverage |
| `GET /api/jobs/{id}/audit` | Saved payloads, raw replies, rejected observations and attempts |
| `GET /api/jobs/{id}/lines/{n}` | Full original physical line |
| `GET /api/status` | Model readiness and combined RSS |

CLI alternative, with live line/call counts:

```powershell
python scripts/analyze_file.py .\your-server.log --output artifacts\report.json
```

For model progress in another PowerShell terminal:

```powershell
Get-Content -LiteralPath .\runtime\model.stderr.log -Tail 20 -Wait
```

## Verification and submission

The supplied sample completed **258/258 lines**, **34 map calls + 5 synthesis
calls**, and **5 merged findings**. Peak sampled backend + model RSS was **1.72
GiB**. The largest input + reserved output + safety margin was **2,047/2,048
tokens**; the source audit found no gaps/overlaps. Recorded active analysis time
was about **18.6 minutes**, excluding downtime and uncommitted interrupted calls.
The full automated suite passed **22 tests**. These describe this sample run,
not general detection accuracy or a full-machine memory guarantee.

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
node --check static/app.js
python scripts/verify_run.py
```

Tests use explicitly labeled fake model clients to inject failures; production
has no mock AI mode. The real-run audit verifies source coverage with no gaps or
overlaps, every actual call budget, rejected observations, findings and sampled
RAM. `scripts/analyze_file.py` runs real inference through the HTTP API.

- [`AI_USAGE.md`](AI_USAGE.md): coding assistance, exact prompt locations,
  revisions, budget plan, real mistakes and corrections.
- [`artifacts/walkthrough.mp4`](artifacts/walkthrough.mp4): short narrated code
  and architecture walkthrough, not a claimed browser recording.
- [`docs/progress.md`](docs/progress.md): implementation and review record.

To regenerate the optional video on Windows, install Pillow (`pip install
Pillow`) and ffmpeg, then run `python scripts/make_walkthrough.py` after a complete
verified analysis. Narration uses the local Windows System.Speech voice.

Known limits: small-model false positives/negatives; rules miss novel attacks;
only common JSON/access/SSH formats are parsed; missing host/account data reduces
correlation precision; no trained traffic baseline; a five-failure threshold has
no fixed time horizon; large fields may be shortened in model evidence views
(full source is retained); arbitrary multiline records are only heuristically
grouped; no independent ground-truth accuracy benchmark. Interactive browser
QA was blocked by the localhost permission gate and remains unverified.
