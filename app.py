import streamlit as st
import youtube_transcript_api as yta # 모듈 전체를 별칭으로 안전하게 가져옴
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

# --- 리소스 설정 ---
@st.cache_resource
def download_nltk():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

download_nltk()

def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_tts_audio(text):
    tts = gTTS(text=text, lang='en')
    audio_fp = io.BytesIO()
    tts.write_to_fp(audio_fp)
    audio_fp.seek(0)
    return audio_fp

def calculate_accuracy(original, recorded):
    # 정규화: 소문자화 및 특수문자 제거
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    # 문자열 유사도 기반 점수 산출
    ratio = SequenceMatcher(None, orig_clean, user_clean).ratio()
    return int(ratio * 100)

# --- UI 레이아웃 ---
st.set_page_config(page_title="AI 유튜브 영어 학습", layout="wide")
st.title("📺 AI 유튜브 영어 발음 교정 서비스")
st.info("유튜브 영상의 자막을 분석하여 핵심 표현을 추출하고 발음 정확도를 체크합니다.")

url = st.text_input("유튜브 영상 주소를 입력하세요 (한국어 가이드 -> 영어 학습 순):", 
                   value="https://www.youtube.com/watch?v=M7BWHPtV1qM")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("유효하지 않은 유튜브 주소입니다.")
    else:
        try:
            # [해결 포인트] 가장 명시적인 경로로 메서드 호출 (AttributeError 방지)
            transcript_data = yta.YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            
            # 분석: 단어 및 문장 추출
            full_text = " ".join([t['text'] for t in transcript_data])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (길이 4자 이상, 불용어 제외)
            top_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 중요 문장 10개 (적당한 길이의 문장 추출)
            top_sentences = [t['text'].replace('\n', ' ') for t in transcript_data if 8 < len(t['text'].split()) < 15][:10]

            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔑 핵심 단어 학습")
                st.write("단어를 확인하고 원어민 발음을 들은 뒤 따라해보세요.")
                for i, word in enumerate(top_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        st.audio(get_tts_audio(word), format="audio/mp3")
                        
                        st.write("🎙️ 발음을 녹음하세요:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="녹음 시작", stop_prompt="중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_text = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_text)
                                    st.write(f"인식 결과: **{user_text}**")
                                    st.metric("정확도 점수", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.error("발음이 명확하지 않습니다. 다시 시도해주세요.")

            with col2:
                st.header("📝 주요 문장 학습")
                st.write("문장 전체의 인토네이션과 호흡을 연습해보세요.")
                for i, sent in enumerate(top_sentences):
                    st.info(f"문장 {i+1}: {sent}")
                    st.audio(get_tts_audio(sent), format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_text = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_accuracy(sent, user_text)
                                st.write(f"인식 결과: **{user_text}**")
                                st.write(f"정확도: **{score}%**")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.warning("영상의 자막 설정이 되어 있는지 확인해 주세요.")
