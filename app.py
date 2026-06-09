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

# --- 도구 함수 정의 ---

def get_video_id(url):
    """유튜브 URL에서 비디오 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript_robust(video_id):
    """수동/자동 자막을 구분하여 최대한 영어 자막을 추출합니다."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # 영어 자막 검색 (수동 우선, 없으면 자동 생성)
        try:
            return transcript_list.find_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            # 다른 언어 자막을 영어로 번역해서 시도
            return transcript_list.find_transcript(['en']).fetch()
    except Exception:
        return None

def get_accuracy_score(original, recorded):
    """원문과 인식된 텍스트 사이의 유사도를 점수로 계산 (0-100)"""
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    rec_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    ratio = SequenceMatcher(None, orig_clean, rec_clean).ratio()
    return int(ratio * 100)

def generate_tts(text):
    """텍스트를 원어민 음성으로 변환"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

# --- UI 레이아웃 ---

st.set_page_config(page_title="AI 유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")
st.markdown("### 유튜브 자막을 분석하여 핵심 단어와 문장을 추출하고 발음을 교정해 드립니다.")

url_input = st.text_input("학습할 유튜브 주소를 입력하세요:", value="https://www.youtube.com/watch?v=Zg2_361CgzE")

if url_input:
    video_id = get_video_id(url_input)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
    else:
        # 자막 가져오기 로직 실행
        transcript_data = fetch_transcript_robust(video_id)
        
        if transcript_data:
            # 1. 텍스트 분석 (단어 10개, 문장 10개)
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (불용어 제외, 4글자 이상)
            common_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 주요 문장 10개 (7~15단어 사이의 학습하기 좋은 문장)
            common_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 학습 섹션 구성
            tab_word, tab_sent = st.tabs(["🔤 Step 1: 핵심 단어 학습", "📝 Step 2: 주요 문장 학습"])

            with tab_word:
                st.subheader("🔑 핵심 단어 10개")
                st.write("한국어 가이드: 발음 기호를 확인하고 원어민 소리를 들은 뒤 마이크로 따라해 보세요.")
                for i, word in enumerate(common_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        c1, c2 = st.columns([1, 2])
                        with c1:
                            st.write(f"**발음 기호:** [{ipa.convert(word)}]")
                            st.audio(generate_tts(word), format="audio/mp3")
                        with c2:
                            st.write("🎙️ 나의 발음 녹음하기:")
                            rec = mic_recorder(key=f"word_{i}", start_prompt="녹음 시작", stop_prompt="중지")
                            if rec:
                                recognizer = sr.Recognizer()
                                with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                    audio = recognizer.record(source)
                                    try:
                                        user_speech = recognizer.recognize_google(audio, language='en-US')
                                        score = get_accuracy_score(word, user_speech)
                                        st.write(f"인식 결과: **{user_speech}**")
                                        st.metric("발음 정확도", f"{score}%")
                                        st.progress(score / 100)
                                    except:
                                        st.error("발음을 인식하지 못했습니다. 다시 시도해 주세요.")

            with tab_sent:
                st.subheader("📝 주요 문장 10개")
                st.write("한국어 가이드: 문장 전체의 억양과 호흡을 원어민 목소리와 비교하며 연습하세요.")
                for i, sent in enumerate(common_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    st.audio(generate_tts(sent), format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_speech = recognizer.recognize_google(audio, language='en-US')
                                score = get_accuracy_score(sent, user_speech)
                                st.write(f"인식 결과: **{user_speech}**")
                                st.write(f"종합 정확도 점수: **{score}%**")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        else:
            st.error("자막 로드 실패: 해당 영상은 자막 데이터를 추출할 수 없는 설정이거나 국가 제한이 걸려 있을 수 있습니다.")
            st.info("💡 **팁**: 자막(CC) 버튼이 활성화된 다른 유튜브 영상으로 테스트해 보시는 것을 추천합니다.")
