# Implementation ledger

Plan: docs/superpowers/plans/2026-11-07-log-analyzer.md

- Workspace inspection: only supplied 94,398-byte log, no existing Git repo or
  AGENTS.md. Source SHA256 2f81f924c06fe8ed848cd51df31c86c914a514a3233c4f11eb2986dbc3d8bd45.
- Memory search: no relevant project history found.
- Ruling: use the supplied detailed challenge as authorized design and execute
  with sensible stack defaults; no additional design approval gate.
- Ruling: work directly in the empty requested workspace; no existing branch
  needs isolation. Initialize a submission repository at the end.
- Preflight: model interface provides prepare(messages)->token IDs and
  complete(token IDs, schema)->validated response; chunking and worker share it.
  Event ledger is source-derived and persists independently of LLM context.

- Task 1: core tokenizer budget, Unicode fragmentation, source validation and
  scoped correlation implemented. Original eight tests failed on missing modules
  before implementation and passed after it.
- Task 2: SQLite checkpoints, attempts/audit, retries, source ingestion, HTTP API,
  single worker/model ownership and setup implemented. Full suite: 22 passed
  (`python -m pytest tests -q`, 4.75s, final run before documentation/video).
- Ruling: raw-body file upload avoids multipart buffering/dependency overhead;
  the dashboard streams the File object directly with its validated filename.
- Task 3: responsive static dashboard, source evidence, severity filters, JSON
  export, live RSS/timing and resume controls implemented. `node --check` passed;
  all literal JavaScript element IDs exist in the HTML.
- Browser QA blocked: CUA localhost navigation denied by origin approval gate.
  No alternate browser mechanism used. Preview was requested in the app, but
  interaction/screenshot verification is not claimed.
- Baseline real run: 0.5B Q8_0, prompt v3, 258 lines, 34 map + 4 reduce calls,
  505.66s, peak sampled combined RSS 726032384 bytes. All final candidates
  rejected; 633 map proposals failed source corroboration. Preserved this
  negative evaluation rather than calling it a clean security report.
- Ruling: upgrade to official 1.5B Q4_K_M; narrow map schema and use type-specific
  final rubrics (prompt v4). Exact hashes pinned in model_config.json.
- Review: independent reviewer reproduced lost syslog host scope, qualifying
  burst hidden by a larger ordinary burst, queue starvation beyond 40 jobs,
  numeric syslog host confused with client IP, and out-of-order timestamp success
  selection. All fixed with regressions observed failing then passing.
- Additional fixes: preserve original exception on retry exhaustion; move fitting
  multiline entries together; deduplicate reliable event/request IDs; bound
  earlier model observations in combined assessment; fingerprint model/prompts.
- Real restart verification: after 13 completed 1.5B calls, restarted backend.
  Completed calls retained; pending call 52 completed, cursor advanced to line
  109, model processing continued. A second restart retained 25 completed calls.
- Submission destination explicitly supplied by user:
  https://github.com/ShishiMaru81/TraceWatch---Local-Log-Analyzer-
  Existing remote had no refs. Use user's existing Git identity; do not change
  collaborator settings or add co-author trailers.
- Final real run: completed 258/258 lines, 34 map + 5 reduce calls, zero failed
  or incomplete calls, zero coverage gaps/overlaps. Max reserved total 2047/2048;
  actual input+output maximum 1616. Peak combined RSS 1846427648 bytes (1.72 GiB).
  Recorded active time 1113.68s, excluding downtime/uncommitted interrupted calls.
- Final model accepted five source-corroborated candidates, including 12 scoped
  login failures followed by success at line 196. SQL duplicate event removed:
  four unique payload requests across early and late chunks. Final local model
  still produced 148 rejected map observations; retained, not hidden.
- Real HTTP export/evidence verification: complete=true, 258/258 source coverage,
  39 completed calls, source snippets match exact original line endpoints,
  report Content-Disposition and CSP present, dashboard assets all HTTP 200.
- Task 4: README, AI_USAGE, CI workflow, pinned setup, verification audit, and
  198.48s narrated architecture/code walkthrough complete. Video has H.264/AAC
  streams, 1600x900 frame size, and passes full ffmpeg decode. Intro/results
  frames visually inspected; this is not a browser recording.

## Extended video requested by user

- Created an 11m29s English full guide, 1920x1080 at 25fps, with 21 chapters and
  109 burned-in caption segments. Narration uses offline Windows System.Speech.
- Added standalone speech MP3, SRT, complete transcript, and chapter timestamps.
  Each caption is timed to its own synthesized speech segment's actual duration.
- Visuals include setup/use instructions, actual findings, cross-part timeline,
  architecture, token budget, source excerpts, failure recovery, mistakes and
  limits. They explicitly identify themselves as illustrations/saved evidence;
  no browser capture or alternative browser automation was performed.
- Preview generation checked all scene/caption bounds. Selected workflow,
  findings, architecture, budget, timeline, code and closing frames were viewed.
- No analyzer behavior or model results changed for this media-only addition.
