import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def fetch_youtube_transcript(video_id):
    """
    YouTubeTranscriptApi의 정적 메서드인 get_transcript를 안전하게 호출합니다.
    """
    try:
        # 클래스명에서 직접 정적 메서드(static method)를 호출해야 합니다.
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'ko'])
        return transcript_list
    except TranscriptsDisabled:
        st.error("이 영상은 자막 기능이 비활성화되어 있습니다.")
    except NoTranscriptFound:
        st.error("해당 영상에서 요청한 언어의 자막을 찾을 수 없습니다.")
    except Exception as e:
        # 예상치 못한 다른 에러 처리
        st.error(f"자막을 가져오는 중 오류가 발생했습니다: {str(e)}")
    return None

# Streamlit UI 예시
video_url = st.text_input("유튜브 URL을 입력하세요")

if video_url:
    # URL에서 11자리 비디오 ID 추출 (정규표현식 등을 사용하면 더 정확합니다)
    if 'v=' in video_url:
        video_id = video_url.split('v=')[1][:11]
        transcript_data = fetch_youtube_transcript(video_id)
        
        if transcript_data:
            st.success("자막 데이터를 성공적으로 가져왔습니다.")
            # 추출된 자막을 이용한 분석 로직 수행
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

# NLTK 데이터 다운로드 (중요 단어 필터링용)
@st.cache_resource
def download_nltk_data():
    nltk.download('stopwords')
    nltk.download('punkt')

download_nltk_data()

# --- 도구 함수 정의 ---

def get_video_id(url):
    """유튜브 URL에서 11자리 비디오 ID 추출"""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_accuracy(original, user_input):
    """두 문장 간의 유사도를 100% 기준으로 계산"""
    original = re.sub(r'[^\w\s]', '', original.lower()).strip()
    user_input = re.sub(r'[^\w\s]', '', user_input.lower()).strip()
    return int(SequenceMatcher(None, original, user_input).ratio() * 100)

def text_to_speech(text):
    """gTTS를 이용해 음성 데이터 생성"""
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp

# --- 스트림릿 UI 시작 ---

st.set_page_config(page_title="유튜브 영어 학습 매니저", layout="wide")
st.title("📺 유튜브 기반 AI 영어 학습 도구")
st.markdown("유튜브 주소를 입력하면 **핵심 단어 10개**와 **주요 문장 10개**를 추출하여 발음 교정을 도와줍니다.")

# 1. 유튜브 주소 입력
url = st.text_input("학습하고 싶은 유튜브 영상 주소를 입력하세요:", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = get_video_id(url)
    if not video_id:
        st.error("올바른 유튜브 주소를 입력해주세요.")
    else:
        try:
            # 2. 자막 데이터 가져오기
            with st.spinner('영상을 분석하여 자막을 추출하고 있습니다...'):
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
                full_text = " ".join([t['text'] for t in transcript])
                
                # 3. 중요 단어 10개 추출 (불용어 제외 및 4글자 이상)
                words = re.findall(r'\b\w+\b', full_text.lower())
                stop_words = set(stopwords.words('english'))
                filtered_words = [w for w in words if w not in stop_words and len(w) > 3]
                important_words = [item[0] for item in Counter(filtered_words).most_common(10)]
                
                # 4. 중요 문장 10개 추출 (너무 짧지 않은 문장 위주)
                important_sentences = [t['text'].replace('\n', ' ') for t in transcript if len(t['text'].split()) > 6][:10]

            st.divider()

            # 레이아웃 구성
            col1, col2 = st.columns(2)

            # --- 단어 학습 영역 ---
            with col1:
                st.header("🔤 핵심 단어 학습")
                st.caption("한국어 설명 -> 영어 발음기호 -> 원어민 발음 -> 따라하기 순서")
                
                for idx, word in enumerate(important_words):
                    with st.expander(f"{idx+1}. {word.upper()}"):
                        # 발음기호 표시
                        phonetic = ipa.convert(word)
                        st.write(f"**발음기호:** [{phonetic}]")
                        
                        # TTS 재생
                        audio_fp = text_to_speech(word)
                        st.audio(audio_fp, format='audio/mp3')
                        
                        # 녹음 및 평가
                        st.write("🎙️ 직접 발음해보세요:")
                        recorded_audio = mic_recorder(key=f"word_rec_{idx}", start_prompt="녹음 시작", stop_prompt="녹음 완료")
                        
                        if recorded_audio:
                            recognizer = sr.Recognizer()
                            audio_data = io.BytesIO(recorded_audio['bytes'])
                            with sr.AudioFile(audio_data) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = get_accuracy(word, user_speech)
                                    st.write(f"인식된 발음: **{user_speech}**")
                                    st.metric("정확도", f"{score}%")
                                    st.progress(score / 100)
                                except:
                                    st.warning("발음을 인식하지 못했습니다. 다시 시도해 주세요.")

            # --- 문장 학습 영역 ---
            with col2:
                st.header("📝 주요 문장 학습")
                st.caption("한국어 설명 -> 원어민 발음 -> 따라하기 순서")

                for idx, sentence in enumerate(important_sentences):
                    with st.container():
                        st.info(f"Sentence {idx+1}: {sentence}")
                        
                        # TTS 재생
                        sent_audio = text_to_speech(sentence)
                        st.audio(sent_audio, format='audio/mp3')
                        
                        # 녹음 및 평가
                        recorded_sent = mic_recorder(key=f"sent_rec_{idx}", start_prompt="문장 따라하기", stop_prompt="녹음 완료")
                        
                        if recorded_sent:
                            recognizer = sr.Recognizer()
                            audio_data = io.BytesIO(recorded_sent['bytes'])
                            with sr.AudioFile(audio_data) as source:
                                audio = recognizer.record(source)
                                try:
                                    user_speech = recognizer.recognize_google(audio, language='en-US')
                                    score = get_accuracy(sentence, user_speech)
                                    st.write(f"인식 결과: **{user_speech}**")
                                    st.write(f"정확도(인토네이션/유사도): **{score}%**")
                                    st.progress(score / 100)
                                except:
                                    st.warning("음성이 명확하지 않습니다.")
                        st.divider()

        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")
            st.info("팁: 영어 자막(CC)이 제공되는 영상인지 확인해 주세요.")

