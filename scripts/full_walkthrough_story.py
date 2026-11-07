"""Narrative and visual plan for the extended, evidence-based project guide."""


def build_story(summary, test_count):
    ram = summary['peak_backend_and_model_rss_bytes']/1024**3
    accepted = [f for f in summary['findings'] if f['status']=='accepted']
    total_calls = summary['map_calls']+summary['reduce_calls']
    return [
        dict(title='Tracewatch: the complete guide', section='Introduction', kind='intro',
             narration='Welcome to this complete guide to Tracewatch, a local AI security log analyzer. '
             'This video explains how to set it up, use it, interpret its findings, and understand the implementation. '
             'You will also see the measured results, the model mistakes that were corrected, and the remaining limitations. '
             'The visuals are workflow illustrations, code excerpts, and saved evidence, rather than a live browser recording.'),
        dict(title='What the challenge requires', section='Constraints', kind='constraints',
             narration='The application must work on a machine with four gigabytes of total memory, two virtual CPU cores, and no GPU. '
             'The log is larger than the model can read in one call. '
             'Every call has a strict two thousand and forty eight token budget, including the prompt, saved context, log text, and answer. '
             'After setup, runtime analysis must work without cloud AI services.'),
        dict(title='One-time setup', section='Getting started', kind='setup',
             narration='Start by opening PowerShell in the project folder. '
             'Create a Python virtual environment and install the requirements using the commands on screen. '
             'Then run the setup script while connected to the internet. '
             'It downloads the pinned CPU runtime and model weights, and checks their SHA two fifty six hashes. '
             'This download is needed only during setup, not each time you analyze a log.'),
        dict(title='Launch the application', section='Getting started', kind='launch',
             narration='For everyday use, open PowerShell, change to the project folder, and run the launch script. '
             'Use the same Python environment that you used during setup. '
             'The backend starts one local model server automatically. '
             'Open the localhost address shown on screen, and wait until the engine reports Ready. '
             'Keep the terminal running while using the application, and avoid launching a second backend.'),
        dict(title='Upload, analyze, review, export', section='Using the app', kind='workflow',
             narration='Choose a dot log or dot text file using the upload area, or drag a file onto it. '
             'The file must be nonempty UTF eight text and no larger than five mebibytes. '
             'Click Start analysis once the local engine is ready. '
             'After processing, expand each finding to inspect the evidence and suggested action. '
             'Export report downloads the combined result as JSON. '
             'Recent analyses lets you reopen saved results without repeating inference.'),
        dict(title='Understand the progress display', section='Using the app', kind='progress',
             narration='Lines processed shows source coverage, while local AI calls shows completed extraction and synthesis calls. '
             'Potential findings are added during the final assessment phase, so an early zero does not mean the file is safe. '
             'Processing details exposes token counts, call duration, status, and retries. '
             'The memory indicator measures the backend and its owned model process. '
             'If a call fails repeatedly, the application preserves completed work and offers Resume analysis.'),
        dict(title='The measured sample result', section='Actual evidence', kind='results',
             narration=f'The supplied sample contained {summary["total_lines"]} physical lines. '
             f'The completed run used {summary["map_calls"]} map calls and {summary["reduce_calls"]} final assessment calls. '
             f'It produced {len(accepted)} merged findings, with no failed calls and no source coverage gaps or overlaps. '
             f'Peak sampled combined resident memory was {ram:.2f} gibibytes. '
             'Recorded active analysis time was about nineteen minutes, excluding downtime and uncommitted interrupted calls. '
             'These are measurements of this sample, not an accuracy benchmark.'),
        dict(title='Read the findings carefully', section='Actual evidence', kind='findings',
             narration='The report includes a possible account compromise, SQL injection attempts, endpoint scanning, repeated denied access, and an unusual request burst. '
             'Each finding includes its severity, source identity, reason, suggested action, and original line references. '
             'Possible compromise does not mean confirmed account takeover. '
             'Likewise, a suspicious SQL payload is evidence of an attempt, not proof that a database executed it. '
             'Human review remains necessary before taking action.'),
        dict(title='Follow a chain across the file', section='Correlation', kind='timeline',
             narration='The most important example is the authentication chain. '
             'The same source IP, host, and account have failed login events near the beginning and throughout the middle of the file. '
             'There are twelve failures before an explicit successful login at line one hundred and ninety six. '
             'The application combines these into one high severity possible compromise finding. '
             'It does not create separate reports that forget the earlier evidence between chunks.'),
        dict(title='Separate attacks from normal failures', section='Detection policy', kind='policy',
             narration='Detection uses conservative, source-backed policies. '
             'Five failed logins can support repeated authentication attempts. '
             'SQL payload syntax, several sensitive-path probes, or repeated non-login authorization denials can support other candidates. '
             'A short request burst needs both a high count and repeated rate-limit responses under its short-window rule. '
             'A database timeout, a deployment error, or a successful health check alone is not treated as a confirmed attack.'),
        dict(title='The end-to-end architecture', section='Inside the backend', kind='architecture',
             narration='FastAPI receives the upload as a stream and writes numbered source lines into SQLite. '
             'A conservative parser builds an event ledger from the source. '
             'The packer prepares bounded chunks for the local model. '
             'Model observations are checked against their cited source lines and saved after each successful call. '
             'Finally, full-file correlation creates candidates, and the local model assesses combined evidence before the main report is produced.'),
        dict(title='Why this local model?', section='Local inference', kind='model',
             narration='The final model is Qwen two point five, one point five billion parameters, in Q four K M quantization. '
             'The weights occupy about one point one two gigabytes on disk. '
             'Llama dot C P P runs the model with two generation threads, two batch threads, no GPU layers, and one inference slot. '
             'One global worker serves the job queue, avoiding several model copies in memory. '
             'Model storage size and actual process memory are different measurements.'),
        dict(title='Account for every token', section='The context limit', kind='budget',
             narration='The input ceiling is one thousand five hundred and sixty eight tokens. '
             'That includes the rendered chat template, instructions, source fragments, and saved facts. '
             'Four hundred and forty eight tokens are reserved for the model response, and thirty two tokens remain as a safety margin. '
             'Relevant prior facts can use up to one hundred and sixty tokens inside the input budget. '
             'The source space is measured dynamically; it is never estimated using a fixed characters-per-token ratio.'),
        dict(title='Use the exact tokenizer and prompt', section='Code walkthrough', kind='code_model',
             narration='This excerpt shows the important boundary between budgeting and inference. '
             'The backend asks the local server to apply the model chat template, then tokenizes the rendered prompt using the tokenizer embedded in the model. '
             'It sends those exact token IDs to the completion endpoint. '
             'This avoids counting one prompt and accidentally submitting a different template. '
             'The backend checks the budget before inference and rejects responses that report truncation or reach the generation limit.'),
        dict(title='Split without losing source coordinates', section='Code walkthrough', kind='chunking',
             narration='The chunk packer prefers complete physical lines. '
             'It also tries to move indented multiline continuations with their parent entry when that entry can fit in a new chunk. '
             'An oversized line is divided into Unicode-safe character fragments. '
             'Every fragment keeps its original physical line number and character offset. '
             'The audit reconstructs coverage and compares every fragment to its source, so dropped text and overlapping coordinates can be detected.'),
        dict(title='Keep more history than the prompt can hold', section='Cross-part memory', kind='memory',
             narration='The context window is small, but the investigation history is not limited to that window. '
             'SQLite retains the full event ledger and validated model observations. '
             'Only a bounded selection of relevant earlier facts enters a later chunk prompt. '
             'Final correlation uses the complete ledger and scopes authentication by IP, host, and account. '
             'The final model receives aggregate counts and representative early, middle, and late evidence, rather than a lossy summary of earlier summaries.'),
        dict(title='Make failures recoverable', section='Reliability', kind='recovery',
             narration='Each request is saved before inference. '
             'After success, the model reply, validated observations, and source checkpoint commit together. '
             'Timeouts, invalid JSON, invalid schemas, and incomplete replies retry up to three times. '
             'Retry exhaustion marks the job as needing attention, while completed work remains saved. '
             'A real restart test retained thirteen completed model calls and continued the pending call. '
             'A model and prompt fingerprint prevents unsafe reuse of saved token IDs after a configuration change.'),
        dict(title='Treat logs as data, never instructions', section='Security boundaries', kind='injection',
             narration='The sample includes submitted text asking the analyzer to report everything as safe and remove failed-login evidence. '
             'That text remains untrusted log data. '
             'The model has no tools or command execution interface, and literal chat-control delimiters are escaped in prompt data. '
             'The interface displays source text using text content, not interpreted HTML. '
             'These boundaries reduce exposure, but they are not a proof that a small language model can never be influenced semantically.'),
        dict(title='What AI got wrong, and what changed', section='Development decisions', kind='mistakes',
             narration='The initial half-billion-parameter model made unsupported line claims and confused attack types in its final assessment. '
             'For example, it discussed login events while assessing SQL injection. '
             'Source checks rejected unsupported citations rather than turning them into findings. '
             'The implementation moved to the larger quantized model, clearer observation definitions, and attack-specific assessment criteria. '
             f'The final sample still had {summary["rejected_model_observations"]} rejected map proposals. '
             'Those failures remain visible in the audit instead of being hidden.'),
        dict(title='Verification and an interview change', section='Evidence and maintenance', kind='tests',
             narration=f'The automated suite passed {test_count} tests, and the published commit also passed GitHub continuous integration. '
             'Tests cover token limits, Unicode fragments, invalid uploads, broken JSON, retries, restart behavior, duplicate events, and host-safe correlation. '
             'A separate audit checks real source coverage and actual call budgets. '
             'For a small interview change, a detection threshold can be edited in the policy module, paired with a meaningful regression test, and verified by running the suite. '
             'This video does not claim to demonstrate an unperformed live code change.'),
        dict(title='Limits and the next steps', section='Wrap-up', kind='outro',
             narration='Tracewatch is an auditable hybrid of local model analysis and conservative rules, not a complete security monitoring system. '
             'Novel attacks and unsupported log formats can be missed, and threshold choices need operational context. '
             'The memory result is sampled process memory, not proof from a complete four-gigabyte virtual machine stress test. '
             'Docker resource limits and browser interaction remain unverified. '
             'The repository includes source, setup instructions, AI usage notes, tests, measured evidence, and both walkthrough videos. '
             'Start with the README, launch the app, and reopen the saved sample under Recent analyses.'),
    ]
