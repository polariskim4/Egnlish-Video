import streamlit as st
import re
import json
import time
import random
from collections import Counter
import urllib.parse

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YouTube 영어 학습기",
    page_icon="🎓",
    layout="wide",
)

# ── 전역 CSS / JS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main { background: #0f1117; color: #e8eaf6; }
  .card {
    background: #1e2130; border-radius: 14px; padding: 18px 22px;
    margin: 10px 0; border: 1px solid #2d3250;
    transition: box-shadow .2s;
  }
  .card:hover { box-shadow: 0 0 12px #5c6bc088; }
  .word-btn {
    background: #3949ab; color: #fff; border: none;
    border-radius: 8px; padding: 6px 14px; cursor: pointer;
    font-size: 1rem; font-weight: 600; margin-right: 8px;
  }
  .word-btn:hover { background: #5c6bc0; }
  .ipa { color: #90caf9; font-size: .9rem; margin-left: 6px; }
  .korean { color: #a5d6a7; font-size: .9rem; }
  .score-bar { height: 12px; border-radius: 6px; background: #2d3250; }
  .score-fill { height: 12px; border-radius: 6px; background: linear-gradient(90deg,#42a5f5,#7c4dff); }
  .sentence-box {
    background: #161b2e; border-left: 3px solid #5c6bc0;
    border-radius: 8px; padding: 12px 16px; margin: 8px 0;
  }
  .rec-btn {
    background: #c62828; color: #fff; border: none;
    border-radius: 50%; width: 44px; height: 44px;
    font-size: 1.3rem; cursor: pointer;
  }
  .rec-btn.recording { animation: pulse 1s infinite; }
  @keyframes pulse {
    0%,100% { box-shadow: 0 0 0 0 #c6282855; }
    50%      { box-shadow: 0 0 0 10px #c6282800; }
  }
  .section-title {
    font-size: 1.3rem; font-weight: 700; color: #90caf9;
    border-bottom: 2px solid #3949ab; padding-bottom: 6px; margin: 20px 0 14px;
  }
  .info-box {
    background: #1a237e22; border: 1px solid #3949ab55;
    border-radius: 10px; padding: 14px 18px; margin: 12px 0;
    font-size: .9rem; color: #b0bec5;
  }
  .stTextInput > div > div > input {
    background: #1e2130 !important; color: #e8eaf6 !important;
    border: 1px solid #3949ab !important; border-radius: 10px !important;
  }
  .stButton > button {
    background: linear-gradient(135deg, #3949ab, #7c4dff) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
  }
</style>
""", unsafe_allow_html=True)

# ── YouTube ID 추출 ───────────────────────────────────────────────────────────
def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ── 자막 취득 (yt-dlp 우선, youtube-transcript-api 차선) ───────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_transcript(video_id: str) -> tuple[str, str]:
    """(transcript_text, method_used) 반환"""

    # ─ 방법 1: yt-dlp (쿠키 없이도 동작, User-Agent 우회) ─────────────────
    try:
        import yt_dlp, tempfile, os, glob

        ydl_opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "vtt",
            "outtmpl": tempfile.gettempdir() + "/yt_sub_%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        vtt_files = glob.glob(tempfile.gettempdir() + f"/yt_sub_{video_id}*.vtt")
        if vtt_files:
            text = parse_vtt(vtt_files[0])
            for f in vtt_files:
                try: os.remove(f)
                except: pass
            if len(text) > 100:
                return text, "yt-dlp"
    except Exception:
        pass

    # ─ 방법 2: youtube-transcript-api ──────────────────────────────────────
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

        proxies = None  # 필요 시 {"http": "...", "https": "..."}
        transcript_list = YouTubeTranscriptApi.list_transcripts(
            video_id,
            proxies=proxies,
            cookies=None,
        )
        # 영어 자막 우선
        for lang in ["en", "en-US", "en-GB"]:
            try:
                t = transcript_list.find_transcript([lang])
                data = t.fetch()
                return " ".join(d["text"] for d in data), "youtube-transcript-api"
            except Exception:
                pass
        # 자동 생성 자막 fallback
        for t in transcript_list:
            if t.language_code.startswith("en"):
                data = t.fetch()
                return " ".join(d["text"] for d in data), "auto-caption"
    except Exception:
        pass

    return "", "failed"


def parse_vtt(path: str) -> str:
    """VTT 자막 파일을 일반 텍스트로 변환"""
    lines = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("WEBVTT") or "-->" in line:
                    continue
                if re.match(r"^\d+$", line):
                    continue
                # HTML 태그 제거
                line = re.sub(r"<[^>]+>", "", line)
                lines.append(line)
    except Exception:
        pass
    return " ".join(lines)


# ── 텍스트 분석: 중요 단어 10개 추출 ──────────────────────────────────────
STOPWORDS = {
    "the","a","an","is","are","was","were","be","been","being",
    "have","has","had","do","does","did","will","would","could",
    "should","may","might","shall","can","need","dare","ought",
    "i","you","he","she","it","we","they","me","him","her","us",
    "them","my","your","his","its","our","their","this","that",
    "these","those","and","but","or","nor","for","yet","so",
    "in","on","at","to","of","up","by","as","if","then","than",
    "with","from","into","onto","upon","about","over","after",
    "before","since","until","while","although","though","because",
    "when","where","who","what","which","how","not","no","just",
    "also","very","really","even","still","already","always",
    "never","ever","there","here","now","then","all","both","each",
    "few","more","most","other","some","such","only","same","own",
    "get","got","make","go","going","come","coming","say","said",
    "know","think","look","want","give","use","find","tell","seem",
    "call","keep","let","put","mean","become","leave","show","feel",
    "try","ask","turn","move","live","play","run","see","take",
    "well","like","way","time","people","one","two","three",
    "re","ve","ll","s","t","d","m",
}

def extract_words(text: str, n: int = 10) -> list[str]:
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    counts = Counter(w for w in words if w not in STOPWORDS)
    return [w for w, _ in counts.most_common(n * 3)][:n]


def extract_sentences(text: str, n: int = 10) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.split()) >= 5]
    # 너무 긴 문장 제외
    sentences = [s for s in sentences if len(s.split()) <= 25]
    if not sentences:
        return []
    # 중복 의미 줄이기: 앞뒤 문장과 단어 겹침 50% 이하만 선택
    selected = [sentences[0]]
    for s in sentences[1:]:
        sw = set(s.lower().split())
        if all(len(sw & set(prev.lower().split())) / max(len(sw), 1) < 0.5
               for prev in selected):
            selected.append(s)
        if len(selected) >= n:
            break
    return selected[:n]


# ── Claude API 호출: 단어 정보 (IPA, 한국어 뜻) ───────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def enrich_words(words: list[str]) -> list[dict]:
    """Claude API로 단어별 IPA 발음기호 + 한국어 뜻 획득"""
    try:
        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            "다음 영어 단어 목록에 대해 JSON 배열로만 응답하세요. "
            "각 항목: {\"word\": ..., \"ipa\": \"IPA 발음기호\", \"korean\": \"한국어 뜻 1~2개\"}.\n"
            f"단어 목록: {json.dumps(words, ensure_ascii=False)}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception:
        return [{"word": w, "ipa": "", "korean": ""} for w in words]


@st.cache_data(ttl=86400, show_spinner=False)
def translate_sentences(sentences: list[str]) -> list[dict]:
    """Claude API로 문장 한국어 번역"""
    try:
        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            "다음 영어 문장들을 한국어로 번역해 JSON 배열로만 응답하세요. "
            "각 항목: {\"en\": ..., \"ko\": ...}.\n"
            f"문장 목록: {json.dumps(sentences, ensure_ascii=False)}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception:
        return [{"en": s, "ko": ""} for s in sentences]


# ── 브라우저 TTS + 음성 인식 JavaScript ──────────────────────────────────
TTS_AND_SPEECH_JS = """
<script>
// ─── TTS ───────────────────────────────────────────────────────────────────
function speakText(text, rate=0.9) {
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-US';
  u.rate = rate;
  // 원어민 목소리 선택 (en-US 계열)
  const voices = window.speechSynthesis.getVoices();
  const pref = voices.find(v => v.lang === 'en-US' && v.name.includes('Google'))
            || voices.find(v => v.lang === 'en-US')
            || voices.find(v => v.lang.startsWith('en'));
  if (pref) u.voice = pref;
  window.speechSynthesis.speak(u);
}

// ─── 음성 인식 ─────────────────────────────────────────────────────────────
let recognizer = null;
let currentTarget = '';
let currentType  = '';  // 'word' | 'sentence'

function startRecording(target, type, btnId) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert('이 브라우저는 음성 인식을 지원하지 않습니다. Chrome을 사용해주세요.');
    return;
  }
  if (recognizer) { recognizer.stop(); recognizer = null; }

  currentTarget = target;
  currentType   = type;

  recognizer = new SpeechRecognition();
  recognizer.lang = 'en-US';
  recognizer.continuous = false;
  recognizer.interimResults = false;

  const btn = document.getElementById(btnId);
  if (btn) btn.classList.add('recording');

  recognizer.onresult = (e) => {
    const spoken = e.results[0][0].transcript.toLowerCase().trim();
    const score  = calcScore(currentTarget.toLowerCase().trim(), spoken, currentType);
    showScore(btnId, score, spoken);
    if (btn) btn.classList.remove('recording');
    recognizer = null;
  };
  recognizer.onerror = () => {
    if (btn) btn.classList.remove('recording');
    recognizer = null;
  };
  recognizer.start();
}

// ─── 정확도 계산 ───────────────────────────────────────────────────────────
function calcScore(target, spoken, type) {
  if (type === 'word') {
    // 단어: 편집 거리 기반
    return Math.round((1 - levenshtein(target, spoken) / Math.max(target.length, 1)) * 100);
  }
  // 문장: 단어 집합 유사도 + 순서 패널티
  const tw = target.replace(/[^a-z ]/g,'').split(/\s+/).filter(Boolean);
  const sw = spoken.replace(/[^a-z ]/g,'').split(/\s+/).filter(Boolean);
  if (!tw.length) return 0;

  let matched = 0;
  const usedIdx = new Set();
  for (const w of sw) {
    const idx = tw.findIndex((t,i) => !usedIdx.has(i) && (t === w || levenshtein(t,w) <= 1));
    if (idx !== -1) { matched++; usedIdx.add(idx); }
  }
  const recall    = matched / tw.length;
  const precision = sw.length ? matched / sw.length : 0;
  const f1 = recall + precision > 0 ? 2*recall*precision/(recall+precision) : 0;

  // 인토네이션/호흡 근사: 문장 길이 비율
  const lenRatio = Math.min(sw.length, tw.length) / Math.max(sw.length, tw.length);

  return Math.min(100, Math.round((f1 * 0.75 + lenRatio * 0.25) * 100));
}

function levenshtein(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({length:m+1}, (_,i) => Array.from({length:n+1}, (_,j) => i||j));
  for (let i=1;i<=m;i++) for (let j=1;j<=n;j++)
    dp[i][j] = a[i-1]===b[j-1] ? dp[i-1][j-1]
             : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
  return dp[m][n];
}

function showScore(btnId, score, spoken) {
  const container = document.getElementById('score_' + btnId);
  if (!container) return;
  const color = score >= 80 ? '#66bb6a' : score >= 50 ? '#ffa726' : '#ef5350';
  container.innerHTML = `
    <div style="margin-top:8px;">
      <div style="color:${color};font-weight:700;font-size:1rem;">정확도: ${score}%</div>
      <div style="background:#2d3250;border-radius:6px;height:10px;margin:4px 0;">
        <div style="width:${score}%;background:${color};height:10px;border-radius:6px;transition:width .5s;"></div>
      </div>
      <div style="color:#b0bec5;font-size:.8rem;">인식된 음성: "${spoken}"</div>
    </div>`;
}

// 보이스 로딩 대기
if (window.speechSynthesis.onvoiceschanged !== undefined)
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
</script>
"""

# ── 단어 카드 렌더링 ──────────────────────────────────────────────────────
def render_word_card(info: dict, idx: int):
    word    = info.get("word", "")
    ipa     = info.get("ipa", "")
    korean  = info.get("korean", "")
    btn_id  = f"wrec_{idx}"
    st.markdown(f"""
<div class="card">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
    <span style="font-size:1.1rem;color:#e8eaf6;">{idx+1}.</span>
    <!-- 🇰🇷 한국어 뜻 먼저 -->
    <span class="korean" style="font-size:1rem;font-weight:600;">🇰🇷 {korean}</span>
    <span style="color:#7986cb;">→</span>
    <!-- 🇺🇸 영어 + 발음기호 -->
    <button class="word-btn" onclick="speakText('{word}')">🔊 {word}</button>
    <span class="ipa">[{ipa}]</span>
    <!-- 따라하기 버튼 -->
    <button class="rec-btn" id="{btn_id}"
      onclick="startRecording('{word}','word','{btn_id}')">🎤</button>
  </div>
  <div id="score_{btn_id}"></div>
</div>
""", unsafe_allow_html=True)


# ── 문장 카드 렌더링 ──────────────────────────────────────────────────────
def render_sentence_card(info: dict, idx: int):
    en     = info.get("en", "").replace("'", "\\'")
    ko     = info.get("ko", "")
    btn_id = f"srec_{idx}"
    st.markdown(f"""
<div class="card sentence-box">
  <!-- 🇰🇷 한국어 번역 먼저 -->
  <div class="korean" style="font-size:.95rem;margin-bottom:6px;">🇰🇷 {ko}</div>
  <div style="color:#cfd8dc;font-size:.9rem;margin-bottom:8px;">🇺🇸 {info.get('en','')}</div>
  <div style="display:flex;gap:10px;align-items:center;">
    <button class="word-btn" onclick="speakText('{en}', 0.85)">🔊 원어민 발음</button>
    <button class="rec-btn" id="{btn_id}"
      onclick="startRecording('{en}','sentence','{btn_id}')">🎤</button>
    <span style="color:#7986cb;font-size:.82rem;">🎤 클릭 후 따라하세요</span>
  </div>
  <div id="score_{btn_id}"></div>
</div>
""", unsafe_allow_html=True)


# ── 메인 UI ──────────────────────────────────────────────────────────────────
def main():
    # JS 삽입 (한 번만)
    st.markdown(TTS_AND_SPEECH_JS, unsafe_allow_html=True)

    st.markdown(
        "<h1 style='text-align:center;color:#90caf9;'>🎓 YouTube 영어 학습기</h1>"
        "<p style='text-align:center;color:#7986cb;'>유튜브 영상에서 핵심 단어·문장을 뽑아 발음을 연습하세요</p>",
        unsafe_allow_html=True,
    )

    st.markdown("""
<div class="info-box">
💡 <b>사용법</b>: YouTube 주소를 입력하고 <b>분석 시작</b>을 클릭하세요.<br>
🔊 단어/문장 버튼 → 원어민 발음 듣기 &nbsp;|&nbsp; 🎤 버튼 → 따라 말하기 → 정확도 즉시 표시<br>
⚠️ 음성 인식은 <b>Chrome 브라우저</b>에서만 작동합니다.
</div>
""", unsafe_allow_html=True)

    col1, col2 = st.columns([5, 1])
    with col1:
        url = st.text_input(
            "YouTube URL",
            placeholder="https://www.youtube.com/watch?v=...",
            label_visibility="collapsed",
        )
    with col2:
        analyze = st.button("🔍 분석 시작", use_container_width=True)

    if not analyze or not url:
        st.markdown("""
<div style='text-align:center;margin-top:60px;color:#3949ab;font-size:3rem;'>🎬</div>
<p style='text-align:center;color:#7986cb;'>YouTube 주소를 입력하면 핵심 단어와 문장을 추출합니다</p>
""", unsafe_allow_html=True)
        return

    video_id = extract_video_id(url)
    if not video_id:
        st.error("올바른 YouTube URL이 아닙니다.")
        return

    # ── 자막 취득 ──
    with st.spinner("📥 자막을 불러오는 중... (최대 30초 소요)"):
        transcript, method = get_transcript(video_id)

    if not transcript:
        st.error(
            "자막을 가져오지 못했습니다. "
            "해당 영상에 영어 자막이 없거나 YouTube가 차단했을 수 있습니다.\n\n"
            "💡 자동 생성 자막이 활성화된 영어 영상으로 다시 시도해보세요."
        )
        return

    st.success(f"✅ 자막 취득 완료 (방법: {method}, {len(transcript.split())}단어)")

    # 영상 임베드
    st.markdown(
        f'<iframe width="100%" height="340" src="https://www.youtube.com/embed/{video_id}"'
        f' frameborder="0" allowfullscreen style="border-radius:12px;"></iframe>',
        unsafe_allow_html=True,
    )

    # ── 분석 ──
    with st.spinner("🔬 핵심 단어·문장 분석 중..."):
        raw_words = extract_words(transcript, 10)
        raw_sents = extract_sentences(transcript, 10)
        word_data = enrich_words(raw_words)
        sent_data = translate_sentences(raw_sents)

    # ── 단어 섹션 ──
    st.markdown('<div class="section-title">📚 핵심 단어 TOP 10</div>', unsafe_allow_html=True)
    st.markdown(
        "<div style='color:#7986cb;font-size:.85rem;margin-bottom:10px;'>"
        "🇰🇷 뜻 → 🇺🇸 단어 순서 &nbsp;|&nbsp; 🔊 원어민 발음 &nbsp;|&nbsp; 🎤 따라하기</div>",
        unsafe_allow_html=True,
    )
    for i, info in enumerate(word_data):
        render_word_card(info, i)

    # ── 문장 섹션 ──
    st.markdown('<div class="section-title">💬 핵심 문장 TOP 10</div>', unsafe_allow_html=True)
    st.markdown(
        "<div style='color:#7986cb;font-size:.85rem;margin-bottom:10px;'>"
        "🇰🇷 번역 → 🇺🇸 원문 순서 &nbsp;|&nbsp; 🔊 원어민 발음 &nbsp;|&nbsp; 🎤 따라하기</div>",
        unsafe_allow_html=True,
    )
    for i, info in enumerate(sent_data):
        render_sentence_card(info, i)

    st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
