import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io

# פונקציית התחברות ל-Google Drive
@st.cache_resource
def connect_to_drive():
    creds_dict = {
        # הכנס כאן את תוכן קובץ ה-JSON שיצרת ב-Google Cloud
    }
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/drive"])
    return build('drive', 'v3', credentials=creds)

service = connect_to_drive()

# פונקציה לקבלת תיקיות בדרייב
def list_drive_folders():
    results = service.files().list(q="mimeType='application/vnd.google-apps.folder'",
                                   fields="files(id, name)").execute()
    folders = results.get('files', [])
    return folders

# ממשק בחירת תיקיות
st.title('🎬 Auto Video Transcriber')
st.write("בחר את התיקייה או התיקיות לסריקה:")

folders = list_drive_folders()
folder_options = {folder['name']: folder['id'] for folder in folders}

selected_folders = st.multiselect("בחר תיקיות", list(folder_options.keys()))

if st.button("התחל סריקה ותמלול"):
    for folder_name in selected_folders:
        folder_id = folder_options[folder_name]
        st.write(f"סריקה של תיקייה: {folder_name}")

        results = service.files().list(q=f"'{folder_id}' in parents and mimeType contains 'video/'",
                                       fields="files(id, name)").execute()
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
                while done is False:
                    status, done = downloader.next_chunk()
                    st.write(f"התקדמות הורדה: {int(status.progress() * 100)}%")

                # יצירת קובץ טקסט פשוט כדוגמה לתמלול (צריך להחליף ב-AI אמיתי)
                transcript_content = f"תמלול של הסרטון {video['name']}"
                transcript_file = io.BytesIO(transcript_content.encode())

                file_metadata = {'name': f"{video['name']}.txt", 'parents': [folder_id]}
                media = MediaIoBaseDownload(transcript_file, mimetype='text/plain')

                service.files().create(body=file_metadata,
                                       media_body=MediaFileUpload(f"{video['name']}.txt", mimetype='text/plain')).execute()
                st.write(f"קובץ תמלול נוצר: {video['name']}.txt")
