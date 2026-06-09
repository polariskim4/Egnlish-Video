import streamlit as st
import youtube_transcript_api
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

# NLTK 데이터 다운로드 (캐싱 처리)
@st.cache_resource
def load_nltk():
    nltk.download('stopwords')
    nltk.download('punkt')

load_nltk()

def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_accuracy(original, speech):
    original = re.sub(r'[^\w\s]', '', original.lower()).strip()
    speech = re.sub(r'[^\w\s]', '', speech.lower()).strip()
    return int(SequenceMatcher(None, original, speech).ratio() * 100)

st.set_page_config(page_title="유튜브 영어 발음 교정", layout="wide")
st.title("📺 AI 유튜브 영어 학습기")

url = st.text_input("학습할 유튜브 주소 입력:", value="https://www.youtube.com/watch?v=jhEtBuuYNj4")

if url:
    video_id = get_video_id(url)
    if video_id:
        try:
            # 오류 해결을 위한 핵심 변경 구간: list_transcripts 방식을 사용하여 우회
            # 기존 YouTubeTranscriptApi.get_transcript(video_id) 대신 아래 방식을 사용합니다.
            transcript_list = youtube_transcript_api.YouTubeTranscriptApi.list_transcripts(video_id)
            # 영어 자막 선택 (수동 자막 우선, 없으면 자동생성)
            transcript_obj = transcript_list.find_transcript(['en'])
            transcript = transcript_obj.fetch()
            
            # 단어/문장 추출 로직
            full_text = " ".join([t['text'] for t in transcript])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            top_words = [w for w, c in Counter(words).most_common(80) if w not in stop_words and len(w) > 3][:10]
            top_sentences = [t['text'].replace('\n', ' ') for t in transcript if 7 < len(t['text'].split()) < 15][:10]

            st.divider()
            c1, c2 = st.columns(2)

            with c1:
                st.header("🔑 핵심 단어")
                for i, word in enumerate(top_words):
                    with st.expander(f"{word.upper()}"):
                        st.write(f"발음기호: [{ipa.convert(word)}]")
                        tts = gTTS(text=word, lang='en')
                        fp = io.BytesIO()
                        tts.write_to_fp(fp)
                        st.audio(fp)
                        
                        # 녹음 기능
                        rec = mic_recorder(key=f"w_{i}", start_prompt="🎙️ 따라하기", stop_prompt="⏹️ 완료")
                        if rec:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(rec['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = get_accuracy(word, user_speech)
                                    st.write(f"인식: {user_speech} (정확도: {score}%)")
                                except: st.error("인식 실패")

            with c2:
                st.header("📝 주요 문장")
                for i, sent in enumerate(top_sentences):
                    st.info(sent)
                    tts_s = gTTS(text=sent, lang='en')
                    fp_s = io.BytesIO()
                    tts_s.write_to_fp(fp_s)
                    st.audio(fp_s)
                    
                    rec_s = mic_recorder(key=f"s_{i}", start_prompt="🎙️ 문장 연습", stop_prompt="⏹️ 완료")
                    if rec_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(rec_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                user_speech = recognizer.recognize_google(audio, language='en-US')
                                score = get_accuracy(sent, user_speech)
                                st.write(f"결과: {user_speech} / 정확도: {score}%")
                            except: st.error("인식 실패")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.write("도움말: 영상에 자막이 없거나 라이브러리 호환성 문제일 수 있습니다.")
