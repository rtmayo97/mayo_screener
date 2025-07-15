import os
import streamlit as st
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from openai import OpenAI

# Load from Streamlit secrets if deployed, else from .env
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    ENCRYPTION_KEY = st.secrets["ENCRYPTION_KEY"]
except:
    load_dotenv("API_Keys.env")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# Initialize clients
fernet = Fernet(ENCRYPTION_KEY.encode())
client = OpenAI(api_key=OPENAI_API_KEY)

# Set data directory
DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)
