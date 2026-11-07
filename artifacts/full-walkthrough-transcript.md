# Tracewatch complete narrated guide

English synthetic narration using Windows System.Speech. Visuals are illustrations, saved evidence and code; no live browser recording.

## 00:00:00.000 - Tracewatch: the complete guide

Welcome to this complete guide to Tracewatch, a local AI security log analyzer. This video explains how to set it up, use it, interpret its findings, and understand the implementation. You will also see the measured results, the model mistakes that were corrected, and the remaining limitations. The visuals are workflow illustrations, code excerpts, and saved evidence, rather than a live browser recording.

## 00:00:29.123 - What the challenge requires

The application must work on a machine with four gigabytes of total memory, two virtual CPU cores, and no GPU. The log is larger than the model can read in one call. Every call has a strict two thousand and forty eight token budget, including the prompt, saved context, log text, and answer. After setup, runtime analysis must work without cloud AI services.

## 00:00:56.082 - One-time setup

Start by opening PowerShell in the project folder. Create a Python virtual environment and install the requirements using the commands on screen. Then run the setup script while connected to the internet. It downloads the pinned CPU runtime and model weights, and checks their SHA two fifty six hashes. This download is needed only during setup, not each time you analyze a log.

## 00:01:22.444 - Launch the application

For everyday use, open PowerShell, change to the project folder, and run the launch script. Use the same Python environment that you used during setup. The backend starts one local model server automatically. Open the localhost address shown on screen, and wait until the engine reports Ready. Keep the terminal running while using the application, and avoid launching a second backend.

## 00:01:50.077 - Upload, analyze, review, export

Choose a dot log or dot text file using the upload area, or drag a file onto it. The file must be nonempty UTF eight text and no larger than five mebibytes. Click Start analysis once the local engine is ready. After processing, expand each finding to inspect the evidence and suggested action. Export report downloads the combined result as JSON. Recent analyses lets you reopen saved results without repeating inference.

## 00:02:21.623 - Understand the progress display

Lines processed shows source coverage, while local AI calls shows completed extraction and synthesis calls. Potential findings are added during the final assessment phase, so an early zero does not mean the file is safe. Processing details exposes token counts, call duration, status, and retries. The memory indicator measures the backend and its owned model process. If a call fails repeatedly, the application preserves completed work and offers Resume analysis.

## 00:02:54.635 - The measured sample result

The supplied sample contained 258 physical lines. The completed run used 34 map calls and 5 final assessment calls. It produced 5 merged findings, with no failed calls and no source coverage gaps or overlaps. Peak sampled combined resident memory was 1.72 gibibytes. Recorded active analysis time was about nineteen minutes, excluding downtime and uncommitted interrupted calls. These are measurements of this sample, not an accuracy benchmark.

## 00:03:29.416 - Read the findings carefully

The report includes a possible account compromise, SQL injection attempts, endpoint scanning, repeated denied access, and an unusual request burst. Each finding includes its severity, source identity, reason, suggested action, and original line references. Possible compromise does not mean confirmed account takeover. Likewise, a suspicious SQL payload is evidence of an attempt, not proof that a database executed it. Human review remains necessary before taking action.

## 00:04:04.397 - Follow a chain across the file

The most important example is the authentication chain. The same source IP, host, and account have failed login events near the beginning and throughout the middle of the file. There are twelve failures before an explicit successful login at line one hundred and ninety six. The application combines these into one high severity possible compromise finding. It does not create separate reports that forget the earlier evidence between chunks.

## 00:04:33.154 - Separate attacks from normal failures

Detection uses conservative, source-backed policies. Five failed logins can support repeated authentication attempts. SQL payload syntax, several sensitive-path probes, or repeated non-login authorization denials can support other candidates. A short request burst needs both a high count and repeated rate-limit responses under its short-window rule. A database timeout, a deployment error, or a successful health check alone is not treated as a confirmed attack.

## 00:05:06.141 - The end-to-end architecture

FastAPI receives the upload as a stream and writes numbered source lines into SQLite. A conservative parser builds an event ledger from the source. The packer prepares bounded chunks for the local model. Model observations are checked against their cited source lines and saved after each successful call. Finally, full-file correlation creates candidates, and the local model assesses combined evidence before the main report is produced.

## 00:05:35.928 - Why this local model?

The final model is Qwen two point five, one point five billion parameters, in Q four K M quantization. The weights occupy about one point one two gigabytes on disk. Llama dot C P P runs the model with two generation threads, two batch threads, no GPU layers, and one inference slot. One global worker serves the job queue, avoiding several model copies in memory. Model storage size and actual process memory are different measurements.

## 00:06:08.874 - Account for every token

The input ceiling is one thousand five hundred and sixty eight tokens. That includes the rendered chat template, instructions, source fragments, and saved facts. Four hundred and forty eight tokens are reserved for the model response, and thirty two tokens remain as a safety margin. Relevant prior facts can use up to one hundred and sixty tokens inside the input budget. The source space is measured dynamically; it is never estimated using a fixed characters-per-token ratio.

## 00:06:41.686 - Use the exact tokenizer and prompt

This excerpt shows the important boundary between budgeting and inference. The backend asks the local server to apply the model chat template, then tokenizes the rendered prompt using the tokenizer embedded in the model. It sends those exact token IDs to the completion endpoint. This avoids counting one prompt and accidentally submitting a different template. The backend checks the budget before inference and rejects responses that report truncation or reach the generation limit.

## 00:07:12.607 - Split without losing source coordinates

The chunk packer prefers complete physical lines. It also tries to move indented multiline continuations with their parent entry when that entry can fit in a new chunk. An oversized line is divided into Unicode-safe character fragments. Every fragment keeps its original physical line number and character offset. The audit reconstructs coverage and compares every fragment to its source, so dropped text and overlapping coordinates can be detected.

## 00:07:42.564 - Keep more history than the prompt can hold

The context window is small, but the investigation history is not limited to that window. SQLite retains the full event ledger and validated model observations. Only a bounded selection of relevant earlier facts enters a later chunk prompt. Final correlation uses the complete ledger and scopes authentication by IP, host, and account. The final model receives aggregate counts and representative early, middle, and late evidence, rather than a lossy summary of earlier summaries.

## 00:08:15.475 - Make failures recoverable

Each request is saved before inference. After success, the model reply, validated observations, and source checkpoint commit together. Timeouts, invalid JSON, invalid schemas, and incomplete replies retry up to three times. Retry exhaustion marks the job as needing attention, while completed work remains saved. A real restart test retained thirteen completed model calls and continued the pending call. A model and prompt fingerprint prevents unsafe reuse of saved token IDs after a configuration change.

## 00:08:52.900 - Treat logs as data, never instructions

The sample includes submitted text asking the analyzer to report everything as safe and remove failed-login evidence. That text remains untrusted log data. The model has no tools or command execution interface, and literal chat-control delimiters are escaped in prompt data. The interface displays source text using text content, not interpreted HTML. These boundaries reduce exposure, but they are not a proof that a small language model can never be influenced semantically.

## 00:09:25.650 - What AI got wrong, and what changed

The initial half-billion-parameter model made unsupported line claims and confused attack types in its final assessment. For example, it discussed login events while assessing SQL injection. Source checks rejected unsupported citations rather than turning them into findings. The implementation moved to the larger quantized model, clearer observation definitions, and attack-specific assessment criteria. The final sample still had 148 rejected map proposals. Those failures remain visible in the audit instead of being hidden.

## 00:10:03.005 - Verification and an interview change

The automated suite passed 22 tests, and the published commit also passed GitHub continuous integration. Tests cover token limits, Unicode fragments, invalid uploads, broken JSON, retries, restart behavior, duplicate events, and host-safe correlation. A separate audit checks real source coverage and actual call budgets. For a small interview change, a detection threshold can be edited in the policy module, paired with a meaningful regression test, and verified by running the suite. This video does not claim to demonstrate an unperformed live code change.

## 00:10:44.095 - Limits and the next steps

Tracewatch is an auditable hybrid of local model analysis and conservative rules, not a complete security monitoring system. Novel attacks and unsupported log formats can be missed, and threshold choices need operational context. The memory result is sampled process memory, not proof from a complete four-gigabyte virtual machine stress test. Docker resource limits and browser interaction remain unverified. The repository includes source, setup instructions, AI usage notes, tests, measured evidence, and both walkthrough videos. Start with the README, launch the app, and reopen the saved sample under Recent analyses.
