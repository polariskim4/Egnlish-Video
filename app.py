import streamlit as st
import youtube_transcript_api as yta
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
import pkg_resources

# --- 1. 리소스 초기화 (NLTK 및 시스템 설정) ---
@st.cache_resource
def initialize_app():
    # 불용어 제거를 위한 NLTK 데이터 다운로드
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    
    # 설치된 라이브러리 버전 확인 (디버깅용)
    try:
        version = pkg_resources.get_distribution("youtube-transcript-api").version
    except:
        version = "알 수 없음"
    return version

yt_api_version = initialize_app()

# --- 2. 비즈니스 로직 함수 ---

def get_video_id(url):
    """유튜브 주소에서 11자리 비디오 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_transcript_robust(video_id):
    """
    [핵심] 수동 자막, 자동 생성 자막, 번역 자막 순서로 
    가장 적절한 영어 자막을 추출합니다.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 수동 생성 영어 자막 시도 (en, en-US, en-GB 등)
        try:
            return transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB']).fetch()
        except:
            # 2. 자동 생성 영어 자막 시도
            try:
                return transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB']).fetch()
            except:
                # 3. 마지막 수단: 어떤 자막이든 영어로 번역하여 시도
                return transcript_list.find_transcript(['en']).fetch()
    except Exception as e:
        st.error(f"자막 로드 실패: {str(e)}")
        return None

def generate_tts(text):
    """원어민 발음 생성을 위한 TTS 스트림 반환"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

def calculate_accuracy(original, recorded):
    """원문과 인식된 텍스트 간의 유사도를 100% 기준으로 계산"""
    # 전처리: 소문자화 및 특수문자 제거
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    rec_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    
    # 유사도 산출 (SequenceMatcher 알고리즘)
    ratio = SequenceMatcher(None, orig_clean, rec_clean).ratio()
    return int(ratio * 100)

# --- 3. Streamlit UI 구성 ---

st.set_page_config(page_title="AI 유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")

# 사이드바: 디버깅 및 가이드
with st.sidebar:
    st.header("⚙️ 시스템 정보")
    st.write(f"API 버전: {yt_api_version}")
    st.divider()
    st.header("💡 학습 가이드")
    st.write("1. 유튜브 영상 주소를 입력하세요.")
    st.write("2. 핵심 단어와 문장을 확인하세요.")
    st.write("3. 원어민 발음을 듣고 따라 하세요.")
    st.write("4. AI가 분석한 정확도를 확인하세요.")

url_input = st.text_input("유튜브 영상 주소를 입력하세요:", 
                         value="https://www.youtube.com/watch?v=M7BWHPtV1qM",
                         placeholder="https://www.youtube.com/watch?v=...")

if url_input:
    video_id = get_video_id(url_input)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
    else:
        # 자막 로드 시도
        transcript_data = fetch_transcript_robust(video_id)
        
        if transcript_data:
            # 텍스트 분석 (단어 10개, 문장 10개 추출)
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (불용어 제외, 4글자 이상)
            common_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 주요 문장 10개 (길이가 적당한 문장 위주)
            common_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 8 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 레이아웃 구성 (단어 학습 | 문장 학습)
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔤 핵심 단어 학습 (10)")
                st.write("한국어 설명: 발음 기호를 보고 소리를 들은 후 따라 하세요.")
                for i, word in enumerate(common_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음 기호:** [{ipa.convert(word)}]")
                        st.audio(generate_tts(word), format="audio/mp3")
                        
                        st.write("🎙️ 나의 발음 녹음:")
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
                                    st.warning("인식을 위해 조금 더 명확하게 발음해 주세요.")

            with col2:
                st.header("📝 주요 문장 학습 (10)")
                st.write("한국어 설명: 문장의 억양과 호흡을 원어민과 비교하며 연습하세요.")
                for i, sent in enumerate(common_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
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
            st.info("팁: 다른 영상을 시도하거나, 잠시 후 다시 시도해 주세요.")
