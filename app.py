import streamlit as st
import streamlit.components.v1 as components
import re, json, os, textwrap

st.set_page_config(page_title="YouTube 영어 학습기", page_icon="🎓", layout="wide")
st.markdown("""
<style>
  .stApp{background:#0f1117;color:#e8eaf6;}
  .stButton>button{background:linear-gradient(135deg,#3949ab,#7c4dff)!important;
    color:#fff!important;border:none!important;border-radius:10px!important;font-weight:600!important;}
  .stTextInput>div>div>input{background:#1e2130!important;color:#e8eaf6!important;
    border:1px solid #3949ab!important;border-radius:10px!important;}
</style>
""", unsafe_allow_html=True)

# ── 커스텀 컴포넌트 등록 (allow="autoplay; microphone" iframe 생성) ─────────
COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "tts_component")
os.makedirs(COMPONENT_DIR, exist_ok=True)

# ── YouTube ID ─────────────────────────────────────────────────────────────────
def extract_video_id(url):
    for p in [r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",r"^([A-Za-z0-9_-]{11})$"]:
        m=re.search(p,url)
        if m: return m.group(1)
    return None

# ── VTT 파싱 ──────────────────────────────────────────────────────────────────
def parse_vtt_text(raw):
    seen,out=[],[]
    for line in raw.splitlines():
        line=line.strip()
        if not line or "-->" in line or line.startswith("WEBVTT") or re.match(r"^\d+$",line): continue
        line=re.sub(r"<[^>]+>","",line)
        if line and line not in seen: seen.append(line);out.append(line)
    return " ".join(out)

# ── 자막 취득 ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600,show_spinner=False)
def get_transcript(video_id):
    errors=[]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tl=YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in ["en","en-US","en-GB"]:
            try:
                segs=tl.find_transcript([lang]).fetch()
                text=" ".join(s["text"] for s in segs)
                if len(text)>100: return text,"transcript-api",""
            except: pass
        for t in tl:
            if t.language_code.startswith("en"):
                segs=t.fetch();text=" ".join(s["text"] for s in segs)
                if len(text)>100: return text,"auto-caption",""
        errors.append("transcript-api: 영어 자막 없음")
    except Exception as e: errors.append(f"transcript-api: {e}")
    try:
        import yt_dlp,tempfile,glob
        tmp=tempfile.mkdtemp()
        opts={"skip_download":True,"writeautomaticsub":True,"writesubtitles":True,
              "subtitleslangs":["en","en-US","en-GB"],"subtitlesformat":"vtt",
              "outtmpl":os.path.join(tmp,"sub_%(id)s.%(ext)s"),"quiet":True,"no_warnings":True,
              "socket_timeout":30,"http_headers":{"User-Agent":"com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"},
              "extractor_args":{"youtube":{"player_client":["android","web"]}}}
        with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        vtt_files=glob.glob(os.path.join(tmp,f"sub_{video_id}*.vtt"))
        if vtt_files:
            text=parse_vtt_text(open(vtt_files[0],encoding="utf-8").read())
            if len(text)>100: return text,"yt-dlp",""
        errors.append("yt-dlp: VTT 없음")
    except Exception as e: errors.append(f"yt-dlp: {e}")
    try:
        import requests
        r=requests.get("https://api.supadata.ai/v1/youtube/transcript",
                       params={"videoId":video_id,"lang":"en"},timeout=20)
        if r.status_code==200:
            d=r.json();content=d.get("content",d.get("transcript",""))
            text=" ".join(c.get("text","") for c in content) if isinstance(content,list) else str(content)
            if len(text)>100: return text,"supadata",""
        errors.append(f"supadata:{r.status_code}")
    except Exception as e: errors.append(f"supadata:{e}")
    return "","failed"," | ".join(errors)

# ── API 키 ─────────────────────────────────────────────────────────────────────
def get_api_key():
    try:
        k=st.secrets.get("GEMINI_API_KEY","")
        if k: return k
    except: pass
    return os.environ.get("GEMINI_API_KEY","")

# ── Gemini 분석 ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400,show_spinner=False)
def analyze_transcript(transcript):
    import requests,time
    api_key=get_api_key()
    if not api_key: return [],[],  "NO_KEY"
    prompt=f"""아래는 YouTube 영상의 영어 자막입니다.
<transcript>{transcript[:6000]}</transcript>
다음 두 가지를 분석해 JSON으로만 응답 (마크다운 코드블록 없이 순수 JSON).
단어 10개: ❌기초어휘 제외 ✅구동사·관용구·콜로케이션·원어민구어
문장 10개: ❌단순구조 제외 ✅도치·분열문·구어체생략·원어민연결어
{{"words":[{{"word":"","ipa":"","korean":"","usage":"","why":""}}],
  "sentences":[{{"en":"","ko":"","why":""}}]}}"""
    MODELS=["gemini-3.5-flash","gemini-3.1-flash-lite","gemini-2.5-flash"]
    last_err="알 수 없는 오류"
    for model in MODELS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":2000,"temperature":0.2}}
        for attempt in range(3):
            try:
                r=requests.post(url,json=payload,timeout=60)
                if r.status_code==429:
                    wait=min(int(r.headers.get("Retry-After",2**(attempt+1))),30)
                    last_err=f"{model}:429,{wait}초대기"; time.sleep(wait); continue
                if r.status_code==404: last_err=f"{model}:404"; break
                r.raise_for_status()
                raw=r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw=re.sub(r"^```[a-z]*","",raw);raw=re.sub(r"```$","",raw).strip()
                data=json.loads(raw)
                return data.get("words",[]),data.get("sentences",[]),""
            except Exception as e:
                last_err=f"{model}시도{attempt+1}:{e}"
                if attempt<2: time.sleep(2**attempt)
    return [],[],f"모든 모델 실패—{last_err}"

# ── 커스텀 컴포넌트 HTML 파일 생성 ────────────────────────────────────────────
def write_component(words, sentences, video_id):
    wj=json.dumps(words,ensure_ascii=False)
    sj=json.dumps(sentences,ensure_ascii=False)

    html=textwrap.dedent(f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#0f1117;color:#e8eaf6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:12px;}}
h2{{color:#90caf9;font-size:1.05rem;font-weight:700;border-bottom:2px solid #3949ab;padding-bottom:5px;margin:18px 0 10px;}}
.card{{background:#1e2130;border-radius:12px;padding:13px 16px;margin:9px 0;border:1px solid #2d3250;}}
.sent{{border-left:3px solid #5c6bc0;}}
.row{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:3px;}}
.num{{color:#7986cb;font-weight:700;min-width:20px;}}
.kor{{color:#a5d6a7;font-weight:700;font-size:.93rem;}}
.ipa{{color:#90caf9;font-size:.82rem;}}
.why{{color:#ffcc80;font-size:.79rem;margin:4px 0;}}
.usage{{background:#0d1021;border-radius:6px;padding:4px 9px;color:#90caf9;font-size:.8rem;font-style:italic;margin-top:3px;}}
.en{{color:#cfd8dc;font-size:.87rem;margin:3px 0 7px;line-height:1.5;}}
button{{cursor:pointer;border:none;outline:none;-webkit-tap-highlight-color:transparent;touch-action:manipulation;}}
.spk{{background:#3949ab;color:#fff;border-radius:8px;padding:6px 13px;font-size:.88rem;font-weight:600;}}
.spk:active{{background:#283593;transform:scale(.96);}}
.spk.playing{{background:#1565c0;animation:sp .7s ease infinite alternate;}}
@keyframes sp{{from{{box-shadow:0 0 0 0 #42a5f566;}}to{{box-shadow:0 0 0 9px #42a5f500;}}}}
.rec{{background:#c62828;color:#fff;border-radius:50%;width:42px;height:42px;font-size:1.2rem;flex-shrink:0;}}
.rec:active{{transform:scale(.91);}}
.rec.on{{background:#b71c1c;animation:rp 1s ease infinite;}}
@keyframes rp{{0%,100%{{box-shadow:0 0 0 0 #c6282855;}}50%{{box-shadow:0 0 0 9px #c6282800;}}}}
.sw{{margin-top:9px;}}
.sl{{font-weight:700;font-size:.92rem;margin-bottom:2px;}}
.st{{height:9px;border-radius:4px;background:#2d3250;overflow:hidden;}}
.sf{{height:9px;border-radius:4px;transition:width .5s ease;}}
.ss{{color:#b0bec5;font-size:.77rem;margin-top:3px;}}
.hint{{color:#7986cb;font-size:.76rem;}}
yt-frame{{display:block;width:100%;border-radius:10px;margin-bottom:14px;}}
</style>
</head>
<body>

<iframe width="100%" height="220" style="border-radius:10px;margin-bottom:14px;display:block;"
  src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen></iframe>

<h2>📚 핵심 단어 TOP 10</h2>
<p style="color:#7986cb;font-size:.79rem;margin-bottom:9px;">🇰🇷 뜻 → 🇺🇸 단어 | 🔊 발음 | 🎤 따라하기</p>
<div id="wc"></div>
<h2 style="margin-top:22px;">💬 핵심 문장 TOP 10</h2>
<p style="color:#7986cb;font-size:.79rem;margin-bottom:9px;">🇰🇷 번역 → 🇺🇸 원문 | 🔊 발음 | 🎤 따라하기</p>
<div id="sc"></div>

<script>
var WORDS={wj};
var SENTS={sj};

/* ── TTS ─────────────────────────────────────────────────────────────────── */
var syn=window.speechSynthesis;
var iosT=null, curBtn=null;

function getVoice(){{
  var vs=syn.getVoices();
  return vs.find(function(v){{return v.lang==='en-US'&&v.name.indexOf('Google')>-1;}})
      ||vs.find(function(v){{return v.name==='Samantha';}})
      ||vs.find(function(v){{return v.lang==='en-US';}})
      ||vs.find(function(v){{return v.lang.indexOf('en')===0;}})
      ||null;
}}

function doSpeak(text,rate){{
  syn.cancel();
  if(iosT){{clearInterval(iosT);iosT=null;}}
  var u=new SpeechSynthesisUtterance(text);
  u.lang='en-US'; u.rate=rate||0.9; u.volume=1; u.pitch=1;
  var v=getVoice(); if(v) u.voice=v;
  u.onstart=function(){{
    iosT=setInterval(function(){{if(syn.paused)syn.resume();}},5000);
  }};
  u.onend=u.onerror=function(e){{
    if(iosT){{clearInterval(iosT);iosT=null;}}
    if(curBtn){{curBtn.classList.remove('playing');curBtn=null;}}
  }};
  syn.resume();
  syn.speak(u);
}}

function speak(text,rate,btn){{
  if(curBtn&&curBtn!==btn) curBtn.classList.remove('playing');
  curBtn=btn; btn.classList.add('playing');
  var vs=syn.getVoices();
  if(vs.length>0){{doSpeak(text,rate);}}
  else{{
    var tid=setTimeout(function(){{doSpeak(text,rate);}},300);
    syn.onvoiceschanged=function(){{syn.onvoiceschanged=null;clearTimeout(tid);doSpeak(text,rate);}};
  }}
}}

/* ── 음성인식 ────────────────────────────────────────────────────────────── */
var activeRec=null;
function startRec(target,type,btn,sid){{
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){{
    var el=document.getElementById(sid);
    if(el) el.innerHTML='<div style="color:#ffa726;font-size:.8rem;margin-top:5px;">⚠️ Android Chrome 또는 iOS Safari 필요</div>';
    return;
  }}
  if(activeRec){{activeRec.stop();activeRec=null;btn.classList.remove('on');return;}}
  var rec=new SR(); activeRec=rec;
  rec.lang='en-US'; rec.continuous=false; rec.interimResults=false;
  btn.classList.add('on');
  rec.onresult=function(e){{
    var spoken=e.results[0][0].transcript.toLowerCase().trim();
    showScore(sid,calcScore(target.toLowerCase(),spoken,type),spoken);
    btn.classList.remove('on'); activeRec=null;
  }};
  rec.onerror=function(e){{
    btn.classList.remove('on'); activeRec=null;
    var el=document.getElementById(sid);
    if(el) el.innerHTML='<div style="color:#ef5350;font-size:.8rem;margin-top:5px;">⚠️ 오류:'+e.error+'</div>';
  }};
  rec.onend=function(){{btn.classList.remove('on');activeRec=null;}};
  rec.start();
}}

/* ── 정확도 ──────────────────────────────────────────────────────────────── */
function lev(a,b){{
  var m=a.length,n=b.length,dp=[],i,j;
  for(i=0;i<=m;i++){{dp[i]=[];for(j=0;j<=n;j++) dp[i][j]=i?j?0:i:j;}}
  for(i=1;i<=m;i++) for(j=1;j<=n;j++)
    dp[i][j]=a[i-1]===b[j-1]?dp[i-1][j-1]:1+Math.min(dp[i-1][j],dp[i][j-1],dp[i-1][j-1]);
  return dp[m][n];
}}
function calcScore(t,s,type){{
  if(type==='word') return Math.max(0,Math.round((1-lev(t,s)/Math.max(t.length,1))*100));
  var tw=t.replace(/[^a-z ]/g,'').split(' ').filter(Boolean);
  var sw=s.replace(/[^a-z ]/g,'').split(' ').filter(Boolean);
  if(!tw.length) return 0;
  var used={{}},matched=0,i,j;
  for(i=0;i<sw.length;i++) for(j=0;j<tw.length;j++)
    if(!used[j]&&(tw[j]===sw[i]||lev(tw[j],sw[i])<=1)){{matched++;used[j]=1;break;}}
  var rc=matched/tw.length,pr=sw.length?matched/sw.length:0;
  var f1=rc+pr>0?2*rc*pr/(rc+pr):0;
  var lr=Math.min(sw.length,tw.length)/Math.max(sw.length,tw.length,1);
  return Math.min(100,Math.round((f1*.75+lr*.25)*100));
}}
function showScore(id,sc,spoken){{
  var el=document.getElementById(id); if(!el) return;
  var c=sc>=80?'#66bb6a':sc>=50?'#ffa726':'#ef5350';
  el.innerHTML='<div class="sw"><div class="sl" style="color:'+c+'">정확도: '+sc+'%</div>'
    +'<div class="st"><div class="sf" style="width:'+sc+'%;background:'+c+'"></div></div>'
    +'<div class="ss">인식: "'+spoken+'"</div></div>';
}}

/* ── 렌더링 ──────────────────────────────────────────────────────────────── */
function renderWords(){{
  var c=document.getElementById('wc');
  WORDS.forEach(function(w,i){{
    var id='w'+i,sid='ws'+i,d=document.createElement('div');
    d.className='card';
    d.innerHTML='<div class="row">'
      +'<span class="num">'+(i+1)+'.</span>'
      +'<span class="kor">🇰🇷 '+w.korean+'</span>'
      +'<span style="color:#3949ab">→</span>'
      +'<button class="spk" id="sp'+id+'">🔊 '+w.word+'</button>'
      +(w.ipa?'<span class="ipa">['+w.ipa+']</span>':'')
      +'<button class="rec" id="rc'+id+'">🎤</button>'
      +'<span class="hint">말하기</span></div>'
      +(w.why?'<div class="why">💡 '+w.why+'</div>':'')
      +(w.usage?'<div class="usage">📌 "'+w.usage+'"</div>':'')
      +'<div id="'+sid+'"></div>';
    c.appendChild(d);
    document.getElementById('sp'+id).addEventListener('click',function(){{speak(w.word,.9,this);}});
    document.getElementById('rc'+id).addEventListener('click',function(){{startRec(w.word,'word',this,sid);}});
  }});
}}
function renderSents(){{
  var c=document.getElementById('sc');
  SENTS.forEach(function(s,i){{
    var id='s'+i,sid='ss'+i,d=document.createElement('div');
    d.className='card sent';
    d.innerHTML='<div class="kor">🇰🇷 '+s.ko+'</div>'
      +'<div class="en">🇺🇸 '+s.en+'</div>'
      +(s.why?'<div class="why">💡 '+s.why+'</div>':'')
      +'<div class="row" style="margin-top:7px;">'
      +'<button class="spk" id="sp'+id+'">🔊 원어민 발음</button>'
      +'<button class="rec" id="rc'+id+'">🎤</button>'
      +'<span class="hint">말하기</span></div>'
      +'<div id="'+sid+'"></div>';
    c.appendChild(d);
    document.getElementById('sp'+id).addEventListener('click',function(){{speak(s.en,.85,this);}});
    document.getElementById('rc'+id).addEventListener('click',function(){{startRec(s.en,'sentence',this,sid);}});
  }});
}}

/* ── 초기화 ──────────────────────────────────────────────────────────────── */
renderWords(); renderSents();
syn.getVoices();
if(typeof syn.onvoiceschanged!=='undefined')
  syn.onvoiceschanged=function(){{syn.getVoices();}};
document.addEventListener('visibilitychange',function(){{if(!document.hidden)syn.cancel();}});
</script>
</body></html>""")

    path=os.path.join(COMPONENT_DIR,"index.html")
    with open(path,"w",encoding="utf-8") as f: f.write(html)
    return path

# ── 커스텀 컴포넌트 선언 ───────────────────────────────────────────────────────
tts_component=components.declare_component("tts_player",path=COMPONENT_DIR)

# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    st.markdown(
        "<h1 style='text-align:center;color:#90caf9;margin-bottom:4px;'>🎓 YouTube 영어 학습기</h1>"
        "<p style='text-align:center;color:#7986cb;margin-bottom:20px;'>원어민 핵심 단어·문장 추출 + 발음 연습</p>",
        unsafe_allow_html=True)
    st.markdown("""
<div style="background:#1a237e22;border:1px solid #3949ab55;border-radius:10px;
  padding:12px 16px;margin-bottom:16px;font-size:.88rem;color:#b0bec5;">
💡 YouTube 주소 입력 → 분석 시작 | 🔊 발음 | 🎤 따라 말하기 → 정확도 표시<br>
⚠️ 음성 인식: <b>Chrome(PC/Android)</b> 또는 <b>Safari(iOS)</b>
</div>""", unsafe_allow_html=True)

    col1,col2=st.columns([5,1])
    with col1:
        url=st.text_input("YouTube URL",placeholder="https://www.youtube.com/watch?v=...",
                          label_visibility="collapsed")
    with col2:
        go=st.button("🔍 분석 시작",use_container_width=True)

    if not go or not url:
        st.markdown("<div style='text-align:center;margin-top:60px;font-size:3rem;color:#3949ab;'>🎬</div>"
                    "<p style='text-align:center;color:#546e7a;'>YouTube 주소를 입력하면 핵심 단어와 문장을 추출합니다</p>",
                    unsafe_allow_html=True); return

    video_id=extract_video_id(url)
    if not video_id: st.error("올바른 YouTube URL을 입력해주세요."); return

    with st.spinner("📥 자막 불러오는 중..."):
        transcript,method,t_err=get_transcript(video_id)
    if not transcript:
        st.error("❌ 자막 취득 실패\n\n```\n"+t_err+"\n```\n\nTED·BBC·CNN 등 영어 자막 있는 영상으로 시도해보세요."); return
    st.success(f"✅ 자막 취득 완료 ({method} · {len(transcript.split())}단어)")

    with st.spinner("🤖 Gemini가 원어민 표현 분석 중..."):
        words,sentences,err=analyze_transcript(transcript)
    if err=="NO_KEY":
        st.error("❌ GEMINI_API_KEY 미설정\nhttps://aistudio.google.com/app/apikey 에서 발급 후\n"
                 "Streamlit Cloud Secrets에 추가:\n```\nGEMINI_API_KEY = \"AIza...\"\n```"); return
    if err: st.error(f"❌ Gemini API 오류: {err}"); return
    if not words and not sentences: st.error("분석 결과가 없습니다. 다시 시도해주세요."); return

    # HTML 파일 생성 후 커스텀 컴포넌트로 렌더링
    # declare_component(path=...) 는 해당 디렉토리의 index.html을 서빙
    # → 같은 origin으로 iframe 생성 → speechSynthesis 차단 없음
    write_component(words, sentences, video_id)
    tts_component(height=1900, scrolling=True)

if __name__=="__main__":
    main()
