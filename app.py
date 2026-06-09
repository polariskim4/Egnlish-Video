import streamlit as st
import youtube_transcript_api as yta  # 모듈 전체를 별칭으로 가져옴
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
import warnings

# 실험적 버전에서 발생하는 구문 경고 무시
warnings.filterwarnings("ignore", category=SyntaxWarning)

# NLTK 리소스 준비
@st.cache_resource
def load_data():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

load_data()

def get_accuracy(target, recorded):
    target = re.sub(r'[^\w\s]', '', target.lower()).strip()
    recorded = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    return int(SequenceMatcher(None, target, recorded).ratio() * 100)

st.set_page_config(page_title="YouTube 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")

url = st.text_input("학습할 유튜브 주소를 입력하세요:", value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    # 비디오 ID 추출
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if video_id_match:
        video_id = video_id_match.group(1)
        try:
            # 오류 해결을 위해 YouTubeTranscriptApi 클래스를 통하지 않고 
            # 모듈의 메서드를 직접 호출하거나 인스턴스화를 시도하는 등 우회 기법 적용
            # 가장 안전한 방식은 list_transcripts를 통한 접근입니다.
            registry = yta.YouTubeTranscriptApi.list_transcripts(video_id)
            transcript_obj = registry.find_transcript(['en'])
            data = transcript_obj.fetch()
            
            # 분석 로직
            full_text = " ".join([d['text'] for d in data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 10개 단어 및 문장 추출
            key_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            key_sentences = [d['text'].replace('\n', ' ') for d in data if 7 < len(d['text'].split()) < 14][:10]

            col1, col2 = st.columns(2)
            
            with col1:
                st.header("🔑 핵심 단어 학습")
                for i, word in enumerate(key_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"발음기호: {ipa.convert(word)}")
                        tts = gTTS(text=word, lang='en')
                        audio_io = io.BytesIO()
                        tts.write_to_fp(audio_io)
                        st.audio(audio_io)
                        
                        # 마이크 녹음 및 점수
                        rec = mic_recorder(key=f"w_{i}", start_prompt="🎙️ 발음하기", stop_prompt="⏹️ 정지")
                        if rec:
                            r = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = r.record(source)
                                try:
                                    text = r.recognize_google(audio, language='en-US')
                                    score = get_accuracy(word, text)
                                    st.write(f"결과: {text} (정확도: {score}%)")
                                except: st.error("인식 실패")

            with col2:
                st.header("📝 주요 문장 학습")
                for i, sent in enumerate(key_sentences):
                    st.info(sent)
                    tts_s = gTTS(text=sent, lang='en')
                    audio_s = io.BytesIO()
                    tts_s.write_to_fp(audio_s)
                    st.audio(audio_s)
                    
                    rec_s = mic_recorder(key=f"s_{i}", start_prompt="🎙️ 따라하기", stop_prompt="⏹️ 완료")
                    if rec_s:
                        r = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = r.record(source)
                            try:
                                text = r.recognize_google(audio, language='en-US')
                                score = get_accuracy(sent, text)
                                st.write(f"정확도: {score}%")
                            except: st.error("인식 실패")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.info("환경 설정(runtime.txt)에서 파이썬 버전을 3.11로 낮추면 이 문제가 해결될 수 있습니다.")
    else:
        st.warning("유효한 유튜브 주소를 입력해주세요.")
