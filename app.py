import streamlit as st
import youtube_transcript_api as yta
from youtube_transcript_api import YouTubeTranscriptApi
import re
from collections import Counter
import eng_to_ipa as ipa
from gtts import gTTS
import io
import nltk
from nltk.corpus import stopwords
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from difflib import SequenceMatcher

# --- 리소스 설정 (NLTK) ---
@st.cache_resource
def load_nltk():
    try:
        nltk.download('stopwords', quiet=True)
        nltk.download('punkt', quiet=True)
    except:
        pass

load_nltk()

# --- 도구 함수 ---
def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript_final(video_id):
    """
    라이브러리 버전에 상관없이 자막을 가져오는 가장 강력한 방법입니다.
    """
    try:
        # 방법 1: 최신 버전의 list_transcripts 사용 시도
        if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                return transcript_list.find_transcript(['en', 'en-US']).fetch()
            except:
                return transcript_list.find_generated_transcript(['en']).fetch()
        
        # 방법 2: 구버전 또는 기본 get_transcript 사용 시도
        return YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US'])
        
    except Exception as e:
        st.error(f"자막 추출 오류: {str(e)}")
        return None

def calculate_accuracy(original, user_input):
    orig = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user = re.sub(r'[^\w\s]', '', user_input.lower()).strip()
    return int(SequenceMatcher(None, orig, user).ratio() * 100)

def text_to_speech(text):
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

# --- UI 레이아웃 ---
st.set_page_config(page_title="유튜브 영어 학습", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")

# 사이드바 디버깅 정보 (필요시 확인)
with st.sidebar:
    st.write(f"라이브러리 버전 확인: {getattr(yta, '__version__', '알 수 없음')}")

url = st.text_input("유튜브 주소를 입력하세요 (한국어 가이드 → 영어 실습 순):", 
                   value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    v_id = get_video_id(url)
    if v_id:
        with st.spinner('자막을 분석 중입니다...'):
            data = fetch_transcript_final(v_id)
        
        if data:
            # 분석 로직
            full_text = " ".join([t['text'] for t in data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            important_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            important_sentences = [t['text'].replace('\n', ' ') for t in data if 7 < len(t['text'].split()) < 14][:10]

            col1, col2 = st.columns(2)

            with col1:
                st.header("🔤 핵심 단어 (10개)")
                st.write("단어의 뜻과 발음을 확인하고 따라해보세요.")
                for i, word in enumerate(important_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        st.audio(text_to_speech(word))
                        
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 녹음 시작", stop_prompt="⏹️ 중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_text = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_text)
                                    st.write(f"인식 결과: **{user_text}**")
                                    st.metric("정확도 점수", f"{score}%")
                                    st.progress(score / 100)
                                except: st.error("인식 실패")

            with col2:
                st.header("📝 주요 문장 (10개)")
                st.write("문장 전체의 억양과 호흡을 원어민 목소리와 비교해보세요.")
                for i, sent in enumerate(important_sentences):
                    st.info(f"문장 {i+1}: {sent}")
                    st.audio(text_to_speech(sent))
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 따라하기", stop_prompt="완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_text = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_accuracy(sent, user_text)
                                st.write(f"결과: {user_text} (정확도: {score}%)")
                                st.progress(score / 100)
                            except: st.error("인식 실패")
                    st.divider()
        else:
            st.error("자막 데이터를 가져오지 못했습니다. 자막이 있는 다른 영상으로 시도해 보세요.")
