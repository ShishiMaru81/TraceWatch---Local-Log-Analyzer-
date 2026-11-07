# Local Security Log Analyzer Implementation Plan

> Execute inline using the executing-plans and test-driven-development skills.

**Goal:** An offline local-model analyzer that produces one cited report.
**Architecture:** FastAPI streams source into SQLite; one durable worker uses
llama.cpp for budgeted map calls and final candidate judgments. SQLite retains
full event history, calls, and findings. Static dashboard polls job state.
**Tech stack:** Python 3.12+, FastAPI, httpx, SQLite, psutil, llama.cpp, vanilla JS.
**Spec:** docs/superpowers/specs/2026-11-07-log-analyzer-design.md

## Global constraints
- 2,048 total tokens per call, actual local model tokenizer, output reserved.
- 4 GB total server resource target; 2 model threads; one concurrent inference.
- Local model only. No commands/tools from log text. No hardcoded findings.
- Preserve original evidence, line numbers, completed calls, and failures.

## Review focus
- Oversized Unicode/multiline entries must retain complete coverage.
- Failed/truncated responses must not turn into a successful clean report.
- Same IP on different hosts/accounts must not create false login chains.
- Partial model coverage must be visible after retry exhaustion/restart.
- Benign errors/health checks must not become confirmed attacks.

## Task 1: Token budget, evidence, and correlation
- [ ] Write failing tests in tests/test_core.py and run them.
- [ ] Implement app/prompts.py, app/model.py, app/chunking.py, app/detection.py.
- [ ] Verify coverage, tokenizer budgeting, JSON validation, scoped correlation.

## Task 2: Durable worker and HTTP API
- [ ] Write failure/restart/upload tests in tests/test_service.py and run them.
- [ ] Implement app/store.py, app/worker.py, app/main.py; scripts/setup.py,
  scripts/run.py, requirements.txt, Dockerfile, compose.yaml.
- [ ] Verify persisted results, retries, JSON audit records, invalid uploads.

## Task 3: Dashboard and real local inference
- [ ] Implement static/index.html, static/app.js, static/style.css.
- [ ] Download hash-verified model/runtime, run model and analyze supplied log.
- [ ] Verify browser upload/progress/report, resource metrics, full-file links.

## Task 4: Submission and review
- [ ] README.md, AI_USAGE.md, walkthrough video, artifacts verification report.
- [ ] Review whole implementation; run full suite and real integration checks.
- [ ] Prepare Git source repository, publish if authenticated tooling permits.
