import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re
from collections import Counter
import eng_to_ipa as ipa
from gtts import gTTS
import io
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from difflib import SequenceMatcher

# 페이지 설정
st.set_page_config(page_title="YouTube 영어 학습 도구", layout="wide")

st.title("📺 유튜브 기반 영어 학습 매니저")
st.info("유튜브 주소를 입력하면 AI가 핵심 단어와 문장을 추출하고 발음을 교정해줍니다.")

# 1. 유튜브 주소 입력
url = st.text_input("유튜브 영상 주소를 입력하세요 (예: https://www.youtube.com/watch?v=...)")

def get_video_id(url):
    video_id = re.search(r"(?<=v=)[^&#]+", url)
    if not video_id:
        video_id = re.search(r"(?<=be/)[^&#]+", url)
    return video_id.group(0) if video_id else None

def play_audio(text):
    tts = gTTS(text=text, lang='en')
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    return fp

def calculate_score(original, speech):
    # 단순 문자열 유사도를 기반으로 하되, 실제 서비스 시에는 Azure/Google Speech API의 상세 메타데이터 권장
    similarity = SequenceMatcher(None, original.lower(), speech.lower()).ratio()
    return int(similarity * 100)

if url:
    try:
        video_id = get_video_id(url)
        # 자막 가져오기 (영어)
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        full_text = " ".join([t['text'] for t in transcript_list])
        
        # 2. 단어 분석 (단어 10개)
        words = re.findall(r'\w+', full_text.lower())
        # 불용어(Stopwords)를 제외하면 더 정확합니다. 여기서는 빈도순 10개
        common_words = [word for word, count in Counter(words).most_common(10)]
        
        # 3. 문장 분석 (긴 문장 중 대표성 있는 10개 추출)
        sentences = [t['text'] for t in transcript_list if len(t['text'].split()) > 5][:10]

        st.divider()

        # UI 출력: 한국어 설명 -> 영어 순서
        col1, col2 = st.columns(2)

        with col1:
            st.header("🔑 중요 단어 학습")
            for word in common_words:
                phonetic = ipa.convert(word)
                st.subheader(f"{word} [{phonetic}]")
                
                # 원어민 발음 듣기
                audio_data = play_audio(word)
                st.audio(audio_data, format="audio/mp3")
                
                # 따라하기 기능
                st.write(f"'{word}' 발음을 따라해보세요:")
                record = mic_recorder(key=f"word_{word}", start_prompt="🎙️ 녹음 시작", stop_prompt="⏹️ 중지")
                
                if record:
                    recognizer = sr.Recognizer()
                    audio_file = io.BytesIO(record['bytes'])
                    with sr.AudioFile(audio_file) as source:
                        audio = recognizer.record(source)
                        try:
                            user_speech = recognizer.recognize_google(audio, language='en-US')
                            score = calculate_score(word, user_speech)
                            st.write(f"인식 결과: **{user_speech}**")
                            st.metric("정확도 (발음/호흡/유사도)", f"{score}%")
                        except:
                            st.error("발음을 인식하지 못했습니다. 다시 시도해주세요.")

        with col2:
            st.header("📝 중요 문장 학습")
            for i, sentence in enumerate(sentences):
                st.write(f"**Sentence {i+1}**")
                st.info(sentence)
                
                # 원어민 발음 듣기
                sent_audio = play_audio(sentence)
                st.audio(sent_audio, format="audio/mp3")
                
                # 따라하기 기능
                st.write("문장을 읽어보세요:")
                sent_record = mic_recorder(key=f"sent_{i}", start_prompt="🎙️ 문장 녹음", stop_prompt="⏹️ 중지")
                
                if sent_record:
                    recognizer = sr.Recognizer()
                    audio_file = io.BytesIO(sent_record['bytes'])
                    with sr.AudioFile(audio_file) as source:
                        audio = recognizer.record(source)
                        try:
                            user_speech = recognizer.recognize_google(audio, language='en-US')
                            score = calculate_score(sentence, user_speech)
                            st.write(f"인식 결과: **{user_speech}**")
                            st.write(f"정확도: **{score}%**")
                            st.progress(score / 100)
                        except:
                            st.error("음성을 인식하지 못했습니다.")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
