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

# --- 리소스 설정 (NLTK 데이터 다운로드) ---
@st.cache_resource
def load_nltk():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)

load_nltk()

# --- 도구 함수 ---
def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_tts_audio(text):
    """gTTS를 사용하여 원어민 발음 생성"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

def calculate_accuracy(original, recorded):
    """발음 정확도를 유사도 기반으로 채점 (0-100%)"""
    orig_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user_clean = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    return int(SequenceMatcher(None, orig_clean, user_clean).ratio() * 100)

# --- 메인 UI ---
st.set_page_config(page_title="유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 & 발음 교정")
st.markdown("유튜브 자막을 분석하여 핵심 표현을 공부하고 나의 발음 정확도를 체크해보세요.")

url = st.text_input("유튜브 주소를 입력하세요 (한국어 가이드 -> 영어 학습 순):", 
                   value="https://www.youtube.com/watch?v=M7BWHPtV1qM")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해주세요.")
    else:
        try:
            # [해결책] 자막 로드 방식 변경: list_transcripts 사용
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            # 영어 자막(수동 또는 자동 생성) 가져오기
            transcript = transcript_list.find_transcript(['en']).fetch()
            
            # 텍스트 분석
            full_text = " ".join([t['text'] for t in transcript])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (4글자 이상, 불용어 제외)
            top_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 중요 문장 10개 (가독성 좋은 길이 추출)
            top_sentences = [t['text'].replace('\n', ' ') for t in transcript if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            
            # 탭을 활용한 레이아웃
            tab_word, tab_sent = st.tabs(["🔤 핵심 단어 10", "📝 주요 문장 10"])

            with tab_word:
                st.write("### 단어별 발음 기호를 확인하고 따라해보세요.")
                for i, word in enumerate(top_words):
                    col1, col2, col3 = st.columns([2, 2, 4])
                    with col1:
                        st.subheader(f"{i+1}. {word.upper()}")
                        st.write(f"[{ipa.convert(word)}]")
                    with col2:
                        st.write("원어민 발음:")
                        st.audio(get_tts_audio(word), format="audio/mp3")
                    with col3:
                        st.write("나의 발음 녹음:")
                        rec = mic_recorder(key=f"word_{i}", start_prompt="🎙️ 녹음", stop_prompt="⏹️ 중지")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_speech)
                                    st.write(f"인식: **{user_speech}**")
                                    st.metric("정확도", f"{score}%")
                                except:
                                    st.warning("인식 실패. 다시 해보세요.")

            with tab_sent:
                st.write("### 문장의 전체적인 호흡과 인토네이션을 연습하세요.")
                for i, sent in enumerate(top_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    st.audio(get_tts_audio(sent), format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 따라하기", stop_prompt="⏹️ 완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_speech = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_accuracy(sent, user_speech)
                                st.write(f"인식: **{user_speech}** | 정확도: **{score}%**")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.warning("유튜브 자막이 비활성화되어 있거나, 일시적인 네트워크 오류일 수 있습니다.")
