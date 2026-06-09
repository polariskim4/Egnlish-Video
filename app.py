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
def prepare_resources():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

prepare_resources()

# --- 주요 함수 정의 ---

def get_video_id(url):
    """유튜브 URL에서 11자리 비디오 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_transcript_robust(video_id):
    """수동/자동 자막을 구분하여 가장 적절한 영어 자막을 추출"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 수동 생성된 영어 자막 시도 ('en', 'en-US', 'en-GB' 등)
        try:
            return transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            # 2. 자동 생성된 영어 자막 시도
            try:
                return transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB']).fetch()
            except:
                # 3. 다른 언어 자막을 영어로 번역해서 가져오기 (마지막 수단)
                return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"자막을 가져올 수 없습니다: {str(e)}")
        return None

def get_tts_audio(text):
    """원어민 발음 생성을 위한 TTS"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

def calculate_accuracy(original, user_input):
    """두 문장의 유사도를 측정하여 100% 기준으로 점수화"""
    # 전처리: 소문자화 및 문장 부호 제거
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user_clean = re.sub(r'[^\w\s]', '', user_input.lower()).strip()
    
    # 유사도 산출 (SequenceMatcher 활용)
    similarity = SequenceMatcher(None, orig_clean, user_clean).ratio()
    return int(similarity * 100)

# --- UI 레이아웃 ---

st.set_page_config(page_title="유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")
st.info("유튜브 자막을 분석하여 핵심 단어와 문장을 추출하고 발음 정확도를 체크해 드립니다.")

url_input = st.text_input("학습할 유튜브 주소를 입력하세요 (한국어 가이드 -> 영어 학습 순):", 
                         value="https://www.youtube.com/watch?v=M7BWHPtV1qM")

if url_input:
    video_id = get_video_id(url_input)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
    else:
        # 자막 가져오기 실행
        transcript_data = get_transcript_robust(video_id)
        
        if transcript_data:
            # 1. 텍스트 분석 (단어 10개, 문장 10개)
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (불용어 제외, 4글자 이상)
            common_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 주요 문장 10개 (7~15단어 사이의 적당한 문장)
            common_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 단어 학습 섹션
            st.header("🔤 Step 1: 핵심 단어 학습")
            st.write("발음기호를 확인하고 원어민 발음을 들은 뒤 직접 발음해 보세요.")
            
            for i, word in enumerate(common_words):
                with st.expander(f"{i+1}. {word.upper()}"):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        st.audio(get_tts_audio(word), format="audio/mp3")
                    with col2:
                        st.write("🎙️ 발음을 녹음해 보세요:")
                        rec = mic_recorder(key=f"word_rec_{i}", start_prompt="녹음 시작", stop_prompt="중지")
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
                                    st.error("발음을 인식하지 못했습니다. 다시 시도해 주세요.")

            st.divider()

            # 문장 학습 섹션
            st.header("📝 Step 2: 주요 문장 학습")
            st.write("문장의 전체적인 억양(Intonation)과 호흡을 생각하며 따라해 보세요.")
            
            for i, sent in enumerate(common_sentences):
                st.info(f"문장 {i+1}: {sent}")
                st.audio(get_tts_audio(sent), format="audio/mp3")
                
                rec_s = mic_recorder(key=f"sent_rec_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="완료")
                if rec_s:
                    recognizer = sr.Recognizer()
                    with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                        audio = recognizer.record(source)
                        try:
                            user_speech = recognizer.recognize_google(audio, language='en-US')
                            score = calculate_accuracy(sent, user_speech)
                            st.write(f"인식 결과: **{user_speech}**")
                            st.write(f"종합 정확도 점수: **{score}%**")
                            st.progress(score / 100)
                        except:
                            st.error("음성을 인식할 수 없습니다.")
                st.divider()
