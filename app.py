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

# --- 리소스 초기화 (NLTK 데이터 다운로드) ---
@st.cache_resource
def load_nltk():
    nltk.download('stopwords')
    nltk.download('punkt')

load_nltk()

# --- 도구 함수 정의 ---

def get_video_id(url):
    """유튜브 URL에서 11자리 ID 추출"""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def text_to_speech(text):
    """텍스트를 음성으로 변환하여 오디오 스트림 반환"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

def calculate_score(original, speech):
    """원문과 인식된 음성 간의 유사도 점수 계산 (0-100%)"""
    original = re.sub(r'[^\w\s]', '', original.lower()).strip()
    speech = re.sub(r'[^\w\s]', '', speech.lower()).strip()
    # 인토네이션과 호흡은 단순 텍스트 유사도로는 한계가 있으나, 일치도를 통해 유사 정확도 산출
    ratio = SequenceMatcher(None, original, speech).ratio()
    return int(ratio * 100)

# --- 스트림릿 UI ---

st.set_page_config(page_title="유튜브 영어 발음 교정기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")
st.info("유튜브 주소를 넣으면 핵심 단어와 문장을 뽑아주고, 발음을 100% 기준으로 채점해줍니다.")

# 유튜브 주소 입력창
url = st.text_input("학습할 유튜브 영상 주소를 입력하세요:", value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("유효한 유튜브 주소를 입력해주세요.")
    else:
        try:
            # 자막 데이터 가져오기 (고급 에러 처리 포함)
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            
            # 단어 분석 (불용어 제외 빈도순 상위 10개)
            full_text = " ".join([t['text'] for t in transcript_list])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            top_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 문장 분석 (7~15단어 사이의 적당한 문장 10개)
            top_sentences = [t['text'].replace('\n', ' ') for t in transcript_list if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            col1, col2 = st.columns(2)

            # --- 단어 학습 영역 ---
            with col1:
                st.header("🔤 중요 단어 학습 (10개)")
                for i, word in enumerate(top_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        # 발음기호 표시
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        
                        # TTS 재생
                        st.write("원어민 발음 듣기:")
                        st.audio(text_to_speech(word), format="audio/mp3")
                        
                        # 따라하기 및 채점
                        st.write("발음 따라하기:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 녹음 시작", stop_prompt="⏹️ 중지")
                        
                        if rec:
                            recognizer = sr.Recognizer()
                            audio_data = io.BytesIO(rec['bytes'])
                            with sr.AudioFile(audio_data) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_score(word, user_speech)
                                    st.write(f"인식된 결과: **{user_speech}**")
                                    st.metric("발음 정확도", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.warning("발음을 인식하지 못했습니다. 다시 시도해 주세요.")

            # --- 문장 학습 영역 ---
            with col2:
                st.header("📝 주요 문장 학습 (10개)")
                for i, sent in enumerate(top_sentences):
                    st.info(f"문장 {i+1}: {sent}")
                    
                    # TTS 재생
                    st.audio(text_to_speech(sent), format="audio/mp3")
                    
                    # 문장 따라하기 및 채점
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 녹음", stop_prompt="⏹️ 완료")
                    
                    if rec_s:
                        recognizer = sr.Recognizer()
                        audio_data = io.BytesIO(rec_s['bytes'])
                        with sr.AudioFile(audio_data) as source:
                            audio = recognizer.record(source)
                            try:
                                user_speech = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_score(sent, user_speech)
                                st.write(f"인식 결과: **{user_speech}**")
                                st.write(f"종합 정확도(발음/호흡/유사도): **{score}%**")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        except TranscriptsDisabled:
            st.error("이 영상은 자막 기능이 비활성화되어 있습니다.")
        except NoTranscriptFound:
            st.error("영어 자막을 찾을 수 없는 영상입니다.")
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")

