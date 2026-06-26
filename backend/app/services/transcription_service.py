"""
TranscriptionService — Groq Whisper (whisper-large-v3) exclusive implementation.

This is the ONLY transcription engine used in the application.
Gemini is NOT used anywhere in this pipeline.

Architecture:
  audio file (WAV, 16kHz mono)
       │
       ▼
  Groq Audio Transcriptions API
  model: whisper-large-v3
  response_format: verbose_json
       │
       ▼
  raw transcript text + metadata

Retry policy: up to 3 attempts with exponential backoff.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, List

from app.config import settings

logger = logging.getLogger("jam_analyzer")

# ── Constants ─────────────────────────────────────────────────────────────────

GROQ_WHISPER_MODEL = "whisper-large-v3"
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SEC = 1.5       # doubles each attempt: 1.5s → 3s → 6s
GROQ_STT_TIMEOUT_SEC = 120.0     # generous for long recordings


# ── TranscriptionService ──────────────────────────────────────────────────────

class TranscriptionService:
    """
    Centralized Speech-to-Text service using Groq Whisper exclusively.

    Provider: Groq (whisper-large-v3)
    No other providers are used.

    Usage:
        service = TranscriptionService()
        result = service.transcribe(audio_path)
        text = result["text"]
    """

    def __init__(self) -> None:
        self._verify_api_key()

    def _verify_api_key(self) -> None:
        """Raise at construction time if GROQ_API_KEY is missing."""
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "[TranscriptionService] GROQ_API_KEY is not configured. "
                "Set it in your .env file."
            )

    # ── Core transcription ────────────────────────────────────────────────────

    def _call_groq_whisper(self, audio_path: str) -> Dict[str, Any]:
        """
        Single attempt to transcribe an audio file using the Groq SDK.

        Returns a dict with:
          text       (str)             — verbatim transcript
          language   (str)             — detected/forced language code
          duration   (float | None)   — audio duration in seconds
          segments   (list | None)    — word/sentence segments with timestamps
          confidence (float | None)   — average confidence or None if unavailable

        Raises on any API or SDK error (caller handles retry).
        """
        from groq import Groq

        audio_size = os.path.getsize(audio_path)
        logger.info(
            f"[GROQ_STT] Opening audio: {os.path.basename(audio_path)} "
            f"({audio_size:,} bytes)"
        )

        client = Groq(api_key=settings.GROQ_API_KEY)

        t_start = time.monotonic()

        with open(audio_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), audio_file, "audio/wav"),
                model=GROQ_WHISPER_MODEL,
                language="en",
                response_format="verbose_json",
                temperature=0.0,
            )

        latency = time.monotonic() - t_start
        logger.info(f"[GROQ_STT] API call completed in {latency:.2f}s")

        # ── Parse verbose_json response ──
        # Groq returns an object with .text, .language, .duration, .segments
        text = ""
        language = "en"
        duration: Optional[float] = None
        segments: Optional[List[Dict[str, Any]]] = None
        confidence: Optional[float] = None

        # Handle both dict and object responses
        if hasattr(response, "text"):
            text = (response.text or "").strip()
            language = getattr(response, "language", "en") or "en"
            duration = getattr(response, "duration", None)
            segments_raw = getattr(response, "segments", None)
        elif isinstance(response, dict):
            text = (response.get("text", "") or "").strip()
            language = response.get("language", "en") or "en"
            duration = response.get("duration")
            segments_raw = response.get("segments")
        else:
            text = str(response).strip()
            segments_raw = None

        # Parse segments if present
        if segments_raw:
            try:
                if isinstance(segments_raw, list):
                    segments = []
                    confidences = []
                    for seg in segments_raw:
                        if isinstance(seg, dict):
                            seg_data = {
                                "id": seg.get("id"),
                                "start": seg.get("start"),
                                "end": seg.get("end"),
                                "text": seg.get("text", "").strip(),
                            }
                            if "avg_logprob" in seg:
                                # Convert log-probability to approximate confidence
                                import math
                                conf = round(min(1.0, math.exp(seg["avg_logprob"])), 4)
                                seg_data["confidence"] = conf
                                confidences.append(conf)
                            elif "confidence" in seg:
                                seg_data["confidence"] = seg["confidence"]
                                confidences.append(seg["confidence"])
                            segments.append(seg_data)
                    if confidences:
                        confidence = round(sum(confidences) / len(confidences), 4)
            except Exception as seg_err:
                logger.warning(f"[GROQ_STT] Could not parse segments: {seg_err}")
                segments = None

        logger.info(
            f"[GROQ_STT] Transcript: {len(text)} chars | "
            f"language={language} | duration={duration}s | "
            f"segments={len(segments) if segments else 0} | "
            f"confidence={confidence} | latency={latency:.2f}s"
        )

        return {
            "text": text,
            "language": language,
            "duration": duration,
            "segments": segments,
            "confidence": confidence,
            "latency_sec": round(latency, 3),
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe an audio file and return the raw transcript text string.

        This is the primary entry point used by audio_processor.process_audio().
        Compatible with the existing pipeline — returns a plain str.

        Retries up to MAX_RETRY_ATTEMPTS times with exponential backoff.
        Raises RuntimeError if all attempts fail.
        """
        return self.transcribe_full(audio_path)["text"]

    def transcribe_full(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe an audio file and return the full structured result.

        Returns:
          {
            "text":       str,
            "language":   str,
            "duration":   float | None,
            "confidence": float | None,
            "segments":   list | None,
            "latency_sec": float,
          }

        Retries up to MAX_RETRY_ATTEMPTS times with exponential backoff.
        Raises RuntimeError if all attempts fail.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(
                f"[TranscriptionService] Audio file not found: {audio_path}"
            )

        audio_size = os.path.getsize(audio_path)
        logger.info(
            f"[GROQ_STT] Starting transcription | "
            f"file={os.path.basename(audio_path)} | "
            f"size={audio_size:,} bytes | "
            f"model={GROQ_WHISPER_MODEL}"
        )

        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                logger.info(
                    f"[GROQ_STT] Attempt {attempt}/{MAX_RETRY_ATTEMPTS}..."
                )
                result = self._call_groq_whisper(audio_path)

                text = result.get("text", "")
                if not text.strip():
                    logger.warning(
                        "[GROQ_STT] Empty transcript returned by Groq — "
                        "likely silent audio."
                    )
                    # Don't retry on empty — audio is genuinely silent
                    raise ValueError(
                        "Groq Whisper returned an empty transcript. "
                        "The audio may be silent or too short."
                    )

                logger.info(
                    f"[GROQ_STT] SUCCESS on attempt {attempt}. "
                    f"Transcript preview: '{text[:80]}'"
                )
                return result

            except ValueError as ve:
                # Empty transcript — no point retrying
                raise RuntimeError(str(ve)) from ve

            except Exception as e:
                last_error = e
                logger.warning(
                    f"[GROQ_STT] Attempt {attempt} FAILED: "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < MAX_RETRY_ATTEMPTS:
                    delay = RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
                    logger.info(
                        f"[GROQ_STT] Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

        # All attempts exhausted
        logger.error(
            f"[GROQ_STT] All {MAX_RETRY_ATTEMPTS} attempts failed. "
            f"Last error: {last_error}"
        )
        raise RuntimeError(
            f"Groq Whisper transcription failed after {MAX_RETRY_ATTEMPTS} attempts. "
            f"Last error: {last_error}"
        ) from last_error
