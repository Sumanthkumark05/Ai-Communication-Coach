import sys
import os

sys.path.insert(0, os.path.abspath("backend"))

from app.services.audio_processor import process_audio

try:
    print("Processing backend/dummy_viva.wav...")
    metrics = process_audio("backend/dummy_viva.wav")
    print("=== RAW TRANSCRIPT ===")
    print(metrics.get("raw_transcript"))
    print("=== TRANSCRIPT ===")
    print(metrics.get("transcript"))
except Exception as e:
    print(f"Error: {e}")
