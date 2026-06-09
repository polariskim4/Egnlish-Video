import streamlit as st
import importlib.metadata  # pkg_resources 대신 이 모듈을 사용합니다.
# ... 다른 임포트 문들 ...

@st.cache_resource
def initialize_app():
    # NLTK 데이터 다운로드 로직
    import nltk
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    
    # 패키지 버전을 확인하는 최신 방식
    try:
        version = importlib.metadata.version("youtube-transcript-api")
    except importlib.metadata.PackageNotFoundError:
        version = "알 수 없음"
    return version

yt_api_version = initialize_app()
import streamlit as st
import youtube_transcript_api as yta
from youtube_transcript_api import YouTubeTranscriptApi
import importlib.metadata  # pkg_resources를 대체하는 파이썬 표준 라이브러리
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

# --- 1. 리소스 초기화 및 환경 설정 ---
@st.cache_resource
def initialize_app():
    """앱 시작 시 필요한 리소스를 한 번만 로드합니다."""
    # NLTK 데이터 다운로드 (불용어 제거 및 토큰화용)
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    
    # 패키지 버전 확인 (importlib.metadata 사용)
    try:
        version = importlib.metadata.version("youtube-transcript-api")
    except importlib.metadata.PackageNotFoundError:
        version = "알 수 없음"
    return version

yt_api_version = initialize_app()

# --- 2. 핵심 비즈니스 로직 함수 ---

def get_video_id(url):
    """유튜브 URL에서 11자리 고유 비디오 ID를 추출합니다."""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript_robust(video_id):
    """
    수동 자막, 자동 생성 자막, 번역 자막 순으로 탐색하여 
    가장 적합한 영어 자막 데이터를 가져옵니다.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1순위: 수동으로 작성된 영어 자막
        try:
            return transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            # 2순위: AI가 자동 생성한 영어 자막
            try:
                return transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB']).fetch()
            except:
                # 3순위: 다른 언어 자막을 영어로 실시간 번역
                return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"자막 로드 중 오류가 발생했습니다: {str(e)}")
        return None

def generate_tts(text):
    """텍스트를 음성으로 변환하여 메모리 내 오디오 스트림을 반환합니다."""
    tts = gTTS(text=text, lang='en')
    audio_fp = io.BytesIO()
    tts.write_to_fp(audio_fp)
    audio_fp.seek(0)
    return audio_fp

def calculate_accuracy(original, recorded):
    """원문과 인식된 음성 텍스트 간의 유사도를 점수(0~100%)로 계산합니다."""
    # 소문자화 및 특수문자 제거로 비교 정확도 향상
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    rec_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    
    # SequenceMatcher를 통한 유사도 산출
    ratio = SequenceMatcher(None, orig_clean, rec_clean).ratio()
    return int(ratio * 100)

# --- 3. Streamlit 웹 인터페이스 구성 ---

st.set_page_config(page_title="AI 유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")
st.markdown("유튜브 자막을 분석하여 핵심 표현을 배우고 발음 정확도를 체크해 드립니다.")

# 사이드바 설정
with st.sidebar:
    st.header("🛠️ 시스템 정보")
    st.write(f"YouTube API 버전: `{yt_api_version}`")
    st.divider()
    st.info("한국어 가이드에 따라 단어와 문장을 소리 내어 읽어보세요.")

# URL 입력창
url_input = st.text_input("유튜브 영상 주소를 입력하세요:", 
                         value="https://www.youtube.com/watch?v=M7BWHPtV1qM",
                         placeholder="https://www.youtube.com/watch?v=...")

if url_input:
    video_id = get_video_id(url_input)
    if not video_id:
        st.error("유효하지 않은 유튜브 주소입니다. 다시 확인해 주세요.")
    else:
        # 자막 가져오기
        transcript_data = fetch_transcript_robust(video_id)
        
        if transcript_data:
            # 텍스트 데이터 정제 및 분석
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (길이 4자 이상, 불용어 제외 빈도순)
            common_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 주요 문장 10개 (7~14단어 사이의 가독성 좋은 문장 위주)
            common_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 화면 레이아웃 분할
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔤 핵심 단어 마스터")
                st.write("발음 기호를 확인하고 원어민 소리를 들은 후 따라 해 보세요.")
                for i, word in enumerate(common_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음 기호:** `{ipa.convert(word)}`")
                        st.audio(generate_tts(word), format="audio/mp3")
                        
                        st.write("🎙️ 나의 발음 녹음:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="녹음 시작", stop_prompt="중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    # Google Web Speech API로 음성 인식
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_speech)
                                    st.write(f"인식 결과: **{user_speech}**")
                                    st.metric("발음 정확도", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.error("음성을 인식하지 못했습니다. 다시 시도해 주세요.")

            with col2:
                st.header("📝 주요 문장 쉐도잉")
                st.write("문장의 전체적인 억양과 호흡을 원어민과 비교하며 연습하세요.")
                for i, sent in enumerate(common_sentences):
                    st.info(f"문장 {i+1}: {sent}")
                    st.audio(generate_tts(sent), format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 따라하기", stop_prompt="완료")
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
            st.warning("이 영상은 현재 자막 데이터를 추출할 수 없거나 자막이 비활성화된 상태입니다.")
