import os
import time
import random
import logging
import threading
import shutil
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session as DBSession
from jose import jwt

from app.database import get_db
from app.models import User, Session, Transcript, CommunicationDNA, VoiceMetrics, FaceMetrics, GrowthMetrics, Report, DocumentSession, VivaSession, SessionRecording
from app.schemas import (
    TopicResponse, GenerateTopicResponse, SessionOut, 
    JAMSessionHistoryItem, LeaderboardEntry, ProgressPoint, DashboardStats
)
from app.auth import get_current_user
from app.config import settings

from app.services.voice_service import VoiceService
from app.services.vision_processor import process_video
from app.services.openai_service import OpenAIService
from app.services.coach_agent import CoachAgent
from app.services.audio_processor import (
    extract_audio, AudioExtractionError, GeminiAPIError, TranscriptGenerationError, process_audio
)
from app.services.topic_generator import generate_topic_from_llm
from app.services.ai_analyzer import analyze_video_speech, AnalysisParsingError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("jam_analyzer")

SESSION_ERRORS = {}

router = APIRouter(prefix="/jam", tags=["jam"])
api_router = APIRouter(tags=["jam"])

# Helper to get user from token for WebSocket
def get_websocket_user_sync(token: str) -> Optional[User]:
    if not token:
        return None
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # Strip any quotes
        if token.startswith('"') and token.endswith('"'):
            token = token[1:-1]
        elif token.startswith("'") and token.endswith("'"):
            token = token[1:-1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except Exception as e:
        logger.error(f"[WS Auth] Error authenticating websocket: {e}")
        return None
    finally:
        db.close()

@router.websocket("/session/{session_id}/realtime")
async def websocket_realtime_coach(websocket: WebSocket, session_id: str, token: Optional[str] = None):
    logger.info(f"[WS] WebSocket connection request for session {session_id}")
    
    # 1. Authenticate user
    user = await asyncio.to_thread(get_websocket_user_sync, token)
    if not user:
        logger.warning(f"[WS] Connection rejected: unauthorized (token: {token[:10] if token else 'None'}...)")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await websocket.accept()
    logger.info(f"[WS] Connection accepted for session {session_id}, user {user.name}")
    
    # Define directories and file paths
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    realtime_file_path = os.path.join(settings.UPLOAD_DIR, f"realtime_{session_id}.webm")
    temp_copy_path = os.path.join(settings.UPLOAD_DIR, f"temp_realtime_{session_id}.webm")
    
    # Make sure to remove any existing file from a previous attempt/run
    if os.path.exists(realtime_file_path):
        try:
            os.remove(realtime_file_path)
        except Exception:
            pass
            
    # Track statistics for aggregation
    wpm_list = []
    confidence_list = []
    final_filler_count = 0
    
    # Mutex or lock for files
    file_write_lock = asyncio.Lock()
    
    # Dynamic coach state suggestions
    # We update suggestions based on current WPM, confidence, fillers, and pauses
    def make_coach_suggestions(wpm: int, confidence: int, fillers_count: int, pause_count: int, pause_duration: float) -> List[str]:
        suggestions = []
        # Pace suggestion
        if wpm == 0:
            suggestions.append("✓ Start Speaking")
        elif wpm < 90:
            suggestions.append("⚠ Speak Faster")
        elif wpm > 160:
            suggestions.append("⚠ Slow Down")
        else:
            suggestions.append("✓ Good Pace")
            
        # Fillers suggestion
        if fillers_count > 4:
            suggestions.append("⚠ Too Many Fillers")
        else:
            suggestions.append("✓ Good Filler Control")
            
        # Confidence suggestion
        if confidence >= 71:
            suggestions.append("✓ Strong Confidence")
        elif confidence >= 41:
            suggestions.append("✓ Steady Confidence")
        else:
            suggestions.append("⚠ Build Confidence")
            
        # Pauses suggestion
        if pause_count > 0 and (pause_duration / pause_count) > 3.0:
            suggestions.append("⚠ Avoid Long Pauses")
        elif pause_count > 5:
            suggestions.append("⚠ Too Many Pauses")
        else:
            suggestions.append("✓ Natural Pauses")
            
        return suggestions
        
    # Helper task for periodic analysis
    async def periodic_analysis_loop():
        nonlocal final_filler_count
        await asyncio.sleep(3) # Initial warmup delay
        while True:
            try:
                # Check if there is data to analyze
                has_data = False
                async with file_write_lock:
                    if os.path.exists(realtime_file_path) and os.path.getsize(realtime_file_path) > 10000:
                        # Copy the file to avoid locking/conflicts during write
                        shutil.copyfile(realtime_file_path, temp_copy_path)
                        has_data = True
                        
                if has_data:
                    # Run STT & analysis pipeline in a separate thread
                    try:
                        metrics = await asyncio.to_thread(process_audio, temp_copy_path)
                        if metrics and metrics.get("raw_transcript"):
                            raw_transcript = metrics["raw_transcript"]
                            wpm = metrics["words_per_minute"]
                            filler_words = metrics["filler_words"]
                            avg_volume = metrics["average_volume"]
                            speech_dur = metrics["speech_duration"]
                            silence_dur = metrics["silence_duration"]
                            pauses_count = metrics["pause_count"]
                            pause_duration = metrics["pause_duration"]
                            
                            # Count active fillers
                            # Track: uh, um, ah, like, actually, basically, you know, sort of, kind of
                            tracked_fillers = ["uh", "um", "ah", "like", "actually", "basically", "you know", "sort of", "kind of"]
                            fillers_count = sum(filler_words.get(f, 0) for f in tracked_fillers)
                            final_filler_count = fillers_count
                            
                            # Find recent fillers (last 3 spoken)
                            words_tokens = [w.strip(".,!?;:\"'()").lower() for w in raw_transcript.split()]
                            recent_fillers = []
                            i = 0
                            while i < len(words_tokens):
                                if i + 1 < len(words_tokens):
                                    phrase = f"{words_tokens[i]} {words_tokens[i+1]}"
                                    if phrase in ["you know", "sort of", "kind of"]:
                                        recent_fillers.append(phrase)
                                        i += 2
                                        continue
                                if words_tokens[i] in ["uh", "um", "ah", "like", "actually", "basically"]:
                                    recent_fillers.append(words_tokens[i])
                                i += 1
                            recent_fillers = recent_fillers[-3:]
                            
                            # Calculate dynamic confidence
                            total_duration = speech_dur + silence_dur
                            continuity = speech_dur / total_duration if total_duration > 0 else 1.0
                            continuity_score = int(continuity * 100)
                            
                            # Voice energy score from avg_volume
                            energy_score = min(100, max(30, int(avg_volume / 80))) if avg_volume > 0 else 70
                            
                            # Pause frequency score
                            minutes = total_duration / 60.0 if total_duration > 0 else 1.0
                            pauses_per_min = pauses_count / minutes
                            if pauses_per_min < 2:
                                pause_score = 90
                            elif pauses_per_min <= 8:
                                pause_score = 100 - int((pauses_per_min - 2) * 5)
                            else:
                                pause_score = max(30, 70 - int((pauses_per_min - 8) * 10))
                                
                            # Speech clarity score
                            clarity_score = metrics.get("speaking_pace_score", 80)
                            
                            confidence = int(0.3 * continuity_score + 0.25 * energy_score + 0.2 * pause_score + 0.25 * clarity_score)
                            confidence = min(100, max(0, confidence))
                            
                            # Confidence levels
                            if confidence >= 71:
                                confidence_level = "High"
                            elif confidence >= 41:
                                confidence_level = "Medium"
                            else:
                                confidence_level = "Low"
                                
                            # Pace status
                            if wpm < 90:
                                wpm_status = "⚠ Speak Faster"
                            elif wpm <= 160:
                                wpm_status = "✓ Good Pace"
                            else:
                                wpm_status = "⚠ Slow Down"
                                
                            # Suggestions list
                            suggestions = make_coach_suggestions(wpm, confidence, fillers_count, pauses_count, pause_duration)
                            
                            # Track values for session metadata
                            wpm_list.append(wpm)
                            confidence_list.append(confidence)
                            
                            # Send real-time packet
                            await websocket.send_json({
                                "type": "metrics",
                                "wpm": wpm,
                                "wpm_status": wpm_status,
                                "fillers_count": fillers_count,
                                "recent_fillers": recent_fillers,
                                "confidence": confidence,
                                "confidence_level": confidence_level,
                                "suggestions": suggestions,
                                "transcript": raw_transcript
                            })
                    except Exception as pipe_err:
                        logger.warning(f"[WS Analysis] Inner pipeline analysis run skipped: {pipe_err}")
            except Exception as e:
                logger.error(f"[WS Analysis] Error in periodic analysis loop: {e}")
            finally:
                if os.path.exists(temp_copy_path):
                    try:
                        os.remove(temp_copy_path)
                    except Exception:
                        pass
            await asyncio.sleep(3)
            
    # Start analysis loop task
    analysis_task = asyncio.create_task(periodic_analysis_loop())
    
    try:
        while True:
            data = await websocket.receive()
            
            # Check for binary data
            if "bytes" in data:
                chunk = data["bytes"]
                async with file_write_lock:
                    with open(realtime_file_path, "ab") as f:
                        f.write(chunk)
                        
            # Check for text messages
            elif "text" in data:
                text_msg = data["text"]
                if text_msg == "stop":
                    logger.info(f"[WS] Stop signal received for session {session_id}")
                    break
    except WebSocketDisconnect:
        logger.info(f"[WS] WebSocket disconnected for session {session_id}")
    except Exception as exc:
        logger.error(f"[WS] WebSocket error: {exc}")
    finally:
        # Cancel the analysis background task
        analysis_task.cancel()
        
        # Clean up temp files
        for path in [realtime_file_path, temp_copy_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"[WS Cleanup] Could not delete file {path}: {e}")
                    
        # Compute session metadata values and write to database
        avg_wpm = int(sum(wpm_list) / len(wpm_list)) if wpm_list else 130
        max_wpm = max(wpm_list) if wpm_list else 170
        avg_confidence = int(sum(confidence_list) / len(confidence_list)) if confidence_list else 82
        
        session_metadata_payload = {
            "average_wpm": avg_wpm,
            "max_wpm": max_wpm,
            "filler_count": final_filler_count,
            "average_confidence": avg_confidence
        }
        
        logger.info(f"[WS Summary] Session {session_id} finished. Metadata: {session_metadata_payload}")
        
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            db_session = db.query(Session).filter(Session.id == session_id).first()
            if db_session:
                db_session.session_metadata = session_metadata_payload
                db.commit()
                logger.info(f"[WS Summary] Session metadata written to database for session {session_id}")
        except Exception as db_err:
            logger.error(f"[WS Summary] Database session metadata update failed: {db_err}")
        finally:
            db.close()

CATEGORIES = [
    "Technology",
    "AI",
    "Education",
    "Business",
    "Environment",
    "Startups",
    "Leadership",
    "Ethics",
    "Social Issues",
    "Innovation",
    "Future Trends",
    "Current Affairs"
]

@api_router.get("/generate-topic", response_model=GenerateTopicResponse)
def get_generate_topic(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    selected_cat = category
    if not selected_cat or selected_cat not in CATEGORIES:
        selected_cat = random.choice(CATEGORIES)
    
    # Retrieve user's recent topics to exclude
    recent_sessions = db.query(Session.topic).filter(
        Session.user_id == current_user.id
    ).order_by(Session.created_at.desc()).limit(20).all()
    exclude_topics = [s[0] for s in recent_sessions if s[0]]
    
    # Call topic generator
    try:
        topic_data = generate_topic_from_llm(selected_cat, exclude_topics, difficulty)
    except Exception as e:
        logger.error(f"Topic generation failed: {e}")
        try:
            from app.services.topic_generator import CATEGORY_MAPPING, TOPICS_METADATA
            if selected_cat in CATEGORY_MAPPING:
                selected_difficulty = difficulty if difficulty in ["Easy", "Medium", "Hard"] else "Medium"
                _, topic_pool = CATEGORY_MAPPING[selected_cat].get(selected_difficulty, CATEGORY_MAPPING[selected_cat]["Easy"])
                chosen_topic = random.choice(topic_pool)
                meta = TOPICS_METADATA[chosen_topic]
                topic_data = {
                    "topic": chosen_topic,
                    "category": selected_cat,
                    "difficulty": selected_difficulty,
                    "keywords": meta["keywords"],
                    "talking_points": meta["talking_points"],
                    "estimated_speaking_time": 60
                }
            else:
                raise ValueError()
        except Exception:
            topic_data = {
                "topic": "My Favorite Movie",
                "category": "Personal Topics",
                "difficulty": "Easy",
                "keywords": ["movies", "entertainment", "cinema"],
                "talking_points": ["Introduce your favorite movie", "Explain why it is your favorite", "Conclude with recommendation"],
                "estimated_speaking_time": 60
            }

    return {
        "topic": topic_data["topic"],
        "category": topic_data["category"],
        "difficulty": topic_data["difficulty"],
        "keywords": topic_data["keywords"],
        "talking_points": topic_data.get("talking_points", []),
        "estimated_speaking_time": topic_data.get("estimated_speaking_time", 60)
    }

@router.get("/topic", response_model=GenerateTopicResponse)
def get_jam_topic(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    return get_generate_topic(category=category, difficulty=difficulty, current_user=current_user, db=db)

@router.post("/session", response_model=SessionOut)
def create_session(
    topic_data: TopicResponse, 
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    session = Session(
        user_id=current_user.id,
        session_type="jam",
        topic=topic_data.topic,
        category=topic_data.category,
        difficulty=topic_data.difficulty,
        instant_start=topic_data.instant_start,
        preparation_mode=topic_data.preparation_mode,
        skip_preparation=topic_data.skip_preparation
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

@router.post("/session/{session_id}/upload", response_model=SessionOut)
async def upload_video(
    session_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("STEP 1:\nMedia upload received")
    logger.info("Request Received")
    logger.info("Recording Received")
    try:
        session = db.query(Session).filter(
            Session.id == session_id, 
            Session.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
            
        # Check file extension
        file_ext = os.path.splitext(file.filename)[1] or ".webm"
        video_filename = f"{session_id}{file_ext}"
        video_path = os.path.join(settings.UPLOAD_DIR, video_filename)
        logger.info(f"[JAM Upload] Video upload received. Saving video to: {video_path}...")
        
        # Save file locally
        try:
            with open(video_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            logger.info(f"[JAM Upload] Video saved successfully. Size: {len(content)} bytes.")
            logger.info("STEP 2:\nVideo saved successfully")
        except Exception as e:
            logger.error(f"[JAM Upload] Failed to save uploaded video: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save uploaded video: {str(e)}"
            )
            
        session.video_url = f"/uploads/{video_filename}"
        session.analysis_status = "processing"
        
        # Save recording details
        recording = db.query(SessionRecording).filter(SessionRecording.session_id == session_id).first()
        if not recording:
            recording = SessionRecording(
                session_id=session_id,
                user_id=current_user.id,
                video_path=video_path,
                upload_time=datetime.utcnow()
            )
            db.add(recording)
        else:
            recording.video_path = video_path
            recording.upload_time = datetime.utcnow()

        db.commit()
        db.refresh(session)

        # Snapshot values needed in the background thread (avoid passing db session)
        session_id = session.id
        topic = session.topic
        category = session.category
        user_id = current_user.id

        # Return immediately — analysis runs in a daemon thread
        def run_analysis_background():
            from app.database import SessionLocal
            bg_db = SessionLocal()
            try:
                bg_session = bg_db.query(Session).filter(Session.id == session_id).first()
                if not bg_session:
                    return

                pipeline_start = time.time()
                logger.info(f"[BG] Starting analysis pipeline for session {session_id}")

                # Stage 1: Full AI analysis (Whisper + MediaPipe + Gemini)
                t1 = time.time()
                logger.info("[BG] Stage 1: Running analyze_video_speech...")
                report_data = analyze_video_speech(video_path, topic, category)
                logger.info(f"[BG] Stage 1 completed in {time.time() - t1:.2f}s")

                if report_data.get("status") == "NO_SPEECH_DETECTED":
                    bg_session.analysis_status = "failed"
                    SESSION_ERRORS[session_id] = "Transcript generation failed"
                    bg_db.commit()
                    logger.warning(f"[BG] No speech detected for session {session_id}. Marked as failed.")
                    return

                # Stage 2: Save all DB records
                logger.info("STEP 9:\nDatabase save started")
                t2 = time.time()
                logger.info("[BG] Stage 2: Saving records to database...")

                try:
                    _raw_t = report_data["original_transcript"]
                    _corr_t = report_data["corrected_transcript"]
                    logger.info("TRANSCRIPT SAVED:")
                    logger.info(f"  raw_transcript  length : {len(_raw_t)} chars")
                    logger.info(f"  corrected_transcript length : {len(_corr_t)} chars")
                    logger.info(f"  raw_transcript preview : '{_raw_t[:500]}'")

                    transcript_record = Transcript(
                        session_id=session_id,
                        raw_transcript=_raw_t,
                        corrected_transcript=_corr_t,
                        confidence_score=report_data["transcript_confidence"],
                        wpm=report_data["words_per_minute"],
                        pauses_detected=[],
                        word_timings=[]
                    )
                    bg_db.add(transcript_record)
                    logger.info("Transcript Saved")
                    logger.info(f"Transcript length: {len(_raw_t)} chars")

                    v_metrics_record = VoiceMetrics(
                        session_id=session_id,
                        pitch_variation=0.0,
                        energy_variation=0.0,
                        rhythm_score=float(report_data["words_per_minute"]),
                        stability_score=float(report_data["transcript_confidence"]),
                        pause_frequency=0.0,
                        vocal_verdict="Dynamic" if report_data["overall_score"] >= 75 else "Stable",
                        raw_metrics={}
                    )
                    bg_db.add(v_metrics_record)

                    f_metrics_record = FaceMetrics(
                        session_id=session_id,
                        eye_contact_percentage=float(report_data["eye_contact_score"]),
                        gaze_direction_distribution={},
                        head_movement_variance=0.0,
                        head_tilt_average=0.0,
                        smile_frequency=float(report_data["emotion_stability_score"]),
                        attention_score=float(report_data["eye_contact_score"]),
                        engagement_score=float(report_data["engagement_score"]),
                        posture_stability=float(report_data["posture_score"]),
                        attention_heatmap=[]
                    )
                    bg_db.add(f_metrics_record)
                    bg_db.flush()

                    dna_record = CommunicationDNA(
                        user_id=user_id,
                        session_id=session_id,
                        confidence=int(report_data["confidence_score"]),
                        fluency=int(report_data["fluency_score"]),
                        vocabulary=int(report_data["vocabulary_score"]),
                        storytelling=int(report_data["vocabulary_score"]),
                        leadership=int(report_data["communication_score"]),
                        persuasion=int(report_data["content_quality_score"]),
                        emotional_intelligence=int(report_data["emotion_stability_score"]),
                        clarity=int(report_data["clarity_score"] * 10),
                        energy_level=80,
                        speaking_speed=int(report_data["speaking_pace_score"]),
                        eye_contact=int(report_data["eye_contact_score"]),
                        posture=int(report_data["posture_score"]),
                        engagement=int(report_data["engagement_score"]),
                        filler_words=int(report_data["overall_score"]),
                        profile_summary=report_data["final_verdict"],
                        filler_word_frequency=report_data["filler_words"]
                    )
                    bg_db.add(dna_record)

                    report = Report(
                        session_id=session_id,
                        summary=report_data["report_data"]
                    )
                    bg_db.add(report)
                    
                    bg_session.final_score = int(report_data.get("overall_score", 0))
                    bg_session.analysis_status = "completed"
                    bg_db.commit()
                    logger.info("STEP 10:\nDatabase save completed")
                    logger.info("Database Updated")
                    logger.info(f"[BG] Stage 2 completed in {time.time() - t2:.2f}s")
                    logger.info(f"[BG] Full pipeline done in {time.time() - pipeline_start:.2f}s for session {session_id}")
                except SQLAlchemyError as db_exc:
                    logger.error(f"[BG] Database save failed: {db_exc}", exc_info=True)
                    bg_db.rollback()
                    raise db_exc

            except Exception as exc:
                logger.error(f"[BG] Analysis pipeline failed for session {session_id}: {exc}", exc_info=True)
                
                # Check exception type to map it to correct detailed error message
                error_msg = "Analysis failed on server"
                if isinstance(exc, AudioExtractionError):
                    error_msg = "Audio extraction failed"
                elif isinstance(exc, GeminiAPIError):
                    error_msg = "Gemini API failed"
                elif isinstance(exc, TranscriptGenerationError):
                    error_msg = "Transcript generation failed"
                elif isinstance(exc, AnalysisParsingError):
                    error_msg = "Analysis parsing failed"
                elif isinstance(exc, SQLAlchemyError):
                    error_msg = "Database save failed"
                    
                SESSION_ERRORS[session_id] = error_msg
                
                try:
                    bg_session = bg_db.query(Session).filter(Session.id == session_id).first()
                    if bg_session:
                        bg_session.analysis_status = "failed"
                        bg_db.commit()
                except Exception:
                    pass
            finally:
                bg_db.close()

        thread = threading.Thread(target=run_analysis_background, daemon=True)
        thread.start()
        logger.info(f"[JAM Upload] Analysis background job started for session {session_id}. Returning session immediately.")

        db.refresh(session)
        logger.info("STEP 11:\nResponse returned")
        logger.info("Response Returned")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in upload_video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )

@router.get("/session/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    try:
        session = db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        # Dynamic progress and message generation
        elapsed = (datetime.utcnow() - session.created_at).total_seconds()
        if session.analysis_status == "completed":
            session.status = "completed"
            session.progress = 100
            session.message = "Analysis completed."
            
            # Dynamic migration/backpopulate final_score for existing sessions
            if getattr(session, "final_score", 0) == 0:
                score = 0
                if session.reports and session.reports[0].summary:
                    score = session.reports[0].summary.get("overall_score", 0)
                if score == 0:
                    score = get_session_score(session)
                session.final_score = int(score)
                db.commit()
        elif session.analysis_status == "failed":
            session.status = "failed"
            session.progress = 100
            session.message = SESSION_ERRORS.get(session_id, "Analysis failed.")
        else:
            session.status = "processing"
            session.progress = min(90, int(10 + (elapsed / 45.0) * 80.0))
            session.message = "Analysis is still running."

        _api_raw_t = session.transcript.raw_transcript if session.transcript else ""
        logger.info("Transcript Returned")
        logger.info(f"Transcript length: {len(_api_raw_t)} chars")
        logger.info("Response Returned")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )

@api_router.get("/session/{session_id}/video")
def get_session_video(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )
        
    recording = db.query(SessionRecording).filter(SessionRecording.session_id == session_id).first()
    
    # Fallback to session.video_url if recording row doesn't exist but video_url does
    if not recording:
        if session.video_url:
            return {"video_url": session.video_url}
        raise HTTPException(
            status_code=404,
            detail="Recording not available for this session."
        )
        
    # Verify file exists on disk
    if not os.path.exists(recording.video_path):
        raise HTTPException(
            status_code=404,
            detail="Recording not available for this session."
        )
        
    video_filename = os.path.basename(recording.video_path)
    video_url = f"/uploads/{video_filename}"
    return {"video_url": video_url}

def get_session_score(s: Session) -> int:
    if s.session_type == "debate" and s.debate_session:
        d = s.debate_session
        scores_list = [
            d.argument_quality_score,
            d.persuasion_score,
            d.logical_consistency_score,
            d.confidence_score,
            d.rebuttal_score,
            d.communication_score,
            d.clarity_score,
            d.vocabulary_score
        ]
        valid_scores = [val for val in scores_list if val is not None]
        return int(sum(valid_scores) / len(valid_scores)) if valid_scores else 70
    elif s.dna:
        dna_metrics = [
            s.dna.confidence,
            s.dna.fluency,
            s.dna.vocabulary,
            s.dna.storytelling,
            s.dna.leadership,
            s.dna.persuasion,
            s.dna.clarity
        ]
        return int(sum(dna_metrics) / 7)
    return 0

@router.get("/history", response_model=List[JAMSessionHistoryItem])
def get_history(
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    logger.info("API Request Started")
    start_time = time.time()
    try:
        # Fetch standard sessions
        sessions_query = db.query(Session).filter(
            Session.user_id == current_user.id
        ).order_by(Session.created_at.desc())
        
        # Fetch document sessions
        doc_sessions_query = db.query(DocumentSession).filter(
            DocumentSession.user_id == current_user.id
        ).order_by(DocumentSession.created_at.desc())
        
        # Fetch viva sessions
        viva_sessions_query = db.query(VivaSession).filter(
            VivaSession.user_id == current_user.id
        ).order_by(VivaSession.created_at.desc())
        
        if limit is not None:
            sessions_query = sessions_query.limit(limit)
            doc_sessions_query = doc_sessions_query.limit(limit)
            viva_sessions_query = viva_sessions_query.limit(limit)
            
        sessions = sessions_query.all()
        doc_sessions = doc_sessions_query.all()
        viva_sessions = viva_sessions_query.all()
        
        logger.info("Database Queries Executed")
        logger.info(f"Records found: standard={len(sessions)}, doc={len(doc_sessions)}, viva={len(viva_sessions)}")
        
        history_items = []
        
        # Process standard sessions (JAM, Debate, Interview)
        for s in sessions:
            try:
                score = 0
                if s.analysis_status == "completed":
                    score = getattr(s, "final_score", 0)
                    if score == 0 or score is None:
                        if s.reports and s.reports[0].summary:
                            score = s.reports[0].summary.get("overall_score", 0)
                        if score == 0:
                            score = get_session_score(s)
                        s.final_score = int(score)
                        db.commit()
                
                history_items.append({
                    "id": str(s.id),
                    "topic": str(s.topic) if s.topic else "Untitled Topic",
                    "category": str(s.category) if s.category else "General",
                    "difficulty": str(s.difficulty) if getattr(s, "difficulty", None) else "Medium",
                    "session_type": str(s.session_type),
                    "created_at": s.created_at,
                    "final_score": int(score),
                    "overall_score": int(score),
                    "status": str(s.analysis_status) if s.analysis_status else "completed"
                })
            except Exception as e:
                logger.warning(f"Error processing standard session {getattr(s, 'id', 'unknown')}: {e}")
                continue
            
        # Process document sessions
        for s in doc_sessions:
            try:
                score = 0
                if s.report:
                    score = int((s.report.accuracy_score + s.report.coverage_score + s.report.understanding_score + s.report.explanation_quality + s.report.technical_correctness + s.report.relevance_score) / 6)
                history_items.append({
                    "id": str(s.id),
                    "topic": str(s.topic_title) if s.topic_title else "Untitled Document Session",
                    "category": str(getattr(s, "session_type", "presentation")).capitalize(),
                    "session_type": "document",
                    "created_at": s.created_at,
                    "final_score": int(score),
                    "overall_score": int(score),
                    "status": "completed" if s.report else "processing"
                })
            except Exception as e:
                logger.warning(f"Error processing document session {getattr(s, 'id', 'unknown')}: {e}")
                continue
            
        # Process viva sessions
        for s in viva_sessions:
            try:
                history_items.append({
                    "id": str(s.id),
                    "topic": f"Viva Q&A: {s.document.title if (s.document and s.document.title) else 'Untitled Document'}",
                    "category": str(s.mode).capitalize() if s.mode else "Viva",
                    "session_type": "viva",
                    "created_at": s.created_at,
                    "final_score": int(s.overall_score) if s.overall_score is not None else 0,
                    "overall_score": int(s.overall_score) if s.overall_score is not None else 0,
                    "status": "completed"
                })
            except Exception as e:
                logger.warning(f"Error processing viva session {getattr(s, 'id', 'unknown')}: {e}")
                continue
            
        # Sort combined list by created_at desc
        history_items.sort(key=lambda x: x["created_at"], reverse=True)
        
        if limit is not None:
            history_items = history_items[:limit]
            
        processing_time = time.time() - start_time
        logger.info("Analytics Data Processed")
        logger.info(f"Response size: {len(str(history_items))} chars")
        logger.info(f"Processing time: {processing_time:.4f}s")
        logger.info("Response Returned")
        return history_items
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.exception("JAM History Error")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )

@router.get("/leaderboard", response_model=List[LeaderboardEntry])
def get_leaderboard(db: DBSession = Depends(get_db)):
    users = db.query(User).all()
    leaderboard = []
    
    for u in users:
        sessions = db.query(Session).filter(Session.user_id == u.id).all()
        scored_sessions = [s for s in sessions if s.dna]
        
        if not scored_sessions:
            continue
            
        total_score_sum = 0
        for s in scored_sessions:
            score = int((s.dna.confidence + s.dna.fluency + s.dna.vocabulary + s.dna.storytelling + s.dna.leadership + s.dna.persuasion + s.dna.clarity) / 7)
            total_score_sum += score
            
        user_average = round(total_score_sum / len(scored_sessions), 1)
        leaderboard.append({
            "name": u.name,
            "average_score": user_average,
            "sessions_count": len(scored_sessions)
        })
        
    leaderboard.sort(key=lambda x: x["average_score"], reverse=True)
    
    ranked_leaderboard = []
    for i, entry in enumerate(leaderboard):
        ranked_leaderboard.append({
            "rank": i + 1,
            "name": entry["name"],
            "average_score": entry["average_score"],
            "sessions_count": entry["sessions_count"]
        })
        
    return ranked_leaderboard[:10]

@router.get("/analytics", response_model=DashboardStats)
def get_analytics(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    logger.info("API Request Started")
    start_time = time.time()
    try:
        # Fetch standard sessions
        sessions = db.query(Session).filter(
            Session.user_id == current_user.id
        ).order_by(Session.created_at.asc()).all()
        
        logger.info("Loading analytics")
        jam_sessions = [s for s in sessions if s.session_type == "jam"]
        debate_sessions = [s for s in sessions if s.session_type == "debate"]
        interview_sessions = [s for s in sessions if s.session_type == "interview"]
        logger.info(f"JAM records: {len(jam_sessions)}")
        logger.info(f"Debate records: {len(debate_sessions)}")
        logger.info(f"Interview records: {len(interview_sessions)}")
        
        # Fetch document sessions
        doc_sessions = db.query(DocumentSession).filter(
            DocumentSession.user_id == current_user.id
        ).order_by(DocumentSession.created_at.asc()).all()
        
        # Fetch viva sessions
        viva_sessions = db.query(VivaSession).filter(
            VivaSession.user_id == current_user.id
        ).order_by(VivaSession.created_at.asc()).all()
        
        scored_sessions = []
        
        # Process standard sessions (JAM, Debate, Interview)
        for s in sessions:
            try:
                if s.analysis_status == "completed":
                    conf = 70
                    flu = 70
                    comm = 70
                    vocab = 70
                    story = 70
                    lead = 70
                    pers = 70
                    eng = 70
                    
                    if s.session_type == "debate" and s.debate_session:
                        d = s.debate_session
                        conf = d.confidence_score or 70
                        flu = d.communication_score or 70
                        comm = d.clarity_score or 70
                        vocab = d.vocabulary_score or 70
                        story = d.argument_quality_score or 70
                        lead = d.communication_score or 70
                        pers = d.persuasion_score or 70
                        eng = d.persuasion_score or 70
                    elif s.dna:
                        conf = s.dna.confidence if s.dna.confidence is not None else 70
                        flu = s.dna.fluency if s.dna.fluency is not None else 70
                        comm = s.dna.clarity if s.dna.clarity is not None else 70
                        vocab = s.dna.vocabulary if s.dna.vocabulary is not None else 70
                        story = s.dna.storytelling if s.dna.storytelling is not None else 70
                        lead = s.dna.leadership if s.dna.leadership is not None else 70
                        pers = s.dna.persuasion if s.dna.persuasion is not None else 70
                        eng = s.dna.engagement if s.dna.engagement is not None else 70
                    
                    if s.created_at is not None:
                        scored_sessions.append({
                            "created_at": s.created_at,
                            "confidence": int(conf),
                            "fluency": int(flu),
                            "clarity": int(comm),
                            "vocabulary": int(vocab),
                            "storytelling": int(story),
                            "leadership": int(lead),
                            "persuasion": int(pers),
                            "engagement": int(eng)
                        })
            except Exception as e:
                logger.warning(f"Error processing analytics for standard session {getattr(s, 'id', 'unknown')}: {e}")
                continue
                
        # Process document sessions
        for s in doc_sessions:
            try:
                if s.report:
                    metrics = s.report.communication_metrics or {}
                    conf = metrics.get("confidence", 80)
                    flu = metrics.get("fluency", 80)
                    comm = metrics.get("leadership", 80)
                    vocab = metrics.get("vocabulary", 80)
                    story = metrics.get("persuasion", 80)
                    lead = metrics.get("leadership", 80)
                    pers = metrics.get("persuasion", 80)
                    eng = metrics.get("engagement", 80)
                    
                    if s.created_at is not None:
                        scored_sessions.append({
                            "created_at": s.created_at,
                            "confidence": int(conf) if conf is not None else 80,
                            "fluency": int(flu) if flu is not None else 80,
                            "clarity": int(comm) if comm is not None else 80,
                            "vocabulary": int(vocab) if vocab is not None else 80,
                            "storytelling": int(story) if story is not None else 80,
                            "leadership": int(lead) if lead is not None else 80,
                            "persuasion": int(pers) if pers is not None else 80,
                            "engagement": int(eng) if eng is not None else 80
                        })
            except Exception as e:
                logger.warning(f"Error processing analytics for document session {getattr(s, 'id', 'unknown')}: {e}")
                continue
                
        # Process viva sessions
        for s in viva_sessions:
            try:
                score = s.overall_score if s.overall_score is not None else 0
                if s.created_at is not None:
                    scored_sessions.append({
                        "created_at": s.created_at,
                        "confidence": int(score),
                        "fluency": int(score),
                        "clarity": int(score),
                        "vocabulary": int(score),
                        "storytelling": int(score),
                        "leadership": int(score),
                        "persuasion": int(score),
                        "engagement": int(score)
                    })
            except Exception as e:
                logger.warning(f"Error processing analytics for viva session {getattr(s, 'id', 'unknown')}: {e}")
                continue
            
        sessions_count = len(scored_sessions)
        print("Sessions Found:", sessions_count)
        logger.info(f"Sessions Found: {sessions_count}")
        
        if not scored_sessions:
            res = {
                "total_sessions": 0,
                "avg_confidence": 0.0,
                "avg_fluency": 0.0,
                "avg_communication": 0.0,
                "streak": 0,
                "progress_data": []
            }
            print("Analytics Generated:", res)
            logger.info("Analytics Generated empty response due to no scored sessions")
            return res
            
        # Averages
        avg_confidence = round(sum(s["confidence"] for s in scored_sessions) / sessions_count, 1)
        avg_fluency = round(sum(s["fluency"] for s in scored_sessions) / sessions_count, 1)
        avg_communication = round(sum(s["clarity"] for s in scored_sessions) / sessions_count, 1)
        
        # Streak Calculation across all sessions
        all_dates = []
        for s in sessions:
            if s.created_at:
                all_dates.append(s.created_at.date())
        for s in doc_sessions:
            if s.created_at:
                all_dates.append(s.created_at.date())
        for s in viva_sessions:
            if s.created_at:
                all_dates.append(s.created_at.date())
            
        dates = sorted(list(set(all_dates)))
        streak = 0
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        
        if today in dates or yesterday in dates:
            streak = 1
            current_date = dates[-1]
            for i in range(len(dates) - 2, -1, -1):
                if current_date - dates[i] == timedelta(days=1):
                    streak += 1
                    current_date = dates[i]
                else:
                    break
        
        # Progress Timeline data
        progress_data = []
        daily_groups = {}
        for s in scored_sessions:
            date_str = s["created_at"].strftime("%Y-%m-%d")
            if date_str not in daily_groups:
                daily_groups[date_str] = []
            daily_groups[date_str].append(s)
            
        for date_str, items in sorted(daily_groups.items()):
            progress_data.append({
                "date": date_str,
                "confidence": round(sum(d["confidence"] for d in items) / len(items), 1),
                "fluency": round(sum(d["fluency"] for d in items) / len(items), 1),
                "vocabulary": round(sum(d["vocabulary"] for d in items) / len(items), 1),
                "storytelling": round(sum(d["storytelling"] for d in items) / len(items), 1),
                "leadership": round(sum(d["leadership"] for d in items) / len(items), 1),
                "persuasion": round(sum(d["persuasion"] for d in items) / len(items), 1),
                "engagement": round(sum(d["engagement"] for d in items) / len(items), 1)
            })
            
        res = {
            "total_sessions": sessions_count,
            "avg_confidence": avg_confidence,
            "avg_fluency": avg_fluency,
            "avg_communication": avg_communication,
            "streak": streak,
            "progress_data": progress_data
        }
        
        print("Analytics Generated:", res)
        
        processing_time = time.time() - start_time
        logger.info("Analytics Data Processed")
        logger.info(f"Response size: {len(str(res))} chars")
        logger.info(f"Processing time: {processing_time:.4f}s")
        logger.info("Response Returned")
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )
