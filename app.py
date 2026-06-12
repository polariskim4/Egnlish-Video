import streamlit as st
import streamlit.components.v1 as components
import re, json

st.set_page_config(page_title="YouTube 영어 학습기", page_icon="🎓", layout="wide")
st.markdown("""
<style>
  .stApp { background:#0f1117; color:#e8eaf6; }
  .stButton>button {
    background:linear-gradient(135deg,#3949ab,#7c4dff)!important;
    color:#fff!important; border:none!important;
    border-radius:10px!important; font-weight:600!important;
  }
  .stTextInput>div>div>input {
    background:#1e2130!important; color:#e8eaf6!important;
    border:1px solid #3949ab!important; border-radius:10px!important;
  }
</style>
""", unsafe_allow_html=True)

# ── YouTube ID 추출 ────────────────────────────────────────────────────────────
def extract_video_id(url):
    for p in [r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
              r"^([A-Za-z0-9_-]{11})$"]:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

# ── VTT 파싱 ──────────────────────────────────────────────────────────────────
def parse_vtt_text(raw):
    lines, seen, out = [], set(), []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "-->" in line or line.startswith("WEBVTT") or re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line and line not in seen:
            seen.add(line); out.append(line)
    return " ".join(out)

# ── 자막 취득 (4단계 폴백) ────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_transcript(video_id):
    errors = []

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tl = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in ["en","en-US","en-GB"]:
            try:
                segs = tl.find_transcript([lang]).fetch()
                text = " ".join(s["text"] for s in segs)
                if len(text) > 100: return text, "transcript-api", ""
            except: pass
        for t in tl:
            if t.language_code.startswith("en"):
                segs = t.fetch()
                text = " ".join(s["text"] for s in segs)
                if len(text) > 100: return text, "auto-caption", ""
        errors.append("transcript-api: 영어 자막 없음")
    except Exception as e:
        errors.append(f"transcript-api: {e}")

    try:
        import yt_dlp, tempfile, os, glob
        tmp = tempfile.mkdtemp()
        opts = {
            "skip_download": True, "writeautomaticsub": True,
            "writesubtitles": True, "subtitleslangs": ["en","en-US","en-GB"],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmp,"sub_%(id)s.%(ext)s"),
            "quiet": True, "no_warnings": True, "socket_timeout": 30,
            "http_headers": {"User-Agent":"com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"},
            "extractor_args": {"youtube": {"player_client": ["android","web"]}},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        vtt_files = glob.glob(os.path.join(tmp,f"sub_{video_id}*.vtt"))
        if vtt_files:
            text = parse_vtt_text(open(vtt_files[0],encoding="utf-8").read())
            if len(text) > 100: return text, "yt-dlp", ""
        errors.append("yt-dlp: VTT 없음")
    except Exception as e:
        errors.append(f"yt-dlp: {e}")

    try:
        import requests
        r = requests.get("https://api.supadata.ai/v1/youtube/transcript",
                         params={"videoId":video_id,"lang":"en"}, timeout=20)
        if r.status_code == 200:
            d = r.json(); content = d.get("content", d.get("transcript",""))
            text = " ".join(c.get("text","") for c in content) if isinstance(content,list) else str(content)
            if len(text) > 100: return text, "supadata", ""
        errors.append(f"supadata: {r.status_code}")
    except Exception as e:
        errors.append(f"supadata: {e}")

    try:
        import requests
        r = requests.get(f"https://youtubetranscript.com/?server_vid2={video_id}",
                         timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200 and "<text" in r.text:
            texts = re.findall(r"<text[^>]*>(.*?)</text>", r.text, re.DOTALL)
            text = " ".join(re.sub(r"&[a-z]+;", " ", t).strip() for t in texts)
            if len(text) > 100: return text, "youtubetranscript.com", ""
        errors.append("youtubetranscript.com: 파싱 실패")
    except Exception as e:
        errors.append(f"youtubetranscript.com: {e}")

    return "", "failed", " | ".join(errors)

# ── API 키 ─────────────────────────────────────────────────────────────────────
def get_api_key():
    import os
    try:
        k = st.secrets.get("GEMINI_API_KEY","")
        if k: return k
    except: pass
    return os.environ.get("GEMINI_API_KEY","")

# ── Gemini 분석 ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def analyze_transcript(transcript):
    import requests, time
    api_key = get_api_key()
    if not api_key: return [], [], "NO_KEY"

    prompt = f"""아래는 YouTube 영상의 영어 자막입니다.

<transcript>
{transcript[:6000]}
</transcript>

다음 두 가지를 분석해 JSON으로만 응답하세요 (마크다운 코드블록 없이 순수 JSON).

### 단어 (10개) 선정 기준
- ❌ 제외: good, bad, big, important, people, time, make, know, think, go, see, want, need 등 기초 어휘
- ✅ 포함: 구동사, 관용구, 콜로케이션, 원어민 구어 특유 어휘, 반복 등장 전문용어

### 문장 (10개) 선정 기준
- ❌ 제외: "This is important.", "Let me explain…" 등 단순 구조
- ✅ 포함: 도치·분열문, 구어체 생략, 원어민 특유 연결어, 관용 비유

출력 형식:
{{
  "words": [
    {{"word":"단어","ipa":"IPA","korean":"한국어 뜻","usage":"예문","why":"원어민 특유 이유"}}
  ],
  "sentences": [
    {{"en":"영어 원문","ko":"한국어 번역","why":"원어민 표현 이유"}}
  ]
}}"""

    MODELS = ["gemini-3.5-flash","gemini-3.1-flash-lite","gemini-2.5-flash"]
    last_err = "알 수 없는 오류"

    for model in MODELS:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        payload = {"contents":[{"parts":[{"text":prompt}]}],
                   "generationConfig":{"maxOutputTokens":2000,"temperature":0.2}}
        for attempt in range(3):
            try:
                r = requests.post(url, json=payload, timeout=60)
                if r.status_code == 429:
                    wait = min(int(r.headers.get("Retry-After", 2**(attempt+1))), 30)
                    last_err = f"{model}: 429 한도 초과, {wait}초 대기"
                    time.sleep(wait); continue
                if r.status_code == 404:
                    last_err = f"{model}: 404 모델 없음"; break
                r.raise_for_status()
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = re.sub(r"^```[a-z]*","",raw); raw = re.sub(r"```$","",raw).strip()
                data = json.loads(raw)
                return data.get("words",[]), data.get("sentences",[]), ""
            except Exception as e:
                last_err = f"{model} 시도{attempt+1}: {e}"
                if attempt < 2: time.sleep(2**attempt)

    return [], [], f"모든 모델 실패 — {last_err}"

# ── TTS 전용 컴포넌트 (height=0, 숨김) ────────────────────────────────────────
# iframe이지만 같은 window.parent를 공유 → UI 컴포넌트로부터 postMessage 수신
TTS_COMPONENT_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body>
<script>
(function(){
  var synth = window.speechSynthesis;
  var iosTimer = null;

  function pickVoice(){
    var vs = synth.getVoices();
    return vs.find(function(v){ return v.lang==='en-US' && v.name.indexOf('Google')!==-1; })
        || vs.find(function(v){ return v.name==='Samantha'; })
        || vs.find(function(v){ return v.lang==='en-US'; })
        || vs.find(function(v){ return v.lang.indexOf('en')===0; })
        || null;
  }

  function speak(text, rate){
    synth.cancel();
    if(iosTimer){ clearInterval(iosTimer); iosTimer=null; }

    function go(){
      var u = new SpeechSynthesisUtterance(text);
      u.lang='en-US'; u.rate=rate||0.9; u.volume=1; u.pitch=1;
      var v=pickVoice(); if(v) u.voice=v;

      u.onstart=function(){
        iosTimer=setInterval(function(){
          if(synth.paused) synth.resume();
        },5000);
        // UI 컴포넌트에 재생 시작 알림
        broadcast('tts_start');
      };
      u.onend=function(){
        if(iosTimer){clearInterval(iosTimer);iosTimer=null;}
        broadcast('tts_end');
      };
      u.onerror=function(e){
        if(iosTimer){clearInterval(iosTimer);iosTimer=null;}
        if(e.error!=='interrupted'&&e.error!=='canceled') broadcast('tts_end');
      };
      synth.resume();
      synth.speak(u);
    }

    var voices=synth.getVoices();
    if(voices.length>0){ go(); }
    else{
      var t=setTimeout(go,300);
      synth.onvoiceschanged=function(){ synth.onvoiceschanged=null; clearTimeout(t); go(); };
    }
  }

  function broadcast(type){
    // window.parent 아래 모든 iframe에 알림 (UI 컴포넌트 포함)
    try{
      var frames=window.parent.document.querySelectorAll('iframe');
      for(var i=0;i<frames.length;i++){
        try{ frames[i].contentWindow.postMessage({type:type},'*'); }catch(e){}
      }
    }catch(e){}
  }

  // window.parent를 통해 UI 컴포넌트로부터 tts_speak 메시지 수신
  window.addEventListener('message',function(e){
    if(!e.data||typeof e.data!=='object') return;
    if(e.data.type==='tts_speak') speak(e.data.text, e.data.rate);
    if(e.data.type==='tts_stop'){
      synth.cancel();
      if(iosTimer){clearInterval(iosTimer);iosTimer=null;}
    }
  });

  // 오디오 잠금 해제 (모바일)
  function unlock(){
    var u=new SpeechSynthesisUtterance(''); u.volume=0;
    synth.speak(u); synth.cancel();
  }
  document.addEventListener('click', unlock, {once:true});
  document.addEventListener('touchstart', unlock, {once:true});

  // 목소리 미리 로드
  synth.getVoices();
  if(typeof synth.onvoiceschanged!=='undefined')
    synth.onvoiceschanged=function(){ synth.getVoices(); };

  document.addEventListener('visibilitychange',function(){
    if(!document.hidden) synth.cancel();
  });
})();
</script>
</body></html>"""

# ── UI 카드 컴포넌트 ───────────────────────────────────────────────────────────
def build_ui_html(words, sentences, video_id):
    wj = json.dumps(words, ensure_ascii=False)
    sj = json.dumps(sentences, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:#0f1117;color:#e8eaf6;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:16px;}}
  h2{{color:#90caf9;font-size:1.1rem;font-weight:700;
    border-bottom:2px solid #3949ab;padding-bottom:6px;margin:20px 0 12px;}}
  .card{{background:#1e2130;border-radius:12px;padding:14px 18px;
    margin:10px 0;border:1px solid #2d3250;}}
  .row{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px;}}
  .num{{color:#7986cb;font-weight:700;min-width:22px;}}
  .kor{{color:#a5d6a7;font-weight:700;font-size:.95rem;}}
  .ipa{{color:#90caf9;font-size:.85rem;}}
  .why{{color:#ffcc80;font-size:.8rem;margin:5px 0;}}
  .usage{{background:#0d1021;border-radius:6px;padding:5px 10px;
    color:#90caf9;font-size:.82rem;font-style:italic;margin-top:4px;}}
  .en-text{{color:#cfd8dc;font-size:.88rem;margin:4px 0 8px;line-height:1.5;}}
  button{{cursor:pointer;border:none;outline:none;-webkit-tap-highlight-color:transparent;}}
  .spk{{background:#3949ab;color:#fff;border-radius:8px;
    padding:6px 14px;font-size:.9rem;font-weight:600;transition:background .15s;}}
  .spk:active{{background:#283593;transform:scale(.97);}}
  .spk.playing{{background:#1565c0;animation:sp .6s ease infinite alternate;}}
  @keyframes sp{{from{{box-shadow:0 0 0 0 #42a5f566;}}to{{box-shadow:0 0 0 8px #42a5f500;}}}}
  .rec{{background:#c62828;color:#fff;border-radius:50%;
    width:44px;height:44px;font-size:1.3rem;flex-shrink:0;}}
  .rec:active{{transform:scale(.93);}}
  .rec.recording{{background:#b71c1c;animation:rp 1s ease infinite;}}
  @keyframes rp{{0%,100%{{box-shadow:0 0 0 0 #c6282855;}}50%{{box-shadow:0 0 0 10px #c6282800;}}}}
  .score-wrap{{margin-top:10px;}}
  .score-lbl{{font-weight:700;font-size:.95rem;margin-bottom:3px;}}
  .score-trk{{height:10px;border-radius:5px;background:#2d3250;overflow:hidden;}}
  .score-fill{{height:10px;border-radius:5px;transition:width .6s ease;}}
  .score-spk{{color:#b0bec5;font-size:.78rem;margin-top:4px;}}
  .hint{{color:#7986cb;font-size:.78rem;}}
  iframe{{border-radius:10px;margin-bottom:16px;}}
</style></head><body>

<iframe width="100%" height="240"
  src="https://www.youtube.com/embed/{video_id}"
  frameborder="0" allowfullscreen></iframe>

<h2>📚 핵심 단어 TOP 10</h2>
<p style="color:#7986cb;font-size:.8rem;margin-bottom:10px;">
  🇰🇷 뜻 → 🇺🇸 단어 | 🔊 발음 | 🎤 따라하기</p>
<div id="wc"></div>

<h2 style="margin-top:24px;">💬 핵심 문장 TOP 10</h2>
<p style="color:#7986cb;font-size:.8rem;margin-bottom:10px;">
  🇰🇷 번역 → 🇺🇸 원문 | 🔊 발음 | 🎤 따라하기</p>
<div id="sc"></div>

<script>
var WORDS={wj};
var SENTS={sj};
var curSpkBtn=null;

// TTS 요청: window.parent 를 통해 TTS 전용 iframe으로 브로드캐스트
function speak(text,rate,btn){{
  if(curSpkBtn&&curSpkBtn!==btn) curSpkBtn.classList.remove('playing');
  curSpkBtn=btn;
  window.parent.postMessage({{type:'tts_speak',text:text,rate:rate||0.9}},'*');
}}

// TTS 상태 수신 (TTS iframe이 window.parent를 통해 전달)
window.addEventListener('message',function(e){{
  if(!e.data||typeof e.data!=='object') return;
  if(e.data.type==='tts_start'){{ if(curSpkBtn) curSpkBtn.classList.add('playing'); }}
  else if(e.data.type==='tts_end'){{ if(curSpkBtn) curSpkBtn.classList.remove('playing'); curSpkBtn=null; }}
}});

// 음성 인식
var activeRec=null;
function startRec(target,type,btn,sid){{
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){{
    var el=document.getElementById(sid);
    if(el) el.innerHTML='<div style="color:#ffa726;font-size:.82rem;margin-top:6px;">⚠️ Android Chrome 또는 iOS Safari에서 지원</div>';
    return;
  }}
  if(activeRec){{ activeRec.stop(); activeRec=null; btn.classList.remove('recording'); return; }}
  var rec=new SR(); activeRec=rec;
  rec.lang='en-US'; rec.continuous=false; rec.interimResults=false; rec.maxAlternatives=1;
  btn.classList.add('recording');
  rec.onresult=function(e){{
    var spoken=e.results[0][0].transcript.toLowerCase().trim();
    showScore(sid,calcScore(target.toLowerCase(),spoken,type),spoken);
    btn.classList.remove('recording'); activeRec=null;
  }};
  rec.onerror=function(e){{
    btn.classList.remove('recording'); activeRec=null;
    var el=document.getElementById(sid);
    if(el) el.innerHTML='<div style="color:#ef5350;font-size:.82rem;margin-top:6px;">⚠️ 오류: '+e.error+'</div>';
  }};
  rec.onend=function(){{ btn.classList.remove('recording'); activeRec=null; }};
  rec.start();
}}

function lev(a,b){{
  var m=a.length,n=b.length;
  var dp=[];
  for(var i=0;i<=m;i++){{ dp[i]=[]; for(var j=0;j<=n;j++) dp[i][j]=i||j; }}
  for(var i=1;i<=m;i++) for(var j=1;j<=n;j++)
    dp[i][j]=a[i-1]===b[j-1]?dp[i-1][j-1]:1+Math.min(dp[i-1][j],dp[i][j-1],dp[i-1][j-1]);
  return dp[m][n];
}}
function calcScore(t,s,type){{
  if(type==='word') return Math.max(0,Math.round((1-lev(t,s)/Math.max(t.length,1))*100));
  var tw=t.replace(/[^a-z ]/g,'').split(/ +/).filter(Boolean);
  var sw=s.replace(/[^a-z ]/g,'').split(/ +/).filter(Boolean);
  if(!tw.length) return 0;
  var used={{}},matched=0;
  for(var i=0;i<sw.length;i++){{
    for(var j=0;j<tw.length;j++){{
      if(!used[j]&&(tw[j]===sw[i]||lev(tw[j],sw[i])<=1)){{ matched++; used[j]=1; break; }}
    }}
  }}
  var rec=matched/tw.length, prec=sw.length?matched/sw.length:0;
  var f1=rec+prec>0?2*rec*prec/(rec+prec):0;
  var lr=Math.min(sw.length,tw.length)/Math.max(sw.length,tw.length,1);
  return Math.min(100,Math.round((f1*.75+lr*.25)*100));
}}
function showScore(id,score,spoken){{
  var el=document.getElementById(id); if(!el) return;
  var c=score>=80?'#66bb6a':score>=50?'#ffa726':'#ef5350';
  el.innerHTML='<div class="score-wrap"><div class="score-lbl" style="color:'+c+'">정확도: '+score+'%</div>'
    +'<div class="score-trk"><div class="score-fill" style="width:'+score+'%;background:'+c+'"></div></div>'
    +'<div class="score-spk">인식된 음성: "'+spoken+'"</div></div>';
}}

function renderWords(){{
  var c=document.getElementById('wc');
  for(var i=0;i<WORDS.length;i++){{
    (function(w,i){{
      var id='w'+i, sid='ws'+i;
      var d=document.createElement('div'); d.className='card';
      d.innerHTML='<div class="row">'
        +'<span class="num">'+(i+1)+'.</span>'
        +'<span class="kor">🇰🇷 '+w.korean+'</span>'
        +'<span style="color:#3949ab">→</span>'
        +'<button class="spk" id="spk_'+id+'">🔊 '+w.word+'</button>'
        +(w.ipa?'<span class="ipa">['+w.ipa+']</span>':'')
        +'<button class="rec" id="rec_'+id+'">🎤</button>'
        +'<span class="hint">말하기</span></div>'
        +(w.why?'<div class="why">💡 '+w.why+'</div>':'')
        +(w.usage?'<div class="usage">📌 "'+w.usage+'"</div>':'')
        +'<div id="'+sid+'"></div>';
      c.appendChild(d);
      document.getElementById('spk_'+id).addEventListener('click',function(){{ speak(w.word,0.9,this); }});
      document.getElementById('rec_'+id).addEventListener('click',function(){{ startRec(w.word,'word',this,sid); }});
    }})(WORDS[i],i);
  }}
}}
function renderSents(){{
  var c=document.getElementById('sc');
  for(var i=0;i<SENTS.length;i++){{
    (function(s,i){{
      var id='s'+i, sid='ss'+i;
      var d=document.createElement('div'); d.className='card'; d.style.borderLeft='3px solid #5c6bc0';
      d.innerHTML='<div class="kor">🇰🇷 '+s.ko+'</div>'
        +'<div class="en-text">🇺🇸 '+s.en+'</div>'
        +(s.why?'<div class="why">💡 '+s.why+'</div>':'')
        +'<div class="row" style="margin-top:8px;">'
        +'<button class="spk" id="spk_'+id+'">🔊 원어민 발음</button>'
        +'<button class="rec" id="rec_'+id+'">🎤</button>'
        +'<span class="hint">말하기</span></div>'
        +'<div id="'+sid+'"></div>';
      c.appendChild(d);
      document.getElementById('spk_'+id).addEventListener('click',function(){{ speak(s.en,0.85,this); }});
      document.getElementById('rec_'+id).addEventListener('click',function(){{ startRec(s.en,'sentence',this,sid); }});
    }})(SENTS[i],i);
  }}
}}

renderWords();
renderSents();
</script></body></html>"""

# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    st.markdown(
        "<h1 style='text-align:center;color:#90caf9;margin-bottom:4px;'>🎓 YouTube 영어 학습기</h1>"
        "<p style='text-align:center;color:#7986cb;margin-bottom:20px;'>원어민 핵심 단어·문장 추출 + 발음 연습</p>",
        unsafe_allow_html=True)
    st.markdown("""
<div style="background:#1a237e22;border:1px solid #3949ab55;border-radius:10px;
  padding:12px 16px;margin-bottom:16px;font-size:.88rem;color:#b0bec5;">
💡 YouTube 주소 입력 → 분석 시작 | 🔊 발음 듣기 | 🎤 따라 말하기 → 정확도 표시<br>
⚠️ 음성 인식: <b>Chrome(PC/Android)</b> 또는 <b>Safari(iOS)</b>
</div>""", unsafe_allow_html=True)

    col1, col2 = st.columns([5,1])
    with col1:
        url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...",
                            label_visibility="collapsed")
    with col2:
        go = st.button("🔍 분석 시작", use_container_width=True)

    if not go or not url:
        st.markdown(
            "<div style='text-align:center;margin-top:60px;font-size:3rem;color:#3949ab;'>🎬</div>"
            "<p style='text-align:center;color:#546e7a;'>YouTube 주소를 입력하면 핵심 단어와 문장을 추출합니다</p>",
            unsafe_allow_html=True)
        return

    video_id = extract_video_id(url)
    if not video_id:
        st.error("올바른 YouTube URL을 입력해주세요."); return

    with st.spinner("📥 자막 불러오는 중... (최대 30초)"):
        transcript, method, t_err = get_transcript(video_id)

    if not transcript:
        st.error("❌ 자막 취득 실패\n\n```\n" + t_err + "\n```\n\n"
                 "영어 자막이 있는 영상(TED·BBC·CNN 등)으로 시도해보세요."); return

    st.success(f"✅ 자막 취득 완료 ({method} · {len(transcript.split())}단어)")

    with st.spinner("🤖 Gemini가 원어민 표현 분석 중..."):
        words, sentences, err = analyze_transcript(transcript)

    if err == "NO_KEY":
        st.error("❌ GEMINI_API_KEY 미설정\n\nhttps://aistudio.google.com/app/apikey 에서 발급 후\n"
                 "Streamlit Cloud → Settings → Secrets 에 추가:\n```\nGEMINI_API_KEY = \"AIza...\"\n```"); return
    if err:
        st.error(f"❌ Gemini API 오류: {err}"); return
    if not words and not sentences:
        st.error("분석 결과가 없습니다. 다시 시도해주세요."); return

    # ① TTS 전용 컴포넌트 (height=0 숨김) — 실제 speechSynthesis 실행 담당
    components.html(TTS_COMPONENT_HTML, height=0)

    # ② UI 카드 컴포넌트 — TTS 요청은 postMessage → window.parent → TTS 컴포넌트
    ui_html = build_ui_html(words, sentences, video_id)
    components.html(ui_html, height=1900, scrolling=True)

if __name__ == "__main__":
    main()
