import streamlit as st
import youtube_transcript_api as yta
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

# --- 리소스 및 NLTK 설정 ---
@st.cache_resource
def setup_resources():
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    return True

setup_resources()

def get_video_id(url):
    """유튜브 URL에서 비디오 ID 추출"""
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match.group(1) if match else None

def get_accuracy_score(original, recorded):
    """텍스트 유사도를 통한 발음 정확도 측정 (0-100%)"""
    orig = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user = re.sub(r'[^\w\s]', '', recorded.lower()).strip()
    return int(SequenceMatcher(None, orig, user).ratio() * 100)

def play_voice(text):
    """Google TTS를 이용한 원어민 발음 생성"""
    tts = gTTS(text=text, lang='en')
    audio_fp = io.BytesIO()
    tts.write_to_fp(audio_fp)
    audio_fp.seek(0)
    return audio_fp

# --- Streamlit UI 시작 ---
st.set_page_config(page_title="AI 영어 발음 학습기", layout="wide")
st.title("📺 AI 유튜브 영어 발음 교정 서비스")
st.info("유튜브 영상의 자막을 분석하여 핵심 표현을 배우고 발음 정확도를 체크합니다.")

url_input = st.text_input("유튜브 영상 주소 (URL)를 입력하세요:", value="https://www.youtube.com/watch?v=M7BWHPtV1qM")

if url_input:
    video_id = get_video_id(url_input)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
    else:
        try:
            # [해결책] AttributeError 방지를 위한 모듈 직접 접근 방식
            # YouTubeTranscriptApi 클래스 내의 get_transcript 메서드를 직접 호출합니다.
            if hasattr(yta, 'YouTubeTranscriptApi'):
                transcript = yta.YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            else:
                # 만약 클래스 참조가 실패할 경우 모듈 수준에서 다시 시도
                st.error("라이브러리 로드 오류가 발생했습니다. 저장소를 다시 빌드해 주세요.")
                st.stop()
            
            # 자막 분석 (단어 10개, 문장 10개)
            full_text = " ".join([t['text'] for t in transcript])
            words = re.findall(r'\b\w+\b', full_text.lower())
            stop_words = set(stopwords.words('english'))
            
            # 중요 단어 10개 (불용어 제외, 4글자 이상)
            common_words = [w for w, c in Counter(words).most_common(100) if w not in stop_words and len(w) > 3][:10]
            
            # 주요 문장 10개 (길이가 적당한 문장 위주)
            common_sentences = [t['text'].replace('\n', ' ') for t in transcript if 8 < len(t['text'].split()) < 15][:10]

            st.divider()
            word_col, sent_col = st.columns(2)

            with word_col:
                st.header("🔤 핵심 단어 학습")
                st.caption("발음기호 확인 -> 원어민 발음 듣기 -> 내 발음 녹음 순서")
                for i, word in enumerate(common_words):
                    with st.expander(f"{i+1}. {word.upper()}"):
                        st.write(f"**발음기호:** [{ipa.convert(word)}]")
                        st.audio(play_voice(word), format="audio/mp3")
                        
                        st.write("🎙️ 따라해 보세요:")
                        record = mic_recorder(key=f"word_{i}", start_prompt="녹음 시작", stop_prompt="중지")
                        if record:
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(io.BytesIO(record['bytes'])) as source:
                                audio = recognizer.record(source)
                                try:
                                    speech_text = recognizer.recognize_google(audio, language='en-US')
                                    score = get_accuracy_score(word, speech_text)
                                    st.write(f"인식 결과: **{speech_text}**")
                                    st.metric("발음 정확도", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.error("인식에 실패했습니다. 다시 시도해 주세요.")

            with sent_col:
                st.header("📝 주요 문장 학습")
                st.caption("문장 전체를 듣고 정확한 호흡과 인토네이션을 연습하세요.")
                for i, sent in enumerate(common_sentences):
                    st.info(f"Sentence {i+1}: {sent}")
                    st.audio(play_voice(sent), format="audio/mp3")
                    
                    record_s = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 연습 시작", stop_prompt="완료")
                    if record_s:
                        recognizer = sr.Recognizer()
                        with sr.AudioFile(io.BytesIO(record_s['bytes'])) as source:
                            audio = recognizer.record(source)
                            try:
                                speech_text = recognizer.recognize_google(audio, language='en-US')
                                score = get_accuracy_score(sent, speech_text)
                                st.write(f"인식 결과: **{speech_text}**")
                                st.write(f"종합 정확도 점수: **{score}%**")
                                st.progress(score / 100)
                            except:
                                st.error("음성을 인식할 수 없습니다.")
                    st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.warning("영상의 자막 설정이 되어 있는지, 또는 라이브러리가 정상 설치되었는지 확인해 주세요.")

