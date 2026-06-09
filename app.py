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

# --- 리소스 준비 (NLTK 데이터 캐싱) ---
@st.cache_resource
def load_nltk_data():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

load_nltk_data()

# --- 핵심 로직 함수 ---

def get_video_id(url):
    """유튜브 URL에서 비디오 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript_robust(video_id):
    """
    [근본적 해결책] 
    수동 자막, 자동 생성 자막, 그리고 번역 자막 순으로 
    최대한 자막을 긁어오는 로직입니다.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 수동 생성된 영어 자막 우선 검색
        try:
            return transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            # 2. 수동 자막이 없으면 자동 생성된 영어 자막 검색
            try:
                return transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB']).fetch()
            except:
                # 3. 마지막 수단: 어떤 자막이든 영어로 번역해서 가져옴
                return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"유튜브 서버에서 자막을 가져오지 못했습니다: {str(e)}")
        return None

def calculate_accuracy(original, speech):
    """발음 정확도 계산 (0-100%)"""
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    speech_clean = re.sub(r'[^\w\s]', '', speech.lower()).strip()
    ratio = SequenceMatcher(None, orig_clean, speech_clean).ratio()
    return int(ratio * 100)

def generate_tts(text):
    """gTTS를 이용한 원어민 음성 생성"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

# --- UI 레이아웃 ---

st.set_page_config(page_title="AI 유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")
st.markdown("### 한국어 가이드를 따라 영어 발음을 마스터해보세요!")

url = st.text_input("학습할 유튜브 주소를 입력하세요 (한국어 가이드 -> 영어 학습 순):", 
                   value="https://www.youtube.com/watch?v=Zg2_361CgzE")

if url:
    v_id = get_video_id(url)
    if not v_id:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
    else:
        # 자막 로드 시작
        transcript_data = fetch_transcript_robust(v_id)
        
        if transcript_data:
            # 텍스트 분석 (중요 단어 및 문장 추출)
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 단어 10개 (불용어 제외, 4글자 이상)
            common_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 문장 10개 (가독성 좋은 길이)
            common_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 8 < len(t['text'].split()) < 14][:10]

            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔤 핵심 단어 학습")
                st.info("한국어 설명: 단어의 발음 기호를 보고 소리를 들은 뒤 마이크로 따라해 보세요.")
                for i, word in enumerate(common_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음 기호:** [{ipa.convert(word)}]")
                        st.audio(generate_tts(word), format="audio/mp3")
                        
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 따라하기", stop_prompt="⏹️ 중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_speech)
                                    st.write(f"인식 결과: **{user_speech}**")
                                    st.metric("정확도 점수", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.warning("발음을 인식하지 못했습니다.")

            with col2:
                st.header("📝 주요 문장 학습")
                st.info("한국어 설명: 문장 전체의 억양과 호흡을 원어민 목소리와 비교하며 연습하세요.")
                for i, sent in enumerate(common_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    st.audio(generate_tts(sent), format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 쉐도잉 시작", stop_prompt="완료")
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
                                st.error("음성 인식 실패")
                    st.divider()
