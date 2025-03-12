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

# הגדרת OpenAI API Key
openai.api_key = st.secrets["openai"]["api_key"]

# פונקציה לקבלת רשימת תיקיות ב-Google Drive
def list_drive_folders():
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    return results.get('files', [])

# פונקציה לפיצול קבצי אודיו גדולים
def split_audio(file_path, chunk_size_mb=24):
    audio_clip = VideoFileClip(file_path).audio
    duration = audio_clip.duration
    chunk_duration = (chunk_size_mb * 1024 * 1024) / (audio_clip.fps * audio_clip.nchannels * 2)
    chunks = []
    start = 0

    while start < duration:
        end = min(start + chunk_duration, duration)
        chunk_filename = f"temp_audio_{len(chunks)}.mp3"
        audio_clip.subclip(start, end).write_audiofile(chunk_filename)
        chunks.append(chunk_filename)
        start = end

    audio_clip.close()
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
            continue

        for video in videos:
            video_name = video['name']
            st.write(f"תהליך תמלול של הסרטון: {video_name}")

            request = service.files().get_media(fileId=video['id'])
            video_bytes = io.BytesIO()
            downloader = MediaIoBaseDownload(video_bytes, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                st.progress(status.progress(), text=f"מוריד סרטון: {int(status.progress() * 100)}%")

            video_bytes.seek(0)

            with open("temp_video.mp4", "wb") as f:
                f.write(video_bytes.read())

            audio_chunks = split_audio("temp_video.mp4")

            full_transcript = ""
            total_chunks = len(audio_chunks)

            progress_bar = st.progress(0, text="מתמלל...")

            for i, audio_chunk in enumerate(audio_chunks):
                with open(audio_chunk, "rb") as audio_file:
                    transcript_response = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="he",
                        response_format="verbose_json",
                        prompt="שיחה בעברית בנושא מסחר באמזון, מוצרים, והקמת ליסטים."
                    )
                
                full_transcript += transcript_response.text + "\n\n"
                progress_bar.progress((i + 1) / total_chunks, text=f"מתמלל קטע {i + 1}/{total_chunks}")

                os.remove(audio_chunk)

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
