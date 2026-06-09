import streamlit as st
import youtube_transcript_api as yta
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
    AttributeError를 원천 봉쇄하기 위해 모듈에서 직접 접근하는 방식입니다.
    """
    try:
        # 1. 모듈 레벨에서 직접 리스트를 가져옵니다.
        # 이 코드가 AttributeError를 발생시킨다면 설치된 라이브러리 자체가 손상된 것입니다.
        transcript_list = yta.YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            # 영어 수동 자막 시도
            return transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            try:
                # 영어 자동 생성 자막 시도
                return transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB']).fetch()
            except:
                # 마지막 수단: 첫 번째 자막을 영어로 번역
                return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"자막 추출 오류: {str(e)}")
        st.info("💡 팁: 이 에러는 유튜브가 서버 IP를 차단했을 때도 발생할 수 있습니다.")
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
st.set_page_config(page_title="유튜브 영어 정복", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")

url = st.text_input("유튜브 주소를 입력하세요 (한국어 가이드 -> 영어 실습 순):", 
                   value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    v_id = get_video_id(url)
    if v_id:
        data = fetch_transcript_final(v_id)
        
        if data:
            # 텍스트 분석
            full_text = " ".join([t['text'] for t in data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 단어 10개, 문장 10개 추출
            important_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            important_sentences = [t['text'].replace('\n', ' ') for t in data if 7 < len(t['text'].split()) < 14][:10]

            col1, col2 = st.columns(2)

            with col1:
                st.header("🔤 핵심 단어")
                for i, word in enumerate(important_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        st.audio(text_to_speech(word))
                        
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 녹음", stop_prompt="중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_text = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_text)
                                    st.write(f"결과: {user_text} (정확도: {score}%)")
                                    st.progress(score / 100)
                                except: st.error("인식 실패")

            with col2:
                st.header("📝 주요 문장")
                for i, sent in enumerate(important_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
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

