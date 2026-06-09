import nltk

# 처음 한 번만 실행하면 됩니다.
nltk.download('stopwords')
nltk.download('punkt')
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
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

# NLTK 데이터 다운로드 (최초 실행 시 필요)
@st.cache_resource
def load_nltk_resources():
    nltk.download('stopwords')
    nltk.download('punkt')

load_nltk_resources()

# --- 비즈니스 로직 함수 ---

def extract_video_id(url):
    """유튜브 URL에서 11자리 비디오 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_transcript_safe(video_id):
    """자막을 안전하게 가져오며 예외 상황을 처리"""
    try:
        # 정적 메서드 호출 방식 준수
        return YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
    except TranscriptsDisabled:
        st.error("이 영상은 자막 기능이 비활성화되어 있습니다.")
    except NoTranscriptFound:
        st.error("영어 자막을 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"자막 로드 중 알 수 없는 오류 발생: {e}")
    return None

def analyze_text(transcript_data):
    """단어 10개와 문장 10개 추출"""
    full_text = " ".join([t['text'] for t in transcript_data])
    
    # 단어 추출 (불용어 제거 및 정제)
    words = re.findall(r'\b\w+\b', full_text.lower())
    stop_words = set(stopwords.words('english'))
    important_words = [w for w, c in Counter(words).most_common(50) if w not in stop_words and len(w) > 3][:10]
    
    # 문장 추출 (가독성 좋은 길이 기준)
    sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 6 < len(t['text'].split()) < 15][:10]
    
    return important_words, sentences

def calculate_score(original, recorded):
    """발음 정확도 계산"""
    original_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    recorded_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    return int(SequenceMatcher(None, original_clean, recorded_clean).ratio() * 100)

# --- UI 레이아웃 ---

st.set_page_config(page_title="AI 영어 학습 매니저", layout="wide")
st.title("📺 YouTube 영어 학습 매니저")
st.markdown("유튜브 주소를 입력해 핵심 표현을 배우고 발음을 교정해보세요.")

url = st.text_input("학습할 유튜브 영상 주소를 입력하세요:", value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    video_id = extract_video_id(url)
    if video_id:
        transcript_data = get_transcript_safe(video_id)
        
        if transcript_data:
            words, sentences = analyze_text(transcript_data)
            
            tab1, tab2 = st.tabs(["🔑 중요 단어 10", "📝 주요 문장 10"])
            
            with tab1:
                for i, word in enumerate(words):
                    col_info, col_audio, col_rec = st.columns([3, 2, 5])
                    with col_info:
                        st.subheader(f"{i+1}. {word}")
                        st.write(f"[{ipa.convert(word)}]")
                    with col_audio:
                        tts = gTTS(text=word, lang='en')
                        fp = io.BytesIO()
                        tts.write_to_fp(fp)
                        st.audio(fp, format="audio/mp3")
                    with col_rec:
                        rec = mic_recorder(key=f"w_{i}", start_prompt="🎙️ 따라하기", stop_prompt="⏹️ 중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_score(word, user_speech)
                                    st.write(f"인식 결과: **{user_speech}** (정확도: {score}%)")
                                    st.progress(score / 100)
                                except:
                                    st.warning("발음을 인식하지 못했습니다.")

            with tab2:
                for i, sent in enumerate(sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    tts_s = gTTS(text=sent, lang='en')
                    fp_s = io.BytesIO()
                    tts_s.write_to_fp(fp_s)
                    st.audio(fp_s, format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"s_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="⏹️ 완료")
                    if rec_s:
                        # 문장 점수 계산 로직 (단어와 동일)
                        pass
                    st.divider()
    else:
        st.error("URL에서 비디오 ID를 추출할 수 없습니다.")
