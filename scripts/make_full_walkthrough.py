"""Render a complete English guide with speech, burned-in captions and MP3.

Uses saved verified results and illustrated workflows, never browser capture.
Requires Pillow, ffmpeg, and Windows System.Speech. Intermediate files ignored.
"""
from pathlib import Path
import argparse
import array
import json
import math
import re
import shutil
import subprocess
import wave
from PIL import Image, ImageDraw
from make_walkthrough import font
from full_walkthrough_story import build_story

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT/'artifacts'
ASSETS = ART/'full-walkthrough-assets'
W,H = 1920,1080
BG,PANEL,BORDER = '#0c1015','#151e27','#30404d'
WHITE,MUTED,GREEN,AMBER = '#e8eef2','#9aaab8','#b5ed8a','#e5bd72'


def put(draw,text,x,y,size=30,color=WHITE,width=1700,mono=False,line_height=None):
    face = font(size,mono)
    line_height = line_height or round(size*1.42)
    for paragraph in str(text).split('\n'):
        if mono:
            line=''
            for character in paragraph:
                if line and draw.textlength(line+character,font=face)>width:
                    draw.text((x,y),line,font=face,fill=color);y+=line_height
                    line='       '+character
                else:line+=character
            draw.text((x,y),line,font=face,fill=color);y+=line_height
            continue
        words = paragraph.split()
        line = ''
        for word in words:
            trial = (line+' '+word).strip()
            if line and draw.textlength(trial,font=face)>width:
                draw.text((x,y),line,font=face,fill=color)
                y += line_height
                line = word
            else:
                line = trial
        draw.text((x,y),line,font=face,fill=color)
        y += line_height
    return y


def box(draw,rect):
    draw.rounded_rectangle(rect,radius=16,fill=PANEL,outline=BORDER,width=2)


def arrow(draw,a,b):
    draw.line((*a,*b),fill=GREEN,width=3)
    angle = math.atan2(b[1]-a[1],b[0]-a[0])
    points=[b]
    for offset in (-.45,.45):
        points.append((b[0]-16*math.cos(angle+offset),b[1]-16*math.sin(angle+offset)))
    draw.polygon(points,fill=GREEN)


def bullets(draw,items,y=400,x=120,width=1600,size=31,spacing=26):
    for i,item in enumerate(items):
        put(draw,f'{i+1:02}',x,y+2,20,GREEN,width=55,mono=True)
        y=put(draw,item,x+66,y,size,width=width-66)+spacing
    if y>914:
        raise RuntimeError('Scene bullet text exceeds the safe frame area')


def metric(draw,x,y,width,value,label,note=''):
    box(draw,(x,y,x+width,y+205))
    put(draw,value,x+27,y+23,61,GREEN,width=width-54)
    put(draw,label,x+28,y+108,24,width=width-56)
    if note:put(draw,note,x+28,y+149,19,MUTED,width=width-56)


def terminal(draw,title,commands,note):
    box(draw,(80,330,1840,775))
    put(draw,title,112,351,19,MUTED,mono=True)
    draw.line((112,393,1808,393),fill=BORDER,width=2)
    y=425
    for command in commands:
        put(draw,'PS >',113,y+3,25,GREEN,width=95,mono=True)
        y=put(draw,command,219,y,31,width=1570,mono=True)+20
    put(draw,note,85,810,25,MUTED,width=1730)


def excerpt(path,marker,count):
    source=(ROOT/path).read_text(encoding='utf-8').splitlines()
    index=next(i for i,line in enumerate(source) if marker in line)
    return '\n'.join(f'{i+1:>3}  {line}' for i,line in enumerate(source[index:index+count],index))


def code_panel(draw,title,code,x=80,y=330,width=1760,height=520,size=26):
    box(draw,(x,y,x+width,y+height))
    put(draw,title,x+30,y+18,20,GREEN,width=width-60,mono=True)
    end=put(draw,code,x+30,y+69,size,width=width-60,mono=True,line_height=size+10)
    if end>y+height-10:raise RuntimeError(f'Code does not fit: {title}')


def render_scene(scene,index,count,summary,test_count):
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    d.rounded_rectangle((80,50,126,96),radius=12,fill=GREEN)
    d.line((92,74,101,84,116,64),fill='#142514',width=4)
    put(d,'tracewatch.',146,50,36)
    put(d,'ILLUSTRATED GUIDE / SAVED EVIDENCE / CODE',1170,67,17,MUTED,mono=True,width=690)
    d.line((80,127,1840,127),fill=BORDER,width=2)
    put(d,f'{index+1:02} / {count:02}   {scene["section"].upper()}',84,160,20,GREEN,mono=True)
    put(d,scene['title'],80,207,59,width=1760)
    kind=scene['kind']
    ram=summary['peak_backend_and_model_rss_bytes']/1024**3
    if kind in ('intro','constraints','results','model','tests'):
        values={
            'intro':[('LOCAL','Inference','Qwen + llama.cpp'),('2,048','Tokens per call','Prompt + evidence + output'),('ONE','Combined report','Across the complete log'),('OFFLINE','After setup','No cloud AI at runtime')],
            'constraints':[('4 GB','Machine target','OS + backend + model'),('2 CPU','No GPU','One inference slot'),('2,048','Token ceiling','Every single call'),('LOCAL','Model only','Download once at setup')],
            'results':[(str(summary['completed_lines']),'Source lines covered','No gaps or overlaps'),(str(summary['map_calls']+summary['reduce_calls']),'Completed AI calls','34 map + 5 synthesis'),(str(len([f for f in summary['findings'] if f['status']=='accepted'])),'Merged findings','Candidates for review'),(f'{ram:.2f} GiB','Peak combined RSS','Sampled processes')],
            'model':[('1.5B','Qwen2.5 Instruct','General language model'),('Q4_K_M','GGUF quantization','About 1.12 GB of weights'),('2','CPU threads','Generation and batch'),('1','Inference slot','One owned model process')],
            'tests':[(str(test_count),'Automated tests','Recorded suite: PASS'),('PASS','GitHub CI','Published app commit'),('258 / 258','Real source audit','Exact coordinates checked'),('2,047','Largest reserved total','Within 2,048 tokens')],
        }[kind]
        for i,(v,label,note) in enumerate(values):metric(d,80+i*450,350,410,v,label,note)
        notes={
            'intro':['Setup and everyday use','Evidence, code decisions, recovery and limitations'],
            'constraints':['A file larger than the context requires multiple calls.','The result must preserve links between distant events.'],
            'results':['Verified sample results, not a general accuracy claim.','Recorded active time: 18.6 minutes; downtime excluded.'],
            'model':['The initial 0.5B evaluation was unreliable.','One queue avoids multiple model copies in memory.'],
            'tests':['Boundary cases: Unicode, JSON failures, restart and host scopes.','Interview change: policy -> regression test -> full suite.'],
        }[kind]
        bullets(d,notes,y=626,size=30,spacing=22)
    elif kind=='setup':
        terminal(d,'ONE-TIME POWERSHELL SETUP',[
            'python -m venv .venv',
            '.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt',
            '.\\.venv\\Scripts\\python.exe scripts/setup.py'],
            'Internet is needed here. Downloads are pinned and SHA-256 verified.')
    elif kind=='launch':
        terminal(d,'EVERYDAY STARTUP', ['cd D:\\Cultive','python scripts/run.py','Open: http://127.0.0.1:8000'],
                 'Use the same Python environment as setup. Keep PowerShell running.')
    elif kind=='workflow':
        steps=[('Choose file','.log or .txt / UTF-8'),('Start analysis','Wait for engine Ready'),('Review findings','Expand original evidence'),('Export report','Download combined JSON')]
        for i,(title,note) in enumerate(steps):
            x=80+i*450;box(d,(x,375,x+410,620))
            put(d,f'0{i+1}',x+28,400,32,GREEN,mono=True)
            put(d,title,x+28,470,32,width=354)
            put(d,note,x+28,531,22,MUTED,width=350)
            if i<3:arrow(d,(x+416,493),(x+443,493))
        bullets(d,['Up to 5 MiB. Invalid or empty uploads are rejected.','Recent analyses reopens saved work without rerunning the model.'],y=695,size=27)
    elif kind=='progress':
        box(d,(80,332,1840,560))
        put(d,'SOURCE COVERAGE',112,358,22,MUTED,mono=True)
        put(d,f'{summary["completed_lines"]} / {summary["total_lines"]} original lines',112,407,43,width=1600)
        d.rounded_rectangle((115,501,1802,510),radius=4,fill=GREEN)
        bullets(d,['Lines processed and call counts show completed work.','Extraction first; combined assessment adds the findings.','Needs attention -> Resume retries the incomplete call.'],y=613,size=28,spacing=17)
    elif kind=='findings':
        box(d,(80,330,1840,838));put(d,'SAVED COMBINED REPORT',110,350,20,GREEN,mono=True)
        rows=sorted(summary['findings'],key=lambda f:f['severity']!='High')
        for i,f in enumerate(rows):
            y=405+i*76
            color=AMBER if f['severity']=='Medium' else '#f29a92'
            put(d,f['severity'].upper(),115,y+2,20,color,width=175,mono=True)
            put(d,f['attack_type'],310,y,29,width=810)
            put(d,f['ip'],1240,y+3,25,MUTED,width=520,mono=True)
            d.line((114,y+56,1805,y+56),fill=BORDER,width=1)
        put(d,'All entries are possible attacks requiring review, not confirmed exploitation.',85,867,24,MUTED)
    elif kind=='timeline':
        chain=next(f for f in summary['findings'] if f['attack_type']=='Possible account compromise')
        success=chain['counts']['later_success_line']; failures=[n for n in chain['lines'] if n<success]
        data=[('EARLY',failures[0],'Failed login'),('MIDDLE',failures[len(failures)//2],'More failures'),('LATE',success,'Explicit success')]
        for i,(label,line,caption) in enumerate(data):
            x=80+i*610;box(d,(x,355,x+540,630));put(d,label,x+30,381,22,GREEN,mono=True)
            put(d,f'Line {line}',x+30,431,52,width=470);put(d,caption,x+30,516,28,MUTED,width=470)
            if i<2:arrow(d,(x+550,490),(x+598,490))
        put(d,f"{chain['counts']['failed_logins']} prior failures -> one possible-compromise finding",85,680,35,GREEN)
        put(d,f"IP: {chain['ip']}   /   Account: {chain['account']}",85,753,28,mono=True)
        put(d,chain['host'],85,807,24,MUTED,mono=True)
    elif kind=='policy':
        bullets(d,['Authentication: 5 failures; explicit later success for a possible chain.','Requests: SQL syntax, sensitive-path probes, repeated 401/403.','Rate: 30 / 60s, or 10 / 5s plus at least 3 HTTP 429 responses.','Normal errors and successful health checks alone are insufficient.'],y=359,size=31,spacing=28)
    elif kind=='architecture':
        cards=[('STREAM UPLOAD','Bounded UTF-8 ingestion'),('SQLITE SOURCE','Lines + event facts'),('TOKEN PACKER','Count exact rendered prompt'),('LOCAL MODEL','Sequential map calls'),('VALIDATE + SAVE','Check source citations'),('COMBINED REPORT','Correlate, assess, deduplicate')]
        positions=[(80,340),(690,340),(1300,340),(1300,614),(690,614),(80,614)]
        for (title,note),(x,y) in zip(cards,positions):
            box(d,(x,y,x+540,y+180));put(d,title,x+28,y+31,26,GREEN,width=485,mono=True)
            put(d,note,x+28,y+99,25,width=485)
        arrow(d,(630,430),(675,430));arrow(d,(1240,430),(1285,430));arrow(d,(1570,533),(1570,598))
        arrow(d,(1285,704),(1240,704));arrow(d,(675,704),(630,704))
        put(d,'Persistent history lives outside the model context.',85,853,25,MUTED)
    elif kind=='budget':
        labels=[('1,568','Input: template + source + saved facts'),('448','Reserved model response'),('32','Unused safety margin')]
        for i,(value,label) in enumerate(labels):metric(d,80+i*600,348,550,value,label)
        x=80;available=1760
        for value,color in [(1568,GREEN),(448,'#71a5cd'),(32,AMBER)]:
            length=round(available*value/2048);d.rectangle((x,640,x+length,705),fill=color);x+=length
        put(d,'2,048 TOTAL TOKENS',83,743,39,GREEN,mono=True)
        put(d,'Up to 160 saved-fact tokens are included INSIDE the input allocation.',84,817,27,MUTED)
    elif kind=='code_model':
        snippet=excerpt(Path('app/model.py'),'    def prepare(',3)+'\n     ...\n'+excerpt(Path('app/model.py'),'        with self.lock:',6)
        code_panel(d,'app/model.py  /  render, tokenize, submit (excerpts)',snippet,height=550,size=24)
    elif kind=='chunking':
        code_panel(d,'app/chunking.py  /  retained coordinates',excerpt(Path('app/chunking.py'),'@dataclass',6),width=815,height=430,size=30)
        box(d,(945,330,1840,760))
        bullets(d,['Whole lines when they fit.','Move fitting continuations together.','Oversized line -> Unicode-safe pieces.','Retain physical line + character offset.'],x=975,y=373,width=800,size=27,spacing=21)
        put(d,'Audit: reconstruct fragments and compare with the source.',85,817,30,GREEN)
    elif kind=='memory':
        for x,title,items in [(80,'PERSISTED IN SQLITE',['Complete event ledger','Validated model observations','Source lines and attempts']),
                              (1020,'INSIDE A MODEL CALL',['Relevant earlier facts only','Bounded to 160 tokens','Fits inside the 1,568-token input'])]:
            box(d,(x,340,x+820,760));put(d,title,x+30,371,26,GREEN,width=760,mono=True)
            bullets(d,items,x=x+30,y=440,width=755,size=28,spacing=26)
        arrow(d,(919,555),(1000,555));put(d,'Final correlation uses the full ledger, not just the carried prompt.',85,817,30,MUTED)
    elif kind=='recovery':
        bullets(d,['Save the exact request BEFORE inference.','Commit successful reply + observations + cursor together.','Retry up to 3 times; 2s and 4s backoff between attempts.','Pause safely; restart or Resume continues incomplete work.','Model / prompt fingerprint protects saved token IDs.'],y=342,size=29,spacing=20)
    elif kind=='injection':
        box(d,(80,340,1840,495));put(d,'UNTRUSTED LOG TEXT IS STILL DATA',112,365,24,AMBER,mono=True)
        put(d,'A submitted message requested removal of failed-login evidence.',113,420,31,width=1660)
        bullets(d,['No shell commands or tools are exposed to the model.','Escape literal chat delimiters; validate source citations.','Render evidence as text, never interpreted HTML.','Semantic influence remains a limitation to acknowledge.'],y=548,size=29,spacing=20)
    elif kind=='mistakes':
        box(d,(80,340,920,790));box(d,(1000,340,1840,790))
        put(d,'INITIAL 0.5B EVALUATION',112,370,26,AMBER,width=770,mono=True)
        bullets(d,['Unsupported source-line claims','SQL assessment discussed unrelated logins','Negative results preserved'],x=112,y=445,width=740,size=28,spacing=26)
        put(d,'CORRECTIONS',1032,370,26,GREEN,width=770,mono=True)
        bullets(d,['1.5B quantized local model','Clear kinds + attack-specific rubrics','Source corroboration and retained audit'],x=1032,y=445,width=740,size=28,spacing=26)
        put(d,f"Final sample: {summary['rejected_model_observations']} map proposals rejected. No accuracy guarantee.",85,835,28,MUTED)
    elif kind=='outro':
        bullets(d,['Read README.md and AI_USAGE.md.','Run the app, then open the saved sample in Recent analyses.','Review original evidence before taking security actions.','Known limits: model/rule misses; browser and Docker QA incomplete.','Source and videos are included in the GitHub repository.'],y=348,size=30,spacing=24)
    else:raise ValueError(kind)
    d.line((80,916,1840,916),fill=BORDER,width=2)
    d.line((80,916,80+1760*(index+1)/count,916),fill=GREEN,width=4)
    return im


def segments(text):
    result=[]
    for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])',text.strip()):
        words=sentence.split()
        while words:
            take=min(26,len(words))
            while len(' '.join(words[:take]))>190 and take>8:take-=1
            result.append(' '.join(words[:take]));words=words[take:]
    return result


def caption(base,text,chapter):
    im=base.copy();d=ImageDraw.Draw(im)
    put(d,chapter,84,939,16,GREEN,width=1750)
    end=put(d,text,84,971,30,width=1750,line_height=39)
    if end>1078:raise RuntimeError('Caption exceeds frame: '+text)
    return im


def timestamp(seconds,srt=False):
    milliseconds=round(seconds*1000)
    h,m=divmod(milliseconds//60000,60);s=(milliseconds//1000)%60
    return f'{h:02}:{m:02}:{s:02}{"," if srt else "."}{milliseconds%1000:03}'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview-only',action='store_true');args=parser.parse_args()
    summary=json.loads((ART/'verification.json').read_text(encoding='utf-8'))
    if summary['status']!='completed' or summary['coverage_errors'] or summary['incomplete_calls']:
        raise SystemExit('Requires a completed, verified source run.')
    matched=re.search(r'Result:\s*(\d+) passed',(ART/'test-results.txt').read_text())
    if not matched:raise SystemExit('Recorded test result not found.')
    test_count=int(matched[1]);story=build_story(summary,test_count)
    ASSETS.mkdir(parents=True,exist_ok=True)
    metadata=[]
    for index,scene in enumerate(story):
        base=render_scene(scene,index,len(story),summary,test_count)
        parts=segments(scene['narration'])
        caption(base,parts[0],scene['section']).save(ASSETS/f'preview-{index:02}.png')
        if args.preview_only:continue
        for text in parts:
            n=len(metadata);image=ASSETS/f'frame-{n:03}.png';audio=ASSETS/f'audio-{n:03}.wav'
            caption(base,text,scene['section']).save(image)
            metadata.append(dict(index=n,chapter=index,title=scene['title'],image=str(image),audio=str(audio),narration=text))
    print(f'{len(story)} chapters, {sum(len(s["narration"].split()) for s in story)} spoken words',flush=True)
    if args.preview_only:return
    story_path=ASSETS/'speech.json';story_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    print('Synthesizing offline English speech...',flush=True)
    subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'scripts'/'narrate.ps1'),'-StoryPath',str(story_path)],check=True)
    duration=0;params=None;cues=[];chapters=[]
    with wave.open(str(ASSETS/'narration.wav'),'wb') as joined:
        for part in metadata:
            with wave.open(part['audio'],'rb') as source:
                current=source.getparams()
                if params is None:params=current;joined.setparams(params)
                if current[:3]!=params[:3] or params.sampwidth!=2:raise RuntimeError('Unexpected speech audio format')
                data=source.readframes(source.getnframes())
                samples=array.array('h',data)
                if not any(samples):raise RuntimeError('Speech segment is silent')
                speech_seconds=source.getnframes()/params.framerate
                silence=bytes(round(params.framerate*.18)*params.sampwidth*params.nchannels)
                joined.writeframes(data);joined.writeframes(silence)
                seconds=speech_seconds+len(silence)/(params.framerate*params.sampwidth*params.nchannels)
            if not chapters or chapters[-1]['index']!=part['chapter']:
                chapters.append(dict(index=part['chapter'],title=part['title'],start=duration))
            cues.append(dict(start=duration,end=duration+seconds,text=part['narration'],image=part['image']))
            duration+=seconds
    subtitles='\n\n'.join(f'{i+1}\n{timestamp(c["start"],True)} --> {timestamp(c["end"],True)}\n{c["text"]}' for i,c in enumerate(cues))+'\n'
    (ART/'full-walkthrough.srt').write_text(subtitles,encoding='utf-8',newline='\n')
    transcript=['# Tracewatch complete narrated guide','',
                'English synthetic narration using Windows System.Speech. Visuals are illustrations, saved evidence and code; no live browser recording.','']
    for chapter,scene in zip(chapters,story):
        transcript.extend([f'## {timestamp(chapter["start"])} - {scene["title"]}','',scene['narration'],''])
    (ART/'full-walkthrough-transcript.md').write_text('\n'.join(transcript),encoding='utf-8',newline='\n')
    (ART/'full-walkthrough-chapters.txt').write_text('\n'.join(f'{timestamp(c["start"])} {c["title"]}' for c in chapters)+'\n',encoding='utf-8',newline='\n')
    manifest=[]
    for cue in cues:
        manifest.extend(["file '"+Path(cue['image']).as_posix()+"'",f'duration {cue["end"]-cue["start"]:.6f}'])
    manifest.append("file '"+Path(cues[-1]['image']).as_posix()+"'")
    concat=ASSETS/'frames.txt';concat.write_text('\n'.join(manifest)+'\n',encoding='utf-8',newline='\n')
    ffmpeg=shutil.which('ffmpeg') or 'ffmpeg'
    common=[ffmpeg,'-hide_banner','-loglevel','error','-y']
    print(f'Encoding {duration:.1f}s of full-HD video with {len(cues)} caption cues...',flush=True)
    subprocess.run(common+['-f','concat','-safe','0','-i',str(concat),'-i',str(ASSETS/'narration.wav'),
        '-c:v','libx264','-preset','fast','-threads','2','-crf','21','-vf','fps=25,format=yuv420p',
        '-c:a','aac','-b:a','112k','-t',f'{duration:.6f}','-movflags','+faststart',str(ART/'full-walkthrough.mp4')],check=True)
    subprocess.run(common+['-i',str(ASSETS/'narration.wav'),'-codec:a','libmp3lame','-q:a','3',str(ART/'full-walkthrough-speech.mp3')],check=True)
    print(json.dumps({'duration_seconds':round(duration,3),'chapters':len(chapters),'caption_cues':len(cues),
                      'video':str(ART/'full-walkthrough.mp4'),'speech':str(ART/'full-walkthrough-speech.mp3')}),flush=True)


if __name__=='__main__':main()
