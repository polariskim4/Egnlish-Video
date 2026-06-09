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

# --- 리소스 준비 (NLTK 데이터 다운로드) ---
@st.cache_resource
def prepare_nltk():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

prepare_nltk()

# --- 주요 로직 함수 ---

def get_video_id(url):
    """유튜브 주소에서 비디오 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript_robust(video_id):
    """수동/자동 자막을 구분하여 가장 적합한 영어 자막 추출"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # 1. 영어 자막 시도 (수동 우선, 없으면 자동 생성)
        try:
            return transcript_list.find_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            # 2. 어떤 언어의 자막이든 영어로 번역해서 시도
            return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"자막 로드 실패: {str(e)}")
        return None

def calculate_accuracy(original, recorded):
    """텍스트 유사도를 기반으로 발음 정확도 점수 산출 (0-100%)"""
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    rec_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    ratio = SequenceMatcher(None, orig_clean, rec_clean).ratio()
    return int(ratio * 100)

def generate_tts(text):
    """원어민 음성 생성을 위한 오디오 스트림 반환"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

# --- UI 레이아웃 ---

st.set_page_config(page_title="유튜브 영어 발음 교정", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")
st.markdown("유튜브 주소를 입력하여 핵심 단어와 문장을 추출하고, 나의 발음 정확도를 체크해 보세요.")

url = st.text_input("학습할 유튜브 주소를 입력하세요:", value="https://www.youtube.com/watch?v=M7BWHPtV1qM")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
    else:
        # 자막 가져오기
        transcript_data = fetch_transcript_robust(video_id)
        
        if transcript_data:
            # 텍스트 분석 (단어 및 문장 추출)
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (4글자 이상, 불용어 제외)
            top_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 주요 문장 10개 (가독성 좋은 길이 추출)
            top_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 탭을 활용한 레이아웃 구성
            tab_word, tab_sent = st.tabs(["🔤 핵심 단어 학습", "📝 주요 문장 학습"])

            with tab_word:
                st.subheader("🔑 핵심 단어 10개")
                st.write("한국어 가이드: 발음 기호를 확인하고 원어민 소리를 들은 뒤 마이크로 따라해 보세요.")
                for i, word in enumerate(top_words):
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
                                        score = calculate_accuracy(word, user_speech)
                                        st.write(f"인식된 결과: **{user_speech}**")
                                        st.metric("발음 정확도", f"{score}%")
                                        st.progress(score / 100)
                                    except:
                                        st.warning("인식 실패. 다시 시도해 주세요.")

            with tab_sent:
                st.subheader("📝 주요 문장 10개")
                st.write("한국어 가이드: 문장 전체의 억양과 호흡을 원어민 목소리와 비교하며 연습하세요.")
                for i, sent in enumerate(top_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    st.audio(generate_tts(sent), format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="완료")
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

        else:
            st.warning("이 영상은 현재 자막 데이터를 추출할 수 없는 설정이거나 국가 제한이 걸려 있을 수 있습니다.")
