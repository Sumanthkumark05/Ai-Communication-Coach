import requests
import os
import sys

# Add backend app directory to sys.path to import extract_audio
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))
from services.audio_processor import extract_audio

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    # Try reading from .env
    with open(".env") as f:
        for line in f:
            if line.startswith("GROQ_API_KEY="):
                api_key = line.split("=")[1].strip()

if not api_key:
    print("GROQ_API_KEY not found!")
    sys.exit(1)

video_path = "uploads/debate_aace9c1d-a9e5-437d-bd54-4f9dcdcb3391_0.webm"
if not os.path.exists(video_path):
    print("Test video file not found!")
    sys.exit(1)

print("Extracting audio from video...")
audio_path = extract_audio(video_path)
print(f"Extracted audio to {audio_path}, size={os.path.getsize(audio_path)} bytes")

headers = {
    "Authorization": f"Bearer {api_key}"
}

files = {
    "file": (os.path.basename(audio_path), open(audio_path, "rb"), "audio/wav")
}

data = {
    "model": "whisper-large-v3",
    "temperature": "0.0",
    "response_format": "json"
}

print("Sending transcription request to Groq API...")
res = requests.post(
    "https://api.groq.com/openai/v1/audio/transcriptions",
    headers=headers,
    files=files,
    data=data
)

print("Status Code:", res.status_code)
print("Response text:", res.text)

# Cleanup
if os.path.exists(audio_path):
    os.remove(audio_path)
