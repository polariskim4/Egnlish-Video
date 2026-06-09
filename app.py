import nltk
nltk.download('stopwords')
nltk.download('punkt')
import nltk
nltk.download('stopwords')
nltk.download('punkt')
import streamlit as st
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

# NLTK 초기화 (중요 단어 필터링용)
@st.cache_resource
def init_resources():
    nltk.download('stopwords')
    nltk.download('punkt')

init_resources()

# --- 유틸리티 함수 ---

def get_video_id(url):
    """유튜브 URL에서 ID 추출"""
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match.group(1) if match else None

def get_audio_tts(text):
    """문장을 읽어주는 오디오 데이터 생성"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

def calculate_accuracy(original, recorded):
    """발음 정확도 계산 (0~100)"""
    original = re.sub(r'[^\w\s]', '', original.lower()).strip()
    recorded = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    return int(SequenceMatcher(None, original, recorded).ratio() * 100)

# --- UI 구성 ---

st.set_page_config(page_title="YouTube 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")
st.info("유튜브 영상의 자막을 분석하여 핵심 단어와 문장을 공부하고 발음을 체크합니다.")

url = st.text_input("학습할 유튜브 영상 주소를 입력하세요:", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("유효하지 않은 유튜브 주소입니다.")
    else:
        try:
            # 1. 자막 가져오기
            # 라이브러리의 정적 메서드를 올바른 방식으로 호출합니다.
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            full_text = " ".join([t['text'] for t in transcript_list])

            # 2. 핵심 단어 10개 추출
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            # 4글자 이상이며 불용어가 아닌 단어 중 빈도수 상위 10개
            important_words = [w for w, c in Counter(words).most_common(60) if w not in stop_words and len(w) > 3][:10]

            # 3. 주요 문장 10개 추출 (단어 수가 적당한 문장 위주)
            important_sentences = [t['text'].replace('\n', ' ') for t in transcript_list if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            col1, col2 = st.columns(2)

            # --- 단어 학습 영역 ---
            with col1:
                st.header("🔤 핵심 단어 학습")
                for i, word in enumerate(important_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**[발음기호]** : {ipa.convert(word)}")
                        
                        # TTS 재생
                        st.write("원어민 발음 듣기:")
                        st.audio(get_audio_tts(word), format="audio/mp3")
                        
                        # 따라하기 및 평가
                        st.write("내 발음 녹음하기:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 녹음 시작", stop_prompt="⏹️ 중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            audio_file = io.BytesIO(rec['bytes'])
                            with sr.AudioFile(audio_file) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_text = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_text)
                                    st.write(f"인식 결과: **{user_text}**")
                                    st.write(f"정확도 점수: **{score}%**")
                                    st.progress(score / 100)
                                except:
                                    st.error("발음을 인식하지 못했습니다.")

            # --- 문장 학습 영역 ---
            with col2:
                st.header("📝 주요 문장 학습")
                for i, sent in enumerate(important_sentences):
                    st.info(f"문장 {i+1}: {sent}")
                    
                    # TTS 재생
                    st.audio(get_audio_tts(sent), format="audio/mp3")
                    
                    # 따라하기 및 평가
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 따라하기", stop_prompt="⏹️ 중지")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        audio_file = io.BytesIO(rec_s['bytes'])
                        with sr.AudioFile(audio_file) as source:
                            audio = recognizer.record(source)
                            try:
                                user_text = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_accuracy(sent, user_text)
                                st.write(f"인식 결과: **{user_text}**")
                                st.write(f"정확도(인토네이션/호흡 포함): **{score}%**")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")
            st.warning("영상의 자막 설정이 활성화되어 있는지 확인해 주세요.")
