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

# --- 초기 설정 및 캐싱 ---
@st.cache_resource
def init_nltk():
    try:
        nltk.download('stopwords')
        nltk.download('punkt')
    except:
        pass

init_nltk()

def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def calculate_accuracy(original, user_input):
    original_clean = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user_input_clean = re.sub(r'[^\w\s]', '', user_input.lower()).strip()
    return int(SequenceMatcher(None, original_clean, user_input_clean).ratio() * 100)

# --- UI 레이아웃 ---
st.set_page_config(page_title="유튜브 영어 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 학습 매니저")
st.info("유튜브 주소를 입력하면 핵심 단어와 문장을 추출하고 발음을 교정해줍니다.")

# 사이드바에 사용법 안내
with st.sidebar:
    st.header("💡 사용법")
    st.write("1. 유튜브 URL 입력")
    st.write("2. 핵심 단어/문장 확인")
    st.write("3. 스피커로 발음 듣기")
    st.write("4. 마이크로 따라하며 점수 확인")

url = st.text_input("학습할 유튜브 주소 입력:", value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    v_id = get_video_id(url)
    if v_id:
        try:
            # 자막 데이터 로드 (클래스 메서드 직접 호출)
            transcript_list = YouTubeTranscriptApi.get_transcript(v_id, languages=['en'])
            
            # 텍스트 분석
            full_text = " ".join([t['text'] for t in transcript_list])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 추출
            important_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 중요 문장 10개 추출
            important_sentences = [t['text'].replace('\n', ' ') for t in transcript_list if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.header("🔤 핵심 단어")
                for i, word in enumerate(important_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        
                        # TTS
                        tts = gTTS(text=word, lang='en')
                        fp = io.BytesIO()
                        tts.write_to_fp(fp)
                        st.audio(fp, format="audio/mp3")
                        
                        # 녹음
                        rec = mic_recorder(key=f"w_{i}", start_prompt="🎙️ 따라하기", stop_prompt="⏹️ 완료")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = calculate_accuracy(word, user_speech)
                                    st.write(f"인식: **{user_speech}**")
                                    st.metric("정확도", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.error("인식 실패. 다시 해보세요!")

            with col2:
                st.header("📝 주요 문장")
                for i, sent in enumerate(important_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    tts_s = gTTS(text=sent, lang='en')
                    fp_s = io.BytesIO()
                    tts_s.write_to_fp(fp_s)
                    st.audio(fp_s, format="audio/mp3")
                    
                    rec_s = mic_recorder(key=f"s_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="⏹️ 완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_speech = recognizer.recognize_google(audio, language='en-US')
                                score = calculate_accuracy(sent, user_speech)
                                st.write(f"인식: **{user_speech}** (정확도: {score}%)")
                                st.progress(score / 100)
                            except:
                                st.error("음성 인식에 실패했습니다.")
                    st.divider()

        except TranscriptsDisabled:
            st.error("이 영상은 자막이 비활성화되어 있습니다.")
        except NoTranscriptFound:
            st.error("영어 자막을 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
    else:
        st.warning("유효한 유튜브 주소를 입력하세요.")
