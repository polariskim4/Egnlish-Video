import streamlit as st
import streamlit.components.v1 as components
import re
import json

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="YouTube 영어 학습기", page_icon="🎓", layout="wide")

st.markdown("""
<style>
  .stApp { background:#0f1117; color:#e8eaf6; }
  .stButton>button {
    background:linear-gradient(135deg,#3949ab,#7c4dff)!important;
    color:#fff!important; border:none!important; border-radius:10px!important;
    font-weight:600!important;
  }
  .stTextInput>div>div>input {
    background:#1e2130!important; color:#e8eaf6!important;
    border:1px solid #3949ab!important; border-radius:10px!important;
  }
</style>
""", unsafe_allow_html=True)

# ── YouTube ID 추출 ───────────────────────────────────────────────────────────
def extract_video_id(url: str) -> str | None:
    for p in [r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
              r"^([A-Za-z0-9_-]{11})$"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ── VTT 파싱 헬퍼 ────────────────────────────────────────────────────────────
def parse_vtt_text(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "-->" in line or line.startswith("WEBVTT") or re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"&amp;", "&", line)
        if line:
            lines.append(line)
    # 중복 줄 제거 (자동자막 중복 많음)
    seen, deduped = set(), []
    for l in lines:
        if l not in seen:
            seen.add(l); deduped.append(l)
    return " ".join(deduped)

# ── 자막 취득 ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_transcript(video_id: str) -> tuple[str, str, str]:
    """(text, method, error_detail) 반환"""
    errors = []

    # ── 방법 1: youtube-transcript-api (가장 가벼움, Streamlit Cloud에서 잘 됨)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
        tl = YouTubeTranscriptApi.list_transcripts(video_id)
        # 수동 영어 자막 우선
        for lang in ["en", "en-US", "en-GB"]:
            try:
                segs = tl.find_transcript([lang]).fetch()
                text = " ".join(s["text"] for s in segs)
                if len(text) > 100:
                    return text, "transcript-api (수동자막)", ""
            except Exception:
                pass
        # 자동생성 자막
        for t in tl:
            if t.language_code.startswith("en"):
                segs = t.fetch()
                text = " ".join(s["text"] for s in segs)
                if len(text) > 100:
                    return text, f"transcript-api (자동:{t.language_code})", ""
        errors.append("transcript-api: 영어 자막 없음")
    except Exception as e:
        errors.append(f"transcript-api: {e}")

    # ── 방법 2: yt-dlp (User-Agent + android client 우회)
    try:
        import yt_dlp, tempfile, os, glob
        tmp = tempfile.mkdtemp()
        opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmp, "sub_%(id)s.%(ext)s"),
            "quiet": True, "no_warnings": True,
            "socket_timeout": 30,
            "http_headers": {
                "User-Agent": (
                    "com.google.android.youtube/19.09.37 "
                    "(Linux; U; Android 11) gzip"
                )
            },
            "extractor_args": {
                "youtube": {"player_client": ["android", "web"]}
            },
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        vtt_files = glob.glob(os.path.join(tmp, f"sub_{video_id}*.vtt"))
        if vtt_files:
            raw = open(vtt_files[0], encoding="utf-8").read()
            text = parse_vtt_text(raw)
            for fv in glob.glob(os.path.join(tmp, "*")):
                try: os.remove(fv)
                except: pass
            if len(text) > 100:
                return text, "yt-dlp", ""
        errors.append("yt-dlp: VTT 파일 없음")
    except Exception as e:
        errors.append(f"yt-dlp: {e}")

    # ── 방법 3: Supadata 무료 API (서드파티, 별도 인증 불필요)
    try:
        import requests
        r = requests.get(
            "https://api.supadata.ai/v1/youtube/transcript",
            params={"videoId": video_id, "lang": "en"},
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            # content 는 list[{text}] 또는 str
            content = data.get("content", data.get("transcript", ""))
            if isinstance(content, list):
                text = " ".join(c.get("text","") for c in content)
            else:
                text = str(content)
            if len(text) > 100:
                return text, "supadata-api", ""
        errors.append(f"supadata: HTTP {r.status_code}")
    except Exception as e:
        errors.append(f"supadata: {e}")

    # ── 방법 4: YouTubeTranscript.io 무료 엔드포인트
    try:
        import requests
        r = requests.get(
            f"https://youtubetranscript.com/?server_vid2={video_id}",
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200 and "<text" in r.text:
            texts = re.findall(r"<text[^>]*>(.*?)</text>", r.text, re.DOTALL)
            text = " ".join(
                re.sub(r"&[a-z]+;", " ", t).strip() for t in texts
            )
            if len(text) > 100:
                return text, "youtubetranscript.com", ""
        errors.append(f"youtubetranscript.com: 파싱 실패")
    except Exception as e:
        errors.append(f"youtubetranscript.com: {e}")

    return "", "failed", " | ".join(errors)

# ── API 키 로딩 (Gemini) ─────────────────────────────────────────────────────
def get_api_key() -> str:
    import os
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "")

# ── Gemini 분석 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def analyze_with_claude(transcript: str) -> tuple[list[dict], list[dict], str]:
    import requests
    api_key = get_api_key()
    if not api_key:
        return [], [], "NO_KEY"
    sample = transcript[:6000]
    prompt = f"""아래는 YouTube 영상의 영어 자막입니다.

<transcript>
{sample}
</transcript>

다음 두 가지를 분석해 JSON으로만 응답하세요 (마크다운 코드블록 없이 순수 JSON).

### 단어 (10개) 선정 기준
- ❌ 제외: good, bad, big, important, different, people, things, time, make, take, know, think, go, see, want, need, great, real 등 초등~중학교 수준 기초 어휘
- ✅ 포함: 구동사(double down, pan out…), 관용구(off the cuff, on the fence…), 콜로케이션(stark contrast, pivotal role…), 원어민 구어 특유 어휘(gloss over, hedge, conflate, reckon…), 반복 등장 전문용어

### 문장 (10개) 선정 기준
- ❌ 제외: "This is important.", "In this video I will…", "Let me explain…" 등 단순 구조
- ✅ 포함: 도치·분열문, 구어체 생략(Not gonna lie…, Thing is,…), 원어민 특유 연결어(mind you, that said, go figure…), 관용 비유

출력 형식:
{{
  "words": [
    {{
      "word": "단어 또는 구동사/관용구",
      "ipa": "IPA 발음기호",
      "korean": "한국어 뜻 1~2가지",
      "usage": "자막 속 짧은 예문",
      "why": "원어민 특유인 이유 (한국어 한 줄)"
    }}
  ],
  "sentences": [
    {{
      "en": "영어 원문",
      "ko": "자연스러운 한국어 번역",
      "why": "원어민 표현인 이유 (한국어 한 줄)"
    }}
  ]
}}"""
    # 429 대비: gemini-2.0-flash → gemini-1.5-flash → gemini-1.5-pro 순 폴백
    MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
    import time

    last_err = "알 수 없는 오류"  # UnboundLocalError 방지

    for model in MODELS:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 2000, "temperature": 0.2},
        }
        for attempt in range(3):
            try:
                r = requests.post(url, json=payload, timeout=60)
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 2 ** (attempt + 1)))
                    wait = min(wait, 30)
                    last_err = f"{model}: 429 한도 초과, {wait}초 대기"
                    time.sleep(wait)
                    continue
                if r.status_code == 404:
                    last_err = f"{model}: 404 모델 없음"
                    break
                r.raise_for_status()
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = re.sub(r"^```[a-z]*", "", raw)
                raw = re.sub(r"```$", "", raw).strip()
                data = json.loads(raw)
                return data.get("words", []), data.get("sentences", []), ""
            except Exception as e:
                last_err = f"{model} 시도{attempt+1}: {e}"
                if attempt < 2:
                    time.sleep(2 ** attempt)

    return [], [], f"모든 모델 실패 — {last_err}"

# ── 인터랙티브 컴포넌트 HTML 생성 ────────────────────────────────────────────
# ── TTS 브리지: Streamlit 메인 페이지에 inject (cross-origin iframe 우회) ─────
# 안드로이드 크롬은 iframe 내부 speechSynthesis 완전 차단
# → iframe에서 postMessage로 텍스트 전달 → 부모(Streamlit) 페이지에서 재생
TTS_BRIDGE_JS = """
<script>
(function() {
  // ── 중복 inject 방지 ──────────────────────────────────────────────────────
  if (window.__ttsBridgeReady) return;
  window.__ttsBridgeReady = true;

  let iosTimer = null;
  let activeBtn = null;   // 현재 재생 중인 버튼 참조(postMessage로 못 넘기므로 null)

  function pickVoice() {
    const vs = window.speechSynthesis.getVoices();
    return vs.find(v => v.lang === 'en-US' && v.name.includes('Google'))
        || vs.find(v => v.name === 'Samantha')
        || vs.find(v => v.lang === 'en-US')
        || vs.find(v => v.lang.startsWith('en'))
        || null;
  }

  function doSpeak(text, rate) {
    window.speechSynthesis.cancel();
    if (iosTimer) { clearInterval(iosTimer); iosTimer = null; }

    const u = new SpeechSynthesisUtterance(text);
    u.lang   = 'en-US';
    u.rate   = rate  || 0.9;
    u.volume = 1;
    u.pitch  = 1;

    // 목소리 로드 대기 (모바일 지연 대응)
    function go() {
      const v = pickVoice();
      if (v) u.voice = v;
      u.onstart = () => {
        // iOS 15초 중단 버그 방지
        iosTimer = setInterval(() => {
          if (window.speechSynthesis.paused) window.speechSynthesis.resume();
        }, 5000);
        // iframe에 재생 시작 알림
        notifyIframe('tts_start');
      };
      u.onend = u.onerror = (e) => {
        if (iosTimer) { clearInterval(iosTimer); iosTimer = null; }
        notifyIframe('tts_end');
        if (e.error && e.error !== 'interrupted' && e.error !== 'canceled')
          console.warn('TTS:', e.error);
      };
      window.speechSynthesis.resume();
      window.speechSynthesis.speak(u);
    }

    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      go();
    } else {
      const t = setTimeout(go, 200);
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.onvoiceschanged = null;
        clearTimeout(t); go();
      };
    }
  }

  function notifyIframe(type) {
    // Streamlit component iframe에 메시지 전달
    const frames = document.querySelectorAll('iframe');
    frames.forEach(f => {
      try { f.contentWindow.postMessage({ type }, '*'); } catch(e) {}
    });
  }

  // ── iframe → 부모 메시지 수신 ──────────────────────────────────────────────
  window.addEventListener('message', (e) => {
    const d = e.data;
    if (!d || typeof d !== 'object') return;
    if (d.type === 'tts_speak') {
      doSpeak(d.text, d.rate);
    } else if (d.type === 'tts_stop') {
      window.speechSynthesis.cancel();
      if (iosTimer) { clearInterval(iosTimer); iosTimer = null; }
      notifyIframe('tts_end');
    }
  });

  // 첫 클릭/탭으로 오디오 잠금 해제 (모바일 필수)
  function unlock() {
    if (window.speechSynthesis) {
      const u = new SpeechSynthesisUtterance('');
      u.volume = 0;
      window.speechSynthesis.speak(u);
      window.speechSynthesis.cancel();
    }
  }
  document.addEventListener('click',      unlock, { once: true });
  document.addEventListener('touchstart', unlock, { once: true });

  // visibilitychange: 백→포그라운드 복귀 시 리셋
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) window.speechSynthesis.cancel();
  });

  // 목소리 미리 로드
  window.speechSynthesis.getVoices();
  if (typeof window.speechSynthesis.onvoiceschanged !== 'undefined')
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
})();
</script>
"""

def build_component_html(words: list[dict], sentences: list[dict], video_id: str) -> str:
    words_json = json.dumps(words, ensure_ascii=False)
    sents_json = json.dumps(sentences, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{
    background:#0f1117; color:#e8eaf6;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    padding:16px;
  }}
  h2 {{
    color:#90caf9; font-size:1.1rem; font-weight:700;
    border-bottom:2px solid #3949ab; padding-bottom:6px; margin:20px 0 12px;
  }}
  .card {{
    background:#1e2130; border-radius:12px; padding:14px 18px;
    margin:10px 0; border:1px solid #2d3250;
  }}
  .row {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:4px; }}
  .num {{ color:#7986cb; font-weight:700; min-width:22px; }}
  .korean {{ color:#a5d6a7; font-weight:700; font-size:.95rem; }}
  .ipa {{ color:#90caf9; font-size:.85rem; }}
  .why {{ color:#ffcc80; font-size:.8rem; margin:5px 0; }}
  .usage {{
    background:#0d1021; border-radius:6px; padding:5px 10px;
    color:#90caf9; font-size:.82rem; font-style:italic; margin-top:4px;
  }}
  .en-text {{ color:#cfd8dc; font-size:.88rem; margin:4px 0 8px; line-height:1.5; }}

  button {{ cursor:pointer; border:none; outline:none; }}

  .speak-btn {{
    background:#3949ab; color:#fff; border-radius:8px;
    padding:5px 13px; font-size:.9rem; font-weight:600;
    transition:background .15s;
    -webkit-tap-highlight-color: transparent;
  }}
  .speak-btn:hover {{ background:#5c6bc0; }}
  .speak-btn:active {{ background:#283593; transform:scale(.97); }}
  .speak-btn.playing {{
    background:#1565c0;
    animation:speakPulse .6s ease infinite alternate;
  }}
  @keyframes speakPulse {{
    from {{ box-shadow:0 0 0 0 #42a5f566; }}
    to   {{ box-shadow:0 0 0 8px #42a5f500; }}
  }}

  .rec-btn {{
    background:#c62828; color:#fff;
    border-radius:50%; width:44px; height:44px;
    font-size:1.3rem; flex-shrink:0;
    -webkit-tap-highlight-color: transparent;
  }}
  .rec-btn:active {{ transform:scale(.93); }}
  .rec-btn.recording {{
    background:#b71c1c;
    animation:recPulse 1s ease infinite;
  }}
  @keyframes recPulse {{
    0%,100% {{ box-shadow:0 0 0 0 #c6282855; }}
    50%      {{ box-shadow:0 0 0 10px #c6282800; }}
  }}

  .score-wrap {{ margin-top:10px; }}
  .score-label {{ font-weight:700; font-size:.95rem; margin-bottom:3px; }}
  .score-track {{ height:10px; border-radius:5px; background:#2d3250; overflow:hidden; }}
  .score-fill {{ height:10px; border-radius:5px; transition:width .6s ease; }}
  .score-spoken {{ color:#b0bec5; font-size:.78rem; margin-top:4px; }}
  .hint {{ color:#7986cb; font-size:.78rem; }}
  iframe {{ border-radius:10px; margin-bottom:16px; }}
</style>
</head>
<body>

<iframe width="100%" height="240"
  src="https://www.youtube.com/embed/{video_id}"
  frameborder="0" allowfullscreen></iframe>

<h2>📚 핵심 단어 TOP 10</h2>
<p style="color:#7986cb;font-size:.8rem;margin-bottom:10px;">
  🇰🇷 뜻 → 🇺🇸 단어 | 🔊 발음 | 🎤 따라하기
</p>
<div id="words-container"></div>

<h2 style="margin-top:24px;">💬 핵심 문장 TOP 10</h2>
<p style="color:#7986cb;font-size:.8rem;margin-bottom:10px;">
  🇰🇷 번역 → 🇺🇸 원문 | 🔊 발음 | 🎤 따라하기
</p>
<div id="sents-container"></div>

<script>
const WORDS = {words_json};
const SENTS = {sents_json};

// ── postMessage로 부모(Streamlit)에게 TTS 요청 ─────────────────────────────
// 안드로이드 크롬: iframe 내부 speechSynthesis 차단 → 부모에서 실행
function requestSpeak(text, rate) {{
  window.parent.postMessage({{ type: 'tts_speak', text, rate }}, '*');
}}
function requestStop() {{
  window.parent.postMessage({{ type: 'tts_stop' }}, '*');
}}

// ── 부모로부터 TTS 상태 수신 → 버튼 UI 업데이트 ───────────────────────────
let currentSpeakBtn = null;
window.addEventListener('message', (e) => {{
  if (!e.data || typeof e.data !== 'object') return;
  if (e.data.type === 'tts_start') {{
    if (currentSpeakBtn) currentSpeakBtn.classList.add('playing');
  }} else if (e.data.type === 'tts_end') {{
    if (currentSpeakBtn) currentSpeakBtn.classList.remove('playing');
    currentSpeakBtn = null;
  }}
}});

function speakText(text, rate, btnEl) {{
  // 이전 버튼 초기화
  if (currentSpeakBtn && currentSpeakBtn !== btnEl) {{
    currentSpeakBtn.classList.remove('playing');
  }}
  currentSpeakBtn = btnEl;
  requestSpeak(text, rate || 0.9);
}}

// ── 음성 인식 ────────────────────────────────────────────────────────────────
let activeRec = null;

function startRec(target, type, btnEl, scoreId) {{
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{
    const el = document.getElementById(scoreId);
    if (el) el.innerHTML = '<div style="color:#ffa726;font-size:.82rem;margin-top:6px;">⚠️ 음성 인식: Android Chrome 또는 iOS Safari에서 지원됩니다.</div>';
    return;
  }}
  if (activeRec) {{
    activeRec.stop(); activeRec = null;
    btnEl.classList.remove('recording');
    return;
  }}
  const rec = new SR();
  activeRec = rec;
  rec.lang = 'en-US';
  rec.continuous = false;
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  btnEl.classList.add('recording');
  rec.onresult = (e) => {{
    const spoken = e.results[0][0].transcript.toLowerCase().trim();
    showScore(scoreId, calcScore(target.toLowerCase(), spoken, type), spoken);
    btnEl.classList.remove('recording');
    activeRec = null;
  }};
  rec.onerror = (e) => {{
    btnEl.classList.remove('recording');
    activeRec = null;
    const el = document.getElementById(scoreId);
    if (el) el.innerHTML = '<div style="color:#ef5350;font-size:.82rem;margin-top:6px;">⚠️ 인식 오류: ' + e.error + '</div>';
  }};
  rec.onend = () => {{ btnEl.classList.remove('recording'); activeRec = null; }};
  rec.start();
}}

// ── 정확도 ───────────────────────────────────────────────────────────────────
function levenshtein(a, b) {{
  const m = a.length, n = b.length;
  const dp = Array.from({{length:m+1}}, (_,i) => Array.from({{length:n+1}}, (_,j) => i||j));
  for (let i=1;i<=m;i++) for (let j=1;j<=n;j++)
    dp[i][j] = a[i-1]===b[j-1] ? dp[i-1][j-1] : 1+Math.min(dp[i-1][j],dp[i][j-1],dp[i-1][j-1]);
  return dp[m][n];
}}
function calcScore(target, spoken, type) {{
  if (type==='word') return Math.max(0,Math.round((1-levenshtein(target,spoken)/Math.max(target.length,1))*100));
  const tw=target.replace(/[^a-z ]/g,'').split(/ +/).filter(Boolean);
  const sw=spoken.replace(/[^a-z ]/g,'').split(/ +/).filter(Boolean);
  if (!tw.length) return 0;
  const used=new Set(); let matched=0;
  for (const w of sw) {{
    const idx=tw.findIndex((t,i)=>!used.has(i)&&(t===w||levenshtein(t,w)<=1));
    if (idx!==-1){{matched++;used.add(idx);}}
  }}
  const rec=matched/tw.length, prec=sw.length?matched/sw.length:0;
  const f1=rec+prec>0?2*rec*prec/(rec+prec):0;
  const lenR=Math.min(sw.length,tw.length)/Math.max(sw.length,tw.length,1);
  return Math.min(100,Math.round((f1*.75+lenR*.25)*100));
}}
function showScore(id, score, spoken) {{
  const el=document.getElementById(id); if (!el) return;
  const c=score>=80?'#66bb6a':score>=50?'#ffa726':'#ef5350';
  el.innerHTML=`<div class="score-wrap">
    <div class="score-label" style="color:${{c}}">정확도: ${{score}}%</div>
    <div class="score-track"><div class="score-fill" style="width:${{score}}%;background:${{c}}"></div></div>
    <div class="score-spoken">인식된 음성: "${{spoken}}"</div>
  </div>`;
}}

// ── 카드 렌더링 ───────────────────────────────────────────────────────────────
function renderWords() {{
  const c=document.getElementById('words-container');
  WORDS.forEach((w,i) => {{
    const id='w'+i, sid='ws'+i;
    const div=document.createElement('div');
    div.className='card';
    div.innerHTML=`
      <div class="row">
        <span class="num">${{i+1}}.</span>
        <span class="korean">🇰🇷 ${{w.korean}}</span>
        <span style="color:#3949ab">→</span>
        <button class="speak-btn" id="spk_${{id}}">🔊 ${{w.word}}</button>
        <span class="ipa">${{w.ipa?'['+w.ipa+']':''}}</span>
        <button class="rec-btn" id="rec_${{id}}">🎤</button>
        <span class="hint">말하기</span>
      </div>
      ${{w.why?'<div class="why">💡 '+w.why+'</div>':''}}
      ${{w.usage?'<div class="usage">📌 "'+w.usage+'"</div>':''}}
      <div id="${{sid}}"></div>`;
    c.appendChild(div);
    document.getElementById('spk_'+id).addEventListener('click', function() {{ speakText(w.word, 0.9, this); }});
    document.getElementById('rec_'+id).addEventListener('click', function() {{ startRec(w.word,'word',this,sid); }});
  }});
}}
function renderSents() {{
  const c=document.getElementById('sents-container');
  SENTS.forEach((s,i) => {{
    const id='s'+i, sid='ss'+i;
    const div=document.createElement('div');
    div.className='card';
    div.style.borderLeft='3px solid #5c6bc0';
    div.innerHTML=`
      <div class="korean">🇰🇷 ${{s.ko}}</div>
      <div class="en-text">🇺🇸 ${{s.en}}</div>
      ${{s.why?'<div class="why">💡 '+s.why+'</div>':''}}
      <div class="row" style="margin-top:8px;">
        <button class="speak-btn" id="spk_${{id}}">🔊 원어민 발음</button>
        <button class="rec-btn" id="rec_${{id}}">🎤</button>
        <span class="hint">말하기</span>
      </div>
      <div id="${{sid}}"></div>`;
    c.appendChild(div);
    document.getElementById('spk_'+id).addEventListener('click', function() {{ speakText(s.en, 0.85, this); }});
    document.getElementById('rec_'+id).addEventListener('click', function() {{ startRec(s.en,'sentence',this,sid); }});
  }});
}}

renderWords();
renderSents();
</script>
</body>
</html>"""


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    st.markdown(
        "<h1 style='text-align:center;color:#90caf9;margin-bottom:4px;'>🎓 YouTube 영어 학습기</h1>"
        "<p style='text-align:center;color:#7986cb;margin-bottom:20px;'>원어민 핵심 단어·문장 추출 + 발음 연습</p>",
        unsafe_allow_html=True,
    )
    st.markdown("""
<div style="background:#1a237e22;border:1px solid #3949ab55;border-radius:10px;
            padding:12px 16px;margin-bottom:16px;font-size:.88rem;color:#b0bec5;">
💡 YouTube 주소 입력 → 분석 시작 &nbsp;|&nbsp;
🔊 발음 버튼 → 원어민 음성 재생 &nbsp;|&nbsp;
🎤 버튼 → 클릭 후 따라 말하면 정확도 즉시 표시<br>
⚠️ 음성 인식은 <b>Chrome(Android) / Safari(iOS)</b>에서 지원됩니다
</div>
""", unsafe_allow_html=True)

    # TTS 브리지: Streamlit 메인 페이지(부모)에 inject
    # 안드로이드 크롬 cross-origin iframe speechSynthesis 차단 우회
    st.markdown(TTS_BRIDGE_JS, unsafe_allow_html=True)

    col1, col2 = st.columns([5, 1])
    with col1:
        url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...",
                            label_visibility="collapsed")
    with col2:
        go = st.button("🔍 분석 시작", use_container_width=True)

    if not go or not url:
        st.markdown(
            "<div style='text-align:center;margin-top:60px;font-size:3rem;color:#3949ab;'>🎬</div>"
            "<p style='text-align:center;color:#546e7a;'>YouTube 주소를 입력하면 핵심 단어와 문장을 추출합니다</p>",
            unsafe_allow_html=True,
        )
        return

    video_id = extract_video_id(url)
    if not video_id:
        st.error("올바른 YouTube URL을 입력해주세요.")
        return

    with st.spinner("📥 자막 불러오는 중... (최대 30초)"):
        transcript, method, t_err = get_transcript(video_id)

    if not transcript:
        st.error(
            "❌ 자막을 가져오지 못했습니다.\n\n"
            "**시도한 방법별 오류:**\n```\n" + t_err + "\n```\n\n"
            "**해결 방법:**\n"
            "- 영어 자막(CC)이 켜진 영상인지 확인\n"
            "- 영상 URL을 다시 복사해서 시도\n"
            "- 유명 채널(TED, BBC, CNN 등) 영상으로 시도"
        )
        return

    st.success(f"✅ 자막 취득 완료 ({method} · {len(transcript.split())}단어)")

    with st.spinner("🤖 Gemini가 원어민 표현 분석 중..."):
        words, sentences, err = analyze_with_claude(transcript)

    if err == "NO_KEY":
        st.error("""
❌ **GEMINI_API_KEY가 설정되지 않았습니다.**

**🔑 무료 API 키 발급 (30초):**
1. https://aistudio.google.com/app/apikey 접속 (구글 계정 필요)
2. **Create API Key** 클릭 → 키 복사

**Streamlit Cloud 배포 시:**
앱 대시보드 → Settings → Secrets 에 추가:
```
GEMINI_API_KEY = "AIza..."
```

**로컬 실행 시:**
`.streamlit/secrets.toml` 파일 생성:
```
GEMINI_API_KEY = "AIza..."
```
""")
        return

    if err:
        st.error(f"❌ Gemini API 오류: {err}")
        return

    if not words and not sentences:
        st.error("분석 결과가 없습니다. 다시 시도해주세요.")
        return

    # 인터랙티브 컴포넌트 (카드 UI + postMessage TTS 요청)
    html = build_component_html(words, sentences, video_id)
    components.html(html, height=1900, scrolling=True)


if __name__ == "__main__":
    main()
