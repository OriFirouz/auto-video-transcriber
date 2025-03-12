import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.oauth2 import service_account

st.title('🎬 Auto Video Transcriber')

st.write("Welcome! Connect your Google Drive.")

# UI לחיבור Google Drive באמצעות API
st.write("## Step 1: Google Drive Connection")

uploaded_file = st.file_uploader("Upload your Google Drive credentials JSON file", type=["json"])

if uploaded_file is not None:
    with open("credentials.json", "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success("Credentials file uploaded successfully!")
    st.write("Next steps will be implemented soon...")

else:
    st.info("Please upload your Google Drive credentials JSON file to proceed.")

