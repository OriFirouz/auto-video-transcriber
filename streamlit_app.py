import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import whisper
import io
import tempfile
import ffmpeg

# חיבור ל-Google Drive עם Secrets של Streamlit
@st.cache_resource
def connect_to_drive():
    creds_info = json.loads(st.secrets["google_credentials"]["credentials_json"])
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

service = connect_to_drive()

# טעינת מודל Whisper
@st.cache_resource
def load_whisper_model():
    return whisper.load_model("base")

model = load_whisper_model()

# פונקציה לרשימת תיקיות ב-Google Drive
def list_drive_folders():
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = results.get('files', [])
    return folders

# ממשק Streamlit
st.title('🎬 Auto Video Transcriber')
st.write("בחר את התיקייה או התיקיות לסריקה:")

folders = list_drive_folders()
folder_options = {folder['name']: folder['id'] for folder in folders}
selected_folders = st.multiselect("בחר תיקיות", list(folder_options.keys()))

if st.button("התחל סריקה ותמלול"):
    for folder_name in selected_folders:
        folder_id = folder_options[folder_name]
        st.write(f"סריקה של תיקייה: {folder_name}")

        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'video/'",
            fields="files(id, name)"
        ).execute()
        videos = results.get('files', [])

        if not videos:
            st.write("לא נמצאו סרטונים בתיקייה זו.")
        else:
            for video in videos:
                st.write(f"תמלול של {video['name']} בתהליך...")

                request = service.files().get_media(fileId=video['id'])
                video_file = io.BytesIO()
                downloader = MediaIoBaseDownload(video_file, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    st.write(f"התקדמות הורדה: {int(status.progress() * 100)}%")

                video_file.seek(0)

                # שמירת הקובץ באופן זמני לתמלול
                with tempfile.NamedTemporaryFile(suffix='.mp4') as temp_video:
                    temp_video.write(video_file.read())
                    temp_video.flush()

                    # תמלול עם whisper
                    result = model.transcribe(temp_video.name, language="he")
                    transcript_content = result["text"]

                # יצירת קובץ עם התמלול
                transcript_file = io.BytesIO(transcript_content.encode("utf-8"))

                # העלאת התמלול ל-Google Drive
                transcript_file.seek(0)
                media = MediaIoBaseUpload(transcript_file, mimetype='text/plain', resumable=True)
                file_metadata = {'name': f"{video['name']}_transcript.txt", 'parents': [folder_id]}

                service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                st.write(f"קובץ תמלול נוצר בהצלחה: {video['name']}_transcript.txt")
