import os
import subprocess
import logging
import re
import math
from typing import Dict, Any, List
import scipy.io.wavfile as wavfile
import numpy as np
import noisereduce as nr
import webrtcvad
from app.config import settings

logger = logging.getLogger("jam_analyzer")

class AudioExtractionError(Exception):
    pass

class GroqAPIError(Exception):
    pass

class TranscriptGenerationError(Exception):
    pass

# Mock get_whisper_model to maintain compatibility with main.py startup events
def get_whisper_model():
    logger.info("[Startup] Whisper warmup mocked (Groq Whisper API is active).")
    return None

def run_webrtc_vad(audio_path: str, aggressiveness: int = 2) -> Dict[str, Any]:
    """
    Runs WebRTC VAD on the audio file (must be 16kHz 16-bit mono PCM).
    Returns speech_duration, silence_duration, and total_duration.
    """
    try:
        vad = webrtcvad.Vad(aggressiveness)
        sample_rate, data = wavfile.read(audio_path)
        
        # Ensure data is 16-bit PCM format
        if data.dtype != np.int16:
            if data.dtype == np.float32 or data.dtype == np.float64:
                data = (data * 32767).astype(np.int16)
            else:
                data = data.astype(np.int16)
                
        raw_bytes = data.tobytes()
        
        # 30 ms frame at 16kHz = 480 samples = 960 bytes
        frame_duration_ms = 30
        frame_size = int(sample_rate * frame_duration_ms / 1000)
        frame_bytes_len = frame_size * 2
        
        total_frames = len(raw_bytes) // frame_bytes_len
        speech_frames = 0
        silence_frames = 0
        
        for i in range(total_frames):
            frame = raw_bytes[i*frame_bytes_len : (i+1)*frame_bytes_len]
            # Avoid checking short trailing frame
            if len(frame) == frame_bytes_len:
                try:
                    is_speech = vad.is_speech(frame, sample_rate)
                    if is_speech:
                        speech_frames += 1
                    else:
                        silence_frames += 1
                except Exception:
                    pass
                    
        speech_duration = speech_frames * (frame_duration_ms / 1000.0)
        silence_duration = silence_frames * (frame_duration_ms / 1000.0)
        
        logger.info(f"WebRTC VAD: speech={speech_duration:.2f}s, silence={silence_duration:.2f}s")
        return {
            "speech_duration": round(speech_duration, 2),
            "silence_duration": round(silence_duration, 2),
            "total_duration": round(speech_duration + silence_duration, 2)
        }
    except Exception as e:
        logger.warning(f"VAD failed: {e}. Using fallback values.")
        # Fallback to simple amplitude-based estimation if VAD crashes
        return {
            "speech_duration": 0.0,
            "silence_duration": 0.0,
            "total_duration": 0.0
        }

def compute_snr_db(data: np.ndarray) -> float:
    """
    Estimates Signal-to-Noise Ratio in decibels using the top 10% loudest frames
    as the signal estimate and the bottom 10% as the noise floor estimate.
    Returns a float in dB. Higher = cleaner audio.
    """
    try:
        abs_data = np.abs(data.astype(np.float64))
        if abs_data.max() == 0:
            return 0.0
        frame_size = max(1, len(abs_data) // 100)
        frame_energies = [np.mean(abs_data[i:i+frame_size]) for i in range(0, len(abs_data), frame_size)]
        frame_energies.sort()
        noise_floor = np.mean(frame_energies[:max(1, len(frame_energies) // 10)]) + 1e-10
        signal_level = np.mean(frame_energies[max(0, len(frame_energies) - len(frame_energies) // 10):]) + 1e-10
        snr = 20 * np.log10(signal_level / noise_floor)
        return float(snr)
    except Exception:
        return 99.0  # assume clean on error

def extract_audio(video_path: str) -> str:
    """
    Extracts the audio channel from a video file into a 16kHz mono WAV file using FFmpeg.
    Applies noisereduce ONLY when SNR is below 25 dB to avoid distorting clean speech.
    """
    if not os.path.exists(video_path):
        logger.error(f"[Audio Extraction] Video file does not exist at path: {video_path}")
        raise AudioExtractionError("Video file does not exist on server.")
    
    video_size = os.path.getsize(video_path)
    logger.info(f"[Audio Extraction] Video file exists. Size: {video_size} bytes.")
    if video_size == 0:
        logger.error("[Audio Extraction] Uploaded video file is empty (0 bytes).")
        raise AudioExtractionError("Uploaded video file is empty.")

    audio_path = os.path.splitext(video_path)[0] + ".wav"
    
    # Overwrite if exists to support new recordings in the same session
    if os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except Exception as e:
            logger.warning(f"Could not remove old audio file: {e}")

    logger.info(f"Audio extraction started from {video_path} to {audio_path}...")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-filter:a", "dynaudnorm",
            audio_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg extraction failed: {result.stderr}")
            raise Exception(f"FFmpeg error: {result.stderr}")
            
        if not os.path.exists(audio_path):
            logger.error(f"[Audio Extraction] Extracted audio file not found at path: {audio_path}")
            raise AudioExtractionError("FFmpeg failed to create audio file.")

        audio_size = os.path.getsize(audio_path)
        logger.info(f"[Audio Extraction] Extracted audio file size: {audio_size} bytes.")
        if audio_size == 0:
            logger.error("[Audio Extraction] Extracted audio file is empty (0 bytes).")
            raise AudioExtractionError("Extracted audio file is empty.")

        rate, data = wavfile.read(audio_path)
        
        if data.size == 0:
            raise ValueError("Extracted audio data is empty (0 samples).")
            
        # Conditional noise reduction: only apply when SNR is low (< 25 dB).
        # Applying aggressive noise reduction on already-clean speech degrades Whisper accuracy
        # by introducing spectral artefacts that the model mistakes for mispronounced words.
        try:
            snr = compute_snr_db(data)
            logger.info(f"Audio SNR estimated at {snr:.1f} dB.")
            if snr < 25.0:
                logger.info("SNR below 25 dB — applying spectral noise reduction...")
                reduced_data = nr.reduce_noise(y=data, sr=rate, prop_decrease=0.75)
                wavfile.write(audio_path, rate, reduced_data.astype(data.dtype))
                logger.info("Noise reduction applied.")
            else:
                logger.info("SNR is acceptable — skipping noise reduction to preserve speech quality.")
        except Exception as e:
            logger.warning(f"Noise reduction step failed: {e}. Using original audio.")
            
        logger.info("Audio Extracted")
        logger.info("STEP 4:\nAudio extraction completed")
        logger.info("Audio extraction completed.")
        return audio_path
    except FileNotFoundError as e:
        logger.error("ffmpeg executable not found.")
        raise AudioExtractionError("Audio extraction failed") from e
    except Exception as e:
        logger.error(f"Audio extraction failed: {e}")
        raise AudioExtractionError("Audio extraction failed") from e

def clean_word(word: str) -> str:
    """
    Cleans punctuation and converts word to lowercase.
    """
    return re.sub(r"[^\w\s']", "", word).strip().lower()

def count_filler_words(transcript: str) -> Dict[str, int]:
    """
    Counts filler words in the transcript using case-insensitive regex matching.
    """
    fillers = {
        "um": 0, "uh": 0, "ah": 0, "ahh": 0, "uhh": 0, "erm": 0, "like": 0,
        "you know": 0, "actually": 0, "basically": 0,
        "literally": 0, "sort of": 0, "kind of": 0
    }
    if not transcript:
        return fillers
        
    clean_text = re.sub(r"[^\w\s']", " ", transcript).lower()
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    text_with_spaces = f" {clean_text} "
    
    patterns = {
        "um": r"\bu+m+\b",
        "uh": r"\bu+h\b",
        "ah": r"\ba+h\b",
        "ahh": r"\ba+hh+\b",
        "uhh": r"\bu+hh+\b",
        "erm": r"\be+r+m+\b",
        "like": r"\blike\b",
        "you know": r"\byou\s+know\b",
        "actually": r"\bactually\b",
        "basically": r"\bbasically\b",
        "literally": r"\bliterally\b",
        "sort of": r"\bsort\s+of\b",
        "kind of": r"\bkind\s+of\b"
    }
    
    for word, pattern in patterns.items():
        matches = re.findall(pattern, text_with_spaces)
        fillers[word] = len(matches)
            
    return fillers

def clean_fillers_from_transcript(raw_transcript: str) -> str:
    """
    Removes filler words and their repeat variations from the transcript.
    """
    if not raw_transcript:
        return ""
        
    patterns = [
        r"\bu+m+\b", r"\bu+h+\b", r"\be+r+\b", r"\ba+h+\b",
        r"\blike\b", r"\byou\s+know\b", r"\bactually\b",
        r"\bbasically\b", r"\bliterally\b", r"\bkind\s+of\b",
        r"\bsort\s+of\b"
    ]
    
    cleaned = raw_transcript
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:\s*,\s*)+", ", ", cleaned)
    cleaned = re.sub(r"(?:\s*\.\s*)+", ". ", cleaned)
    cleaned = re.sub(r",\s*\.", ".", cleaned)
    cleaned = re.sub(r"^[.,!?;:]\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def analyze_speech_metrics(words: List[Dict[str, Any]], duration: float, vad_results: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Calculates detailed speech metrics from timestamped words and VAD results.
    """
    if vad_results is None:
        vad_results = {"speech_duration": duration, "silence_duration": 0.0}
    total_words_count = len(words)
    speech_dur = vad_results.get("speech_duration", duration)
    silence_dur = vad_results.get("silence_duration", 0.0)
    
    if speech_dur <= 0:
        speech_dur = duration if duration > 0 else 1.0

    if total_words_count == 0:
        return {
            "raw_transcript": "",
            "transcript": "",
            "words_per_minute": 0,
            "speech_duration": speech_dur,
            "silence_duration": silence_dur,
            "filler_words": {
                "um": 0, "uh": 0, "ah": 0, "ahh": 0, "uhh": 0, "erm": 0, "like": 0, "you know": 0,
                "actually": 0, "basically": 0, "literally": 0, "sort of": 0, "kind of": 0
            },
            "pause_count": 0,
            "pause_duration": round(silence_dur, 2),
            "vocabulary_score": 0,
            "speaking_pace_score": 0,
            "filler_occurrences": []
        }

    transcript_parts = []
    clean_words = []
    pauses_count = 0
    total_pause_duration = 0.0
    prev_end = 0.0
    
    i = 0
    while i < len(words):
        word_data = words[i]
        raw_word = word_data["word"]
        start = word_data["start"]
        end = word_data["end"]
        
        transcript_parts.append(raw_word)
        cleaned = clean_word(raw_word)
        
        if cleaned:
            clean_words.append(cleaned)
            
            if cleaned == "you" and i + 1 < len(words):
                next_cleaned = clean_word(words[i+1]["word"])
                if next_cleaned == "know":
                    clean_words.append(next_cleaned)
                    transcript_parts.append(words[i+1]["word"])
                    end = words[i+1]["end"]
                    i += 1
            
            if prev_end > 0:
                gap = start - prev_end
                if gap > 1.5:
                    pauses_count += 1
                    total_pause_duration += gap
            
            prev_end = end
        i += 1

    reconstructed_tokens: List[str] = []
    for token in transcript_parts:
        if not reconstructed_tokens:
            reconstructed_tokens.append(token)
        else:
            prev = reconstructed_tokens[-1]
            need_space = True
            if prev.endswith(" ") or token.startswith(" "):
                need_space = False
            elif token in [".", ",", "!", "?", ";", ":"]:
                need_space = False
            
            if need_space:
                reconstructed_tokens.append(" " + token)
            else:
                reconstructed_tokens.append(token)
                
    raw_transcript = "".join(reconstructed_tokens).strip()
    raw_transcript = re.sub(r"\s+", " ", raw_transcript)
    
    filler_counts = count_filler_words(raw_transcript)
    
    filler_occurrences = []
    idx = 0
    while idx < len(words):
        w_data = words[idx]
        raw_w = w_data["word"]
        clean_w = clean_word(raw_w)
        
        is_multi = False
        if idx + 1 < len(words):
            w_data_next = words[idx+1]
            raw_w_next = w_data_next["word"]
            clean_w_next = clean_word(raw_w_next)
            
            phrase = f"{clean_w} {clean_w_next}"
            if phrase in ["you know", "kind of", "sort of"]:
                filler_occurrences.append({
                    "filler": phrase,
                    "start": w_data["start"],
                    "end": w_data_next["end"]
                })
                idx += 2
                is_multi = True
                continue
        if not is_multi:
            for filler_key, pattern in [
                ("um", r"^u+m+$"), ("uh", r"^u+h$"),
                ("ah", r"^a+h$"), ("ahh", r"^a+hh+$"), ("uhh", r"^u+hh+$"),
                ("erm", r"^e+r+m+$"), ("like", r"^like$"), ("actually", r"^actually$"),
                ("basically", r"^basically$"), ("literally", r"^literally$")
            ]:
                if re.match(pattern, clean_w, re.IGNORECASE):
                    filler_occurrences.append({
                        "filler": filler_key,
                        "start": w_data["start"],
                        "end": w_data["end"]
                    })
                    break
            idx += 1
 
    # Calculate WPM based on exact speech duration
    wpm = int((total_words_count / speech_dur) * 60)
    
    # Target pace 135 WPM
    target_pace = 135
    speaking_pace_score = max(30, int(100 - abs(wpm - target_pace) * 1.5))
    if wpm == 0:
        speaking_pace_score = 0
        
    unique_words_count = len(set(clean_words))
    ttr = (unique_words_count / len(clean_words)) * 100 if clean_words else 0
    vocabulary_score = min(100, max(10, int(ttr * 1.6)))
    
    return {
        "raw_transcript": raw_transcript,
        "transcript": raw_transcript,
        "words_per_minute": wpm,
        "speech_duration": round(speech_dur, 2),
        "silence_duration": round(silence_dur, 2),
        "filler_words": filler_counts,
        "pause_count": pauses_count,
        "pause_duration": round(total_pause_duration, 2),
        "vocabulary_score": vocabulary_score,
        "speaking_pace_score": speaking_pace_score,
        "filler_occurrences": filler_occurrences
    }

def validate_transcript_quality(raw_transcript: str, duration: float, segments_list: List[Any]):
    """
    Performs quality and consistency checks on the generated transcript.
    Logs warning messages when issues like empty transcripts, very short transcripts,
    length mismatches, or missing segments are detected.
    """
    cleaned_t = (raw_transcript or "").strip()
    
    # 1. Empty transcript check
    if not cleaned_t:
        logger.warning("[Transcript Validation] WARNING: Transcript is completely empty.")
        return
        
    # 2. Very short transcript check
    word_count = len(cleaned_t.split())
    if word_count < 3:
        logger.warning(f"[Transcript Validation] WARNING: Transcript is extremely short ({word_count} words): '{cleaned_t}'")
        
    # 3. Transcript length mismatch check
    if duration > 10.0 and word_count < 4:
        logger.warning(f"[Transcript Validation] WARNING: Audio duration is {duration:.2f}s but transcript only contains {word_count} words.")
        
    # 4. Missing segments check
    if segments_list:
        segment_durations_sum = sum((seg.end - seg.start) for seg in segments_list)
        if duration > 5.0 and segment_durations_sum < (duration * 0.1):
            logger.warning(f"[Transcript Validation] WARNING: Missing segments. Combined segment duration ({segment_durations_sum:.2f}s) is less than 10% of total audio duration ({duration:.2f}s).")
        
        # Check for gap between consecutive segments
        prev_end = 0.0
        for idx, seg in enumerate(segments_list):
            if idx > 0:
                gap = seg.start - prev_end
                if gap > 15.0:
                    logger.warning(f"[Transcript Validation] WARNING: Detected large silence gap of {gap:.2f}s between segment {idx-1} and segment {idx}.")
            prev_end = seg.end
    else:
        if duration > 2.0:
            logger.warning(f"[Transcript Validation] WARNING: No speech segments were returned by Whisper for audio duration {duration:.2f}s.")

def process_audio(video_path: str, db = None, job_id = None, job_model = None) -> Dict[str, Any]:
    """
    Extracts audio, applies VAD and noise reduction, then transcribes using Groq Whisper.

    Transcription engine: Groq Whisper (whisper-large-v3) — exclusive, no fallback needed.
    Retry policy: up to 3 automatic retries with exponential backoff (handled by TranscriptionService).
    """
    import time
    uploaded_filename = os.path.basename(video_path)
    logger.info(f"--- Audio Processing (Groq Whisper: whisper-large-v3) for file: {uploaded_filename} ---")
    audio_path = None
    try:
        audio_path = extract_audio(video_path)
        
        # 1. Run WebRTC VAD
        vad_results = run_webrtc_vad(audio_path, aggressiveness=2)
        
        # 2. Validate audio file exists and has content
        if not os.path.exists(audio_path):
            raise AudioExtractionError(f"Audio file does not exist: {audio_path}")

        audio_size = os.path.getsize(audio_path)
        logger.info(f"[STT] Audio file verification: path={audio_path}, size={audio_size} bytes")
        if audio_size == 0:
            raise AudioExtractionError("Audio file is empty (0 bytes).")

        # 3. Transcribe using Groq Whisper (whisper-large-v3) exclusively
        from app.services.transcription_service import TranscriptionService
        try:
            logger.info("STEP 5:\nTranscript generation started")
            logger.info("[STEP 5]\nGroq Whisper STT\n- model: whisper-large-v3 | retries: up to 3 | format: verbose_json")

            transcription_service = TranscriptionService()
            raw_transcript = transcription_service.transcribe(audio_path)
            logger.info("[GROQ_STT_COMPLETE] Transcription received successfully.")
        except Exception as e:
            logger.error(f"[STT_FAILURE] Unexpected error during transcription: {type(e).__name__}: {e}")
            raise RuntimeError(f"Transcription failed: {str(e)}") from e

        logger.info(f"[STEP 6]\nTranscription response\n- response received: success\n- response size: {len(raw_transcript)} characters")
        logger.info(f"[STEP 4]\nTranscription\n- transcript length: {len(raw_transcript)} characters")
        logger.info(f"[STT] Raw transcript length: {len(raw_transcript)} chars")

        if not raw_transcript.strip():
            logger.warning("[STT_FAILURE] Transcript is empty after successful API call — likely silent audio.")
            raise TranscriptGenerationError("Transcript generation failed")

        logger.info(f"[STT_RESPONSE_PARSED] transcript_length={len(raw_transcript)} preview='{raw_transcript[:80].strip()}'")
        logger.info("STEP 6:\nTranscript generated")
        
        # 3. Calculate metrics locally
        rate, wav_data = wavfile.read(audio_path)
        duration = len(wav_data) / rate
        avg_volume = float(np.mean(np.abs(wav_data)))
        
        # Override VAD durations with actual audio length if VAD returned zero but speech was transcribed
        if len(raw_transcript.strip()) > 0 and vad_results["speech_duration"] == 0:
            vad_results["speech_duration"] = round(duration, 2)
            vad_results["silence_duration"] = 0.0
            vad_results["total_duration"] = round(duration, 2)
            
        speech_dur = vad_results.get("speech_duration", duration)
        silence_dur = vad_results.get("silence_duration", 0.0)
        if speech_dur <= 0:
            speech_dur = duration if duration > 0 else 1.0
            
        clean_words_list = [clean_word(w) for w in re.split(r'\s+', raw_transcript) if clean_word(w)]
        word_count = len(clean_words_list)
        
        # Calculate WPM based on exact speech duration
        wpm = int((word_count / speech_dur) * 60) if speech_dur > 0 else 0
        target_pace = 135
        speaking_pace_score = max(30, int(100 - abs(wpm - target_pace) * 1.5)) if wpm > 0 else 0
        
        unique_words_count = len(set(clean_words_list))
        ttr = (unique_words_count / len(clean_words_list)) * 100 if clean_words_list else 0
        vocabulary_score = min(100, max(10, int(ttr * 1.6)))
        
        filler_counts = count_filler_words(raw_transcript)
        
        # Estimate pause metrics based on silence duration from VAD
        pause_duration = round(silence_dur, 2)
        pauses_count = int(silence_dur / 2.0)
        avg_confidence = 98  # high default confidence for verified transcription
        
        metrics = {
            "raw_transcript": raw_transcript,
            "transcript": raw_transcript,
            "words_per_minute": wpm,
            "speech_duration": round(speech_dur, 2),
            "silence_duration": round(silence_dur, 2),
            "filler_words": filler_counts,
            "pause_count": pauses_count,
            "pause_duration": pause_duration,
            "vocabulary_score": vocabulary_score,
            "speaking_pace_score": speaking_pace_score,
            "filler_occurrences": [],
            "duration": round(duration, 2),
            "transcript_confidence": int(avg_confidence),
            "average_volume": round(avg_volume, 2),
            "vad_speech_duration": vad_results["speech_duration"],
            "vad_silence_duration": vad_results["silence_duration"],
            "pauses_detected": [],
            "word_timings": []
        }
        
        logger.info("Transcript Generated")
        logger.info(f"Transcript Length: {len(metrics['raw_transcript'])}")
        logger.info(f"Audio metrics: speech_dur={metrics['speech_duration']}s, WPM={metrics['words_per_minute']}, Vol={avg_volume:.1f}")
        return metrics
        
    except Exception as e:
        logger.error(f"Error processing speech: {e}")
        import traceback
        print("FULL TRACEBACK:")
        traceback.print_exc()
        raise e
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass
