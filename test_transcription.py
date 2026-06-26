import sys
import os

sys.path.insert(0, os.path.abspath("backend"))

from app.services.audio_processor import process_audio

try:
    print("Processing backend/uploads/doc_sess_47280024-ba5b-443a-bc58-e8d82cbfc8ab.webm...")
    metrics = process_audio("backend/uploads/doc_sess_47280024-ba5b-443a-bc58-e8d82cbfc8ab.webm")
    print("=== RAW TRANSCRIPT ===")
    print(metrics.get("raw_transcript"))
    print("=== TRANSCRIPT ===")
    print(metrics.get("transcript"))
except Exception as e:
    print(f"Error: {e}")
