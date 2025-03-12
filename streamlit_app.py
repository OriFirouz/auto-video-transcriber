import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
from moviepy.editor import VideoFileClip
import openai
import os

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

        # קבלת סרטוני הוידאו
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

                # הורדת הסרטון
                request = service.files().get_media(fileId=video['id'])
                video_bytes = io.BytesIO()
                downloader = MediaIoBaseDownload(video_bytes, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    st.write(f"הורדת וידאו: {int(status.progress() * 100)}%")

                video_bytes.seek(0)

                # בדיקת גודל הסרטון
                video_size_mb = int(video['size']) / (1024 * 1024)
                st.write(f"גודל הסרטון: {video_size_mb:.2f} MB")

                # המרת הסרטון ל-MP3
                with open("temp_video.mp4", "wb") as f:
                    f.write(video_bytes.read())

                video_clip = VideoFileClip("temp_video.mp4")
                video_clip.audio.write_audiofile("temp_audio.mp3")
                video_clip.close()

                audio_size_mb = os.path.getsize("temp_audio.mp3") / (1024 * 1024)
                st.write(f"גודל קובץ האודיו (MP3): {audio_size_mb:.2f} MB")

                if audio_size_mb > 25:
                    st.error("קובץ האודיו גדול מדי לתמלול (מעל 25MB). דלג לסרטון הבא.")
                    continue

                # שליחת קובץ האודיו לתמלול ב-OpenAI Whisper
                with open("temp_audio.mp3", "rb") as audio_file:
                    transcript_response = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="he"
                    )

                transcript_text = transcript_response.text

                # שמירת התמלול לקובץ טקסט בזיכרון
                transcript_bytes = io.BytesIO(transcript_text.encode('utf-8'))

                # העלאת קובץ התמלול בחזרה ל-Google Drive
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

                # מחיקת קבצים זמניים
                os.remove("temp_video.mp4")
                os.remove("temp_audio.mp3")
