import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
from moviepy.editor import VideoFileClip
import openai
import os
import math

# חיבור ל-Google Drive
@st.cache_resource
def connect_to_drive():
    creds_info = json.loads(st.secrets["google_credentials"]["credentials_json"])
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

service = connect_to_drive()

# OpenAI API Key
openai.api_key = st.secrets["openai"]["api_key"]

# קבלת רשימת תיקיות ב-Google Drive
def list_drive_folders():
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    return results.get('files', [])

# פונקציה לפיצול קובץ אודיו גדול
def split_audio(audio_path, max_size_mb=24):
    audio_clip = VideoFileClip(audio_path)
    audio_length = audio_clip.duration
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    num_parts = math.ceil(file_size_mb / max_size_mb)

    part_duration = audio_length / num_parts
    audio_parts = []

    for i in range(num_parts):
        start = i * part_duration
        end = min((i + 1) * part_duration, audio_length)
        part_path = f"temp_audio_part_{i}.mp3"
        audio_clip.subclip(start, end).audio.write_audiofile(part_path)
        audio_parts.append(part_path)

    audio_clip.close()
    return audio_parts

# Streamlit UI
st.title('🎬 Auto Video Transcriber')
st.write("בחר את התיקייה או התיקיות לסריקה:")

folders = list_drive_folders()
folder_options = {folder['name']: folder['id'] for folder in folders}
selected_folders = st.multiselect("בחר תיקיות", list(folder_options.keys()))

# אפשרות לבחור איכות התמלול
model_quality = st.selectbox("בחר את איכות התמלול (דגם Whisper):", ["tiny", "base", "small", "medium", "large"], index=2)

if st.button("התחל סריקה ותמלול"):
    for folder_name in selected_folders:
        folder_id = folder_options[folder_name]
        st.write(f"סריקת תיקייה: {folder_name}")

        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'video/'",
            fields="files(id, name, size)"
        ).execute()
        videos = results.get('files', [])

        if not videos:
            st.write("לא נמצאו סרטונים.")
        else:
            for video in videos:
                video_name = video['name']
                st.write(f"תהליך תמלול של הסרטון: {video_name}")

                request = service.files().get_media(fileId=video['id'])
                video_bytes = io.BytesIO()
                downloader = MediaIoBaseDownload(video_bytes, request)

                done = False
                progress_bar = st.progress(0)
                while not done:
                    status, done = downloader.next_chunk()
                    progress_bar.progress(int(status.progress() * 100))

                video_bytes.seek(0)

                with open("temp_video.mp4", "wb") as f:
                    f.write(video_bytes.read())

                video_clip = VideoFileClip("temp_video.mp4")
                video_clip.audio.write_audiofile("temp_audio.mp3")
                video_clip.close()

                audio_size_mb = os.path.getsize("temp_audio.mp3") / (1024 * 1024)
                st.write(f"גודל קובץ האודיו (MP3): {audio_size_mb:.2f} MB")

                audio_files = []
                if audio_size_mb > 24:
                    st.info("קובץ האודיו גדול - מבצע פיצול לחלקים קטנים.")
                    audio_files = split_audio("temp_video.mp4")
                else:
                    audio_files = ["temp_audio.mp3"]

                full_transcript = ""
                transcript_status = st.empty()

                for i, audio_file_path in enumerate(audio_files):
                    transcript_status.write(f"מתמלל חלק {i+1}/{len(audio_files)}...")
                    with open(audio_file_path, "rb") as audio_file:
                        transcript_response = openai.audio.transcriptions.create(
                            model=f"whisper-1",
                            file=audio_file,
                            language="he",
                            response_format="text",
                            prompt="זהו סרטון בשפה העברית."
                        )
                    full_transcript += transcript_response + "\n\n"
                    os.remove(audio_file_path)

                transcript_status.write("✅ התמלול הושלם בהצלחה!")

                transcript_bytes = io.BytesIO(full_transcript.encode('utf-8'))

                transcript_metadata = {
                    'name': f"{video_name}.txt",
                    'parents': [folder_id]
                }

                media = MediaIoBaseUpload(transcript_bytes, mimetype='text/plain', resumable=True)
                service.files().create(
                    body=transcript_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                st.success(f"קובץ תמלול נשמר: {video_name}.txt")

                os.remove("temp_video.mp4")
                if os.path.exists("temp_audio.mp3"):
                    os.remove("temp_audio.mp3")
