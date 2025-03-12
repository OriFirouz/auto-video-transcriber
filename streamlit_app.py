import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io

# התחברות ל-Google Drive דרך secrets של Streamlit
@st.cache_resource
def connect_to_drive():
    creds_info = json.loads(st.secrets["google_credentials"]["credentials_json"])
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

service = connect_to_drive()

# פונקציה לקבלת רשימת תיקיות ב-Drive
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

                request = service.files().get_media(fileId=video['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    st.write(f"התקדמות הורדה: {int(status.progress() * 100)}%")

                # דוגמה פשוטה של יצירת תוכן תמלול
                transcript_content = f"תמלול של הסרטון {video['name']}"
                transcript_file = io.BytesIO(transcript_content.encode())
                
                file_metadata = {'name': f"{video['name']}.txt", 'parents': [folder_id]}
                media = MediaIoBaseUpload(transcript_file, mimetype='text/plain', resumable=True)

                service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                st.write(f"קובץ תמלול נוצר: {video['name']}.txt")
