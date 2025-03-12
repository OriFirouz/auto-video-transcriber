import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
from moviepy.editor import VideoFileClip
import openai
import os
from pydub import AudioSegment
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

# הגדרת OpenAI API Key
openai.api_key = st.secrets["openai"]["api_key"]

# פונקציה לקבלת רשימת תיקיות ב-Google Drive
def list_drive_folders():
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    return results.get('files', [])

# פונקציה לפיצול אודיו לחלקים של פחות מ-25MB
def split_audio(audio_path, chunk_size_mb=24):
    audio = AudioSegment.from_file(audio_path)
    audio_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    if audio_size_mb <= chunk_size_mb:
        return [audio_path]

    chunk_length_ms = math.ceil((chunk_size_mb / audio_size_mb) * len(audio))
    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start:start + chunk_length_ms]
        chunk_filename = f"{audio_path}_chunk{i}.mp3"
        chunk.export(chunk_filename, format="mp3")
        chunks.append(chunk_filename)

    return chunks

# Streamlit UI
st.title('🎬 Auto Video Transcriber')
st.write("בחר את התיקייה או התיקיות לסריקה:")

folders = list_drive_folders()
folder_options = {folder['name']: folder['id'] for folder in folders}
selected_folders = st.multiselect("בחר תיקיות", list(folder_options.keys()))

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
                while not done:
                    status, done = downloader.next_chunk()
                    st.write(f"הורדת וידאו: {int(status.progress() * 100)}%")

                video_bytes.seek(0)

                with open("temp_video.mp4", "wb") as f:
                    f.write(video_bytes.read())

                video_clip = VideoFileClip("temp_video.mp4")
                video_clip.audio.write_audiofile("temp_audio.mp3")
                video_clip.close()

                audio_chunks = split_audio("temp_audio.mp3")

                full_transcript = ""

                for chunk_path in audio_chunks:
                    with open(chunk_path, "rb") as audio_file:
                        transcript_response = openai.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="he"
                        )
                        full_transcript += transcript_response.text + "\n"
                    os.remove(chunk_path)

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
                os.remove("temp_audio.mp3")
