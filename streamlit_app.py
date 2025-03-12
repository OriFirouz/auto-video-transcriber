import streamlit as st
import json
import openai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import tempfile

# הגדרת OpenAI API
openai.api_key = st.secrets["openai"]["api_key"]

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

# רשימת תיקיות בדרייב
def list_drive_folders():
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = results.get('files', [])
    return folders

# ממשק המשתמש
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

                # הורדת הסרטון
                request = service.files().get_media(fileId=video['id'])
                video_file = io.BytesIO()
                downloader = MediaIoBaseDownload(video_file, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    st.write(f"התקדמות הורדה: {int(status.progress() * 100)}%")

                video_file.seek(0)

                # שמירה זמנית של קובץ להעלאה ל-OpenAI Whisper API
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as temp_video:
                    temp_video.write(video_file.read())
                    temp_video.flush()

                    # שליחת הסרטון לתמלול דרך Whisper API
                    with open(temp_video.name, "rb") as audio_file:
                        transcript = openai.Audio.transcribe(
                            "whisper-1",
                            audio_file,
                            language="he"
                        )

                    transcript_content = transcript["text"]

                # יצירת קובץ התמלול והעלאה ל-Drive
                transcript_file = io.BytesIO(transcript_content.encode("utf-8"))
                transcript_file.seek(0)
                media = MediaIoBaseUpload(transcript_file, mimetype='text/plain', resumable=True)

                file_metadata = {'name': f"{video['name']}_transcript.txt", 'parents': [folder_id]}

                service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                st.write(f"קובץ תמלול נוצר בהצלחה: {video['name']}_transcript.txt")
