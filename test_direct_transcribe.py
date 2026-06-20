import sys
import os

sys.path.insert(0, os.path.abspath("backend"))

from app.services.audio_processor import get_whisper_model

try:
    print("Directly transcribing backend/uploads/fcafbe33-725d-4156-a278-3ca68ad5c2b8.webm using Whisper...")
    model = get_whisper_model()
    segments, info = model.transcribe(
        "backend/uploads/fcafbe33-725d-4156-a278-3ca68ad5c2b8.webm",
        language="en",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=True,
        word_timestamps=True,
        vad_filter=False
    )
    print("=== SEGMENTS ===")
    for segment in segments:
        print(segment.text)
except Exception as e:
    print(f"Error: {e}")
