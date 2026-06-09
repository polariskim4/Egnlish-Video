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

# --- 리소스 준비 (NLTK 데이터 다운로드) ---
@st.cache_resource
def prepare_nltk():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

prepare_nltk()

# --- 로직 함수 정의 ---

def get_video_id(url):
    """유튜브 URL에서 비디오 ID를 추출합니다."""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript(video_id):
    """수동/자동 자막을 구분하여 가장 적합한 영어 자막을 가져옵니다."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # 영어 관련 모든 태그 시도 (수동 우선, 없으면 자동)
        try:
            return transcript_list.find_transcript(['en', 'en-US', 'en-GB', 'en-CA']).fetch()
        except:
            # 마지막 수단: 어떤 자막이든 영어로 번역해서 가져옴
            return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"자막 로드 실패: {str(e)}")
        return None

def calculate_accuracy(original, recorded):
    """원문과 인식된 음성 사이의 유사도를 점수로 환산합니다."""
    # 소문자 변환 및 구두점 제거
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    rec_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    
    # 유사도 산출 (0.0 ~ 1.0)
    ratio = SequenceMatcher(None, orig_clean, rec_clean).ratio()
    return int(ratio * 100)

def generate_tts(text):
    """텍스트를 음성으로 변환하여 오디오 스트림을 반환합니다."""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

# --- UI 레이아웃 ---

st.set_page_config(page_title="유튜브 영어 발음 교정", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")
st.info("유튜브 자막을 분석하여 핵심 표현을 배우고 발음 정확도를 채점해 드립니다.")

# 입력부
url = st.text_input("학습할 유튜브 주소를 입력하세요:", value="https://www.youtube.com/watch?v=M7BWHPtV1qM")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("유효하지 않은 유튜브 주소입니다.")
    else:
        transcript_data = fetch_transcript(video_id)
        
        if transcript_data:
            # 텍스트 분석
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (불용어 제외, 4자 이상)
            important_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 중요 문장 10개 (가독성 좋은 문장 추출)
            important_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 8 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 단어 학습 섹션
            st.header("🔤 Step 1: 핵심 단어 마스터")
            st.write("한국어 가이드: 단어를 보고 발음 기호를 확인한 뒤, 원어민 발음을 듣고 따라하세요.")
            
            for i, word in enumerate(important_words):
                with st.expander(f"{i+1}. {word.upper()}"):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.write(f"**발음 기호:** [{ipa.convert(word)}]")
                        st.audio(generate_tts(word), format="audio/mp3")
                    with col2:
                        st.write("🎙️ 나의 발음 녹음하기:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="녹음 시작", stop_prompt="중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_speech)
                                    st.write(f"인식 결과: **{user_speech}**")
                                    st.metric("발음 정확도", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.error("인식에 실패했습니다. 다시 시도해 주세요.")

            st.divider()

            # 문장 학습 섹션
            st.header("📝 Step 2: 주요 문장 쉐도잉")
            st.write("한국어 가이드: 문장 전체의 흐름과 인토네이션을 원어민 목소리와 비교하며 연습하세요.")
            
            for i, sent in enumerate(important_sentences):
                st.info(f"Sentence {i+1}: {sent}")
                st.audio(generate_tts(sent), format="audio/mp3")
                
                rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 따라 읽기", stop_prompt="완료")
                if rec_s:
                    recognizer = sr.Recognizer()
                    with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                        audio = recognizer.record(source)
                        try:
                            user_speech = recognizer.recognize_google(audio, language='en-US')
                            score = calculate_accuracy(sent, user_speech)
                            st.write(f"인식 결과: **{user_speech}**")
                            st.write(f"종합 정확도: **{score}%**")
                            st.progress(score / 100)
                        except:
                            st.error("음성을 인식할 수 없습니다.")
                st.divider()
