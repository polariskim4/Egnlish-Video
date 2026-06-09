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

# NLTK 데이터 다운로드
@st.cache_resource
def init_nltk():
    nltk.download('stopwords')

init_nltk()

st.set_page_config(page_title="영어 학습 도구", layout="wide")
st.title("📺 유튜브 영어 학습 매니저")

# 1. 유튜브 주소 입력
url = st.text_input("유튜브 주소를 입력하세요:")

def get_accuracy(original, speech):
    return int(SequenceMatcher(None, original.lower(), speech.lower()).ratio() * 100)

if url:
    video_id = re.search(r"(?<=v=)[^&#]+", url) or re.search(r"(?<=be/)[^&#]+", url)
    if video_id:
        try:
            v_id = video_id.group(0)
            transcript = YouTubeTranscriptApi.get_transcript(v_id, languages=['en'])
            full_text = " ".join([t['text'] for t in transcript])
            
            # 중요 단어 10개 (불용어 제외)
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            important_words = [w for w, c in Counter(words).most_common(50) if w not in stop_words and len(w) > 3][:10]
            
            # 중요 문장 10개
            sentences = [t['text'] for t in transcript if len(t['text'].split()) > 7][:10]

            col1, col2 = st.columns(2)

            with col1:
                st.header("🔑 중요 단어")
                for word in important_words:
                    st.subheader(f"{word} [{ipa.convert(word)}]")
                    # TTS
                    tts = gTTS(word, lang='en')
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    st.audio(fp)
                    
                    # 녹음 및 평가
                    rec = mic_recorder(key=f"w_{word}", start_prompt="따라하기", stop_prompt="중지")
                    if rec:
                        # 발음 평가 로직 (Google STT 사용)
                        pass 

            with col2:
                st.header("📝 중요 문장")
                for i, sent in enumerate(sentences):
                    st.info(sent)
                    tts_s = gTTS(sent, lang='en')
                    fp_s = io.BytesIO()
                    tts_s.write_to_fp(fp_s)
                    st.audio(fp_s)

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
