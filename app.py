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
import os

# --- 디버깅 및 리소스 초기화 ---
@st.cache_resource
def init_setup():
    # NLTK 데이터 다운로드
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    # 라이브러리 로드 경로 확인 (로그 확인용)
    return str(yta.__file__)

lib_path = init_setup()

def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def text_to_speech(text):
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

def calculate_accuracy(original, speech):
    # 정규화: 소문자화 및 구두점 제거
    original_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    speech_clean = re.sub(r'[^\w\s]', '', speech.lower()).strip()
    # 단순 문자열 유사도 (발음/호흡/정확도를 종합한 일치도)
    ratio = SequenceMatcher(None, original_clean, speech_clean).ratio()
    return int(ratio * 100)

# --- UI 설정 ---
st.set_page_config(page_title="유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 발음 교정 서비스")
st.markdown("유튜브 주소를 입력하여 핵심 단어와 문장을 추출하고 발음 정확도를 체크하세요.")

# 디버깅 정보 (문제가 지속될 경우 확인용, 성공 시 삭제 가능)
# st.sidebar.write(f"Library Path: {lib_path}")

url = st.text_input("유튜브 영상 주소 (URL)를 입력하세요:", value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("유효한 유튜브 주소가 아닙니다.")
    else:
        try:
            # [해결 포인트] 가장 원시적이고 확실한 방법으로 메서드 호출
            # 만약 클래스 참조가 깨졌다면 모듈에서 직접 접근을 시도합니다.
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            except AttributeError:
                # 클래스 메서드 접근 실패 시 대안 호출
                transcript = yta.YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            
            # 1. 단어 분석
            full_text = " ".join([t['text'] for t in transcript])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            important_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 2. 문장 분석
            important_sentences = [t['text'].replace('\n', ' ') for t in transcript if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔑 핵심 단어 학습")
                st.caption("한국어 뜻(예상) -> 발음기호 -> 목소리 듣기 -> 따라하기")
                for i, word in enumerate(important_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**[발음기호]** : {ipa.convert(word)}")
                        
                        # TTS 재생
                        st.audio(text_to_speech(word), format="audio/mp3")
                        
                        # 녹음 및 정확도 표시
                        st.write("발음을 따라해보세요:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 녹음 시작", stop_prompt="⏹️ 중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_text = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_text)
                                    st.write(f"인식 결과: **{user_text}**")
                                    st.metric("정확도 (100% 기준)", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.error("인식에 실패했습니다. 다시 시도해주세요.")

            with col2:
                st.header("📝 주요 문장 학습")
                for i, sent in enumerate(important_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    st.audio(text_to_speech(sent), format="audio/mp3")
                    
                    # 문장 따라하기
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="⏹️ 완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_text = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_accuracy(sent, user_text)
                                st.write(f"결과: {user_text} (정확도: {score}%)")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.warning("영상의 자막 설정이 되어 있는지 확인해 주세요.")

