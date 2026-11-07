"""Create a narrated architecture/code walkthrough from measured run artifacts.

This makes explanatory slides, NOT a browser recording. Requires Pillow and
ffmpeg; Windows System.Speech provides offline narration. Not an app dependency.
"""
from pathlib import Path
import json
import shutil
import subprocess
import textwrap
import wave
from PIL import Image,ImageDraw,ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts'/'walkthrough-assets'
WIDTH,HEIGHT = 1600,900
BG,PANEL,LINE = '#0c1015','#151d25','#2c3843'
WHITE,MUTED,GREEN = '#e7ecef','#91a0af','#b5ed8a'


def font(size,mono=False):
    paths = [Path('C:/Windows/Fonts')/('consola.ttf' if mono else 'segoeui.ttf'),
             Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSansMono.ttf' if mono else 'DejaVuSans.ttf')]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path),size)
    return ImageFont.load_default(size=size)


def lines(draw,text,xy,size=30,color=WHITE,width=82,spacing=16):
    x,y=xy
    for paragraph in text.split('\n'):
        for line in textwrap.wrap(paragraph,width=width) or ['']:
            draw.text((x,y),line,font=font(size),fill=color)
            y+=size+spacing
    return y


def main():
    summary = json.loads((ROOT/'artifacts'/'verification.json').read_text())
    if summary['status']!='completed' or summary['coverage_errors']:
        raise SystemExit('A complete verified real run is required before making the walkthrough.')
    OUT.mkdir(parents=True,exist_ok=True)
    ram = summary['peak_backend_and_model_rss_bytes']/1024**3
    findings = [f for f in summary['findings'] if f['status']=='accepted']
    result = f"{summary['total_lines']} lines  |  {summary['map_calls']} map calls  |  {len(findings)} findings"
    story = [
      ('Local AI. Connected evidence.', 'A security log analyzer built for a 4 GB, 2 CPU machine.',
       ['Python + FastAPI + SQLite','Qwen2.5 1.5B Instruct / Q4_K_M','llama.cpp / CPU only / one model slot'],
       'This is Tracewatch, a local AI security log analyzer. The challenge is not just splitting a file. It is keeping related evidence connected under a two thousand and forty eight token context limit, on a small CPU-only machine.'),
      ('One file becomes one investigation.',result,
       ['Stream the upload into numbered SQLite source lines.','Analyze bounded chunks with a downloaded language model.','Correlate the full event ledger, then assess combined candidates.'],
       f"The real sample has {summary['total_lines']} source lines. Uploads are streamed into SQLite, rather than copied into several large strings. The backend made {summary['map_calls']} map calls and {summary['reduce_calls']} final assessment calls. The result is one report, not one report per chunk."),
      ('Count the actual model tokens.','The template, source, saved context and output share one ceiling.',
       ['1,568 tokens maximum: rendered prompt + log fragments + prior facts','448 tokens reserved: structured model response','32 tokens unused: safety margin'],
       'I count tokens with the tokenizer embedded in the model. Llama.cpp first renders the chat template. The same counted token IDs go directly into inference. Input is capped at fifteen sixty eight tokens, with four hundred forty eight reserved for output and a thirty two token safety margin.'),
      ('Keep coordinates. Keep the evidence.','Whole entries where possible. Explicit fragments when necessary.',
       ['Every fragment retains its original physical line and character offset.','Multiline continuations move together when the entry fits.','Oversized Unicode entries split without dropping characters.'],
       'The packer preserves whole lines and moves multiline stack traces together where possible. When an entry is too large, it uses Unicode-safe fragments with original line numbers and character offsets. The verifier reconstructs source coverage and checks for gaps and overlaps.'),
      ('Connect distant events.','A bounded prompt is not a bounded investigation.',
       ['Failure near the start -> more failures in the middle -> later success','Scope authentication by IP + host + account.','Persist all event facts; carry only relevant bounded facts forward.'],
       'All event facts remain in SQLite, even when they cannot fit in the prompt. Authentication is correlated by IP, host and account. Five failures followed by explicit success can become one possible compromise finding. The model sees representative early, middle and late evidence, plus validated earlier observations.'),
      ('Make failures recoverable.','Durable calls and a single FIFO worker.',
       ['Save exact input before inference; commit replies and checkpoints together.','Retry failed calls up to three times. Pause with completed work intact.','A real restart retained 13 completed calls and resumed the pending call.'],
       'The worker saves the exact request before inference. Successful replies and cursor advancement commit together. Timeouts, bad JSON and truncated replies retry up to three times. A restart test retained thirteen completed real model calls and continued the incomplete call. There are no parallel model replicas.'),
      ('Do not trust the model blindly.','An actual mistake changed the implementation.',
       ['The first 0.5B run invented mismatched citations and confused attack types.','Source checks rejected the unsupported observations.','I moved to 1.5B and added attack-specific assessment criteria.'],
       'The first half-billion-parameter model made real mistakes. It labeled unrelated lines and discussed login events while assessing SQL injection. Source validation rejected those observations. I switched to the one point five billion model and replaced the overloaded final prompt with attack-specific criteria. Rejected judgments stay in the audit.'),
      ('Measured results, explicit limits.',f"Peak combined RSS: {ram:.2f} GiB  |  Context ceiling: 2,048 tokens",
       [f"Coverage audit: {summary['completed_lines']}/{summary['total_lines']} lines; {len(summary['coverage_errors'])} gaps or overlaps.",
        'Small-model + rule-based detection is conservative, not complete.','Browser interaction was permission-blocked; Docker cap was not exercised.'],
       f"The final run processed every source line with no coverage errors. Peak sampled model and backend memory was {ram:.2f} gibibytes. This is a hybrid of local AI and conservative rules, not proof that a file is safe. Browser interaction was blocked by the permission gate, and the Docker resource cap was not exercised in this session."),
      ('Ready to inspect. Ready to change.','Source, prompts, tests and measured evidence are included.',
       ['python scripts/setup.py  ->  python scripts/run.py','python -m pytest tests -q  ->  python scripts/verify_run.py','README.md / AI_USAGE.md / app/prompts.py / app/detection.py'],
       'The source includes setup instructions, tests, prompt history, failure handling and a measured run audit. For an interview change, detection thresholds are in detection dot py, model prompts are in prompts dot py, and the tests cover cross-part correlation, invalid input and resume behavior. This video uses explanatory slides, not a claimed browser recording.'),
    ]
    metadata=[]
    for i,(title,subtitle,bullets,narration) in enumerate(story):
        image=Image.new('RGB',(WIDTH,HEIGHT),BG);draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((70,55,108,94),radius=10,fill=GREEN)
        draw.line((81,75,88,82,100,66),fill='#172716',width=3)
        draw.text((123,57),'tracewatch.',font=font(30),fill=WHITE)
        draw.text((1120,67),'LOCAL AI / CODE WALKTHROUGH',font=font(14,True),fill=MUTED)
        draw.line((70,125,1530,125),fill=LINE,width=2)
        draw.text((75,165),f'{i+1:02} / DESIGN + EVIDENCE',font=font(16,True),fill=GREEN)
        draw.text((70,210),title,font=font(55),fill=WHITE)
        lines(draw,subtitle,(75,295),size=25,color=MUTED,width=100)
        draw.rounded_rectangle((70,380,1530,726),radius=18,fill=PANEL,outline=LINE,width=2)
        y=418
        for j,bullet in enumerate(bullets):
            draw.text((101,y+2),f'0{j+1}',font=font(18,True),fill=GREEN)
            y=lines(draw,bullet,(155,y),size=27,width=85,spacing=10)+24
        draw.text((74,766),'DIAGRAMS + SOURCE EXPLANATION / OFFLINE NARRATION',font=font(14,True),fill=MUTED)
        draw.text((74,811),'4 GB target   /   2 CPU threads   /   no cloud AI',font=font(19),fill='#b5c4b1')
        for dot in range(len(story)):
            draw.rounded_rectangle((1238+dot*30,818,1257+dot*30,822),radius=2,fill=GREEN if dot<=i else LINE)
        image_path=OUT/f'slide-{i:02}.png';image.save(image_path)
        metadata.append({'index':i,'image':str(image_path),'audio':str(OUT/f'audio-{i:02}.wav'),'narration':narration})
    story_path=OUT/'story.json';story_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'scripts'/'narrate.ps1'),'-StoryPath',str(story_path)],check=True)
    durations=[]
    params=None
    with wave.open(str(OUT/'narration.wav'),'wb') as joined:
        for slide in metadata:
            with wave.open(slide['audio'],'rb') as part:
                if params is None:
                    params=part.getparams();joined.setparams(params)
                elif part.getparams()[:3]!=params[:3]:
                    raise RuntimeError('Narration audio formats differ')
                data=part.readframes(part.getnframes());joined.writeframes(data)
                silence=bytes(int(params.framerate*.6)*params.sampwidth*params.nchannels)
                joined.writeframes(silence)
                durations.append(part.getnframes()/params.framerate+.6)
    concat=[]
    for slide,duration in zip(metadata,durations):
        concat.extend(["file '"+Path(slide['image']).as_posix()+"'",f'duration {duration:.4f}'])
    concat.append("file '"+Path(metadata[-1]['image']).as_posix()+"'")
    manifest=OUT/'slides.txt';manifest.write_text('\n'.join(concat)+'\n',encoding='utf-8')
    subprocess.run([shutil.which('ffmpeg') or 'ffmpeg','-y','-f','concat','-safe','0','-i',str(manifest),
                    '-i',str(OUT/'narration.wav'),'-c:v','libx264','-preset','fast','-crf','22',
                    '-vf','fps=25,format=yuv420p','-c:a','aac','-b:a','96k','-shortest','-movflags','+faststart',
                    str(ROOT/'artifacts'/'walkthrough.mp4')],check=True)
    print('Created',ROOT/'artifacts'/'walkthrough.mp4','seconds',round(sum(durations),1))


if __name__=='__main__':main()
