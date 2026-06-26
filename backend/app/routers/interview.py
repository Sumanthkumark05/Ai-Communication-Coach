import os
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import User, Session, InterviewSession, Transcript, CommunicationDNA, VoiceMetrics, FaceMetrics, Report, SessionRecording, DocumentSession
from app.schemas import SessionOut
from app.auth import get_current_user
from app.config import settings
from app.services.openai_service import OpenAIService
from app.services.ai_analyzer import analyze_video_speech

logger = logging.getLogger("jam_analyzer")

# Local per-session error store (process-local, for debug logging only).
# Previously imported from jam.py; moved here to eliminate the cross-module dependency.
_SESSION_ERRORS: dict = {}


router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/start")
def start_interview(
    role: str,
    round_type: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Initializes a new Interview Simulator session and returns the first question.
    """
    import time
    start_time = time.time()
    logger.info("Request Received")
    try:
        topic = f"{role} Mock Interview ({round_type})"
        category = "Interview"

        # 1. Create session record
        db_start = time.time()
        session = Session(
            user_id=current_user.id,
            session_type="interview",
            topic=topic,
            category=category
        )
        db.add(session)
        db.flush()
        db_init_time = time.time() - db_start

        # 2. Call OpenAI to generate the first question
        logger.info("LLM Client Initialized")
        logger.info("LLM Request Sent")
        llm_start = time.time()
        try:
            openai_service = OpenAIService()
            first_question = openai_service.generate_interview_question(
                role=role,
                round_type=round_type,
                question_history=[]
            )
            logger.info("LLM Response Received")
        except Exception as e:
            logger.error(f"Failed to generate first interview question: {e}")
            logger.info("LLM Response Received")
            first_question = "Tell me about yourself and your background."
        llm_gen_time = time.time() - llm_start

        # 3. Create interview session record
        db_start2 = time.time()
        interview_session = InterviewSession(
            session_id=session.id,
            role=role,
            round_type=round_type,
            question_history=[first_question]
        )
        db.add(interview_session)
        db.commit()
        db_commit_time = time.time() - db_start2

        total_time = time.time() - start_time
        logger.info(f"[PERF] start_interview timing: db_init={db_init_time:.4f}s, llm_gen={llm_gen_time:.4f}s, db_commit={db_commit_time:.4f}s, total={total_time:.4f}s")
        logger.info("Response Returned")
        return {
            "session_id": session.id,
            "role": role,
            "round_type": round_type,
            "question": first_question
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error starting interview: {e}")
        import traceback
        print("FULL TRACEBACK:")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
        )



@router.post("/{session_id}/answer")
def submit_answer(
    session_id: str,
    user_answer: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Submits user's text answer, generates constructive feedback, and returns the next question.
    """
    logger.info("Request Received")
    try:
        session = db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == current_user.id
        ).first()

        if not session or not session.interview_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active interview session not found."
            )

        interview = session.interview_session
        openai_service = OpenAIService()
        logger.info("LLM Client Initialized")

        if not settings.GROQ_API_KEY:
            logger.error("[Interview] AI model failed to initialize: GROQ_API_KEY is not configured.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI model failed to initialize"
            )

        import json

        # 1. Generate feedback for the previous question/answer pair
        last_question = interview.question_history[-1] if interview.question_history else "Tell me about your background."

        feedback_prompt = f"""
        Provide constructive interview coaching feedback on the user's answer.
        Question Asked: "{last_question}"
        User Answer:
        \"\"\"{user_answer}\"\"\"

        Provide concise specific fields:
        - communication_feedback: (tips on clarity, STAR structure, pacing)
        - confidence_feedback: (tips on word certainty, hesitation, vocabulary)

        Return ONLY valid JSON like:
        {{"communication_feedback": "text...", "confidence_feedback": "text..."}}
        """

        fallback_feedback = {
            "communication_feedback": "A solid response. Keep focusing on the STAR method to structure your key highlights.",
            "confidence_feedback": "Delivery was confident. Work on reducing slight pauses to sound even more polished."
        }
        
        logger.info("LLM Request Sent")
        feedback_data = openai_service.call_llm_json(
            prompt=feedback_prompt,
            system_prompt="You are a professional interview coach. Return valid JSON only.",
            fallback_dict=fallback_feedback
        )
        logger.info("LLM Response Received")

        # 2. Generate the next follow-up question
        logger.info("LLM Request Sent")
        next_question = openai_service.generate_interview_question(
            role=interview.role,
            round_type=interview.round_type,
            question_history=list(interview.question_history)
        )
        logger.info("LLM Response Received")

        # 3. Update interview session record
        history = list(interview.question_history)
        history.append(next_question)
        interview.question_history = history

        interview.communication_feedback = feedback_data.get("communication_feedback", "")
        interview.confidence_feedback = feedback_data.get("confidence_feedback", "")

        # CRITICAL FIX: Mark parent session completed so it shows in Recent Sessions
        # and Growth Analytics after each answered question
        session.analysis_status = "completed"

        db.commit()
        logger.info("Analysis Generated")
        logger.info("Response Returned")

        return {
            "feedback": feedback_data,
            "next_question": next_question
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to process interview response: {e}")
        import traceback
        print("FULL TRACEBACK:")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
        )


@router.post("/session/{session_id}/upload", response_model=SessionOut)
async def upload_interview_video(
    session_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    import time
    # [STEP 1] Audio file received
    logger.info(f"[STEP 1]\nAudio file received\n- filename: {file.filename}\n- size: unknown (streaming)\n- content type: {file.content_type}")
    logger.info("Request Received")
    logger.info("Recording Received")
    try:
        # 1. Retrieve the session
        session = db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == current_user.id
        ).first()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found."
            )

        # Organize recordings by user and generate unique filenames
        recordings_dir = os.path.join(settings.UPLOAD_DIR, "recordings", f"user_{current_user.id}")
        os.makedirs(recordings_dir, exist_ok=True)
        file_ext = os.path.splitext(file.filename or "recording.webm")[1] or ".webm"
        video_filename = f"session_{session_id}{file_ext}"
        video_path = os.path.join(recordings_dir, video_filename)

        logger.info(f"[Interview Upload] Video upload received. Saving video to: {video_path}")
        try:
            with open(video_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            # Update Step 1 with actual size
            logger.info(f"[STEP 1] Completed\n- size: {len(content)} bytes")
            # [STEP 2] Audio saved successfully
            logger.info(f"[STEP 2]\nAudio saved successfully\n- file path: {video_path}")
            logger.info(f"[Interview Upload] Saved {len(content):,} bytes.")
        except Exception as e:
            logger.error(f"[Interview Upload] Failed to save video: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded video."
            )

        session.video_url = f"/uploads/recordings/user_{current_user.id}/{video_filename}"
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

        # Snapshot parameters for background thread
        topic = session.topic
        category = session.category
        user_id = current_user.id

        import threading

        def run_interview_analysis_background():
            from app.database import SessionLocal
            from app.models import Transcript, Session, VoiceMetrics, FaceMetrics, CommunicationDNA, Report
            bg_db = SessionLocal()
            try:
                bg_session = bg_db.query(Session).filter(Session.id == session_id).first()
                if not bg_session:
                    return

                pipeline_start = time.time()
                logger.info(f"[BG Interview] Starting analysis pipeline for session {session_id}")

                # Stage 1: Full centralized A/V analysis pipeline
                t1 = time.time()
                report_data = analyze_video_speech(video_path, topic, category, db=bg_db, job_id=session_id, job_model=Session)
                logger.info(f"[BG Interview] Stage 1 completed in {time.time() - t1:.2f}s")

                if report_data.get("status") == "NO_SPEECH_DETECTED":
                    bg_session.analysis_status = "failed"
                    bg_db.commit()
                    logger.warning(f"[BG Interview] No speech detected for session {session_id}. Marked as failed.")
                    return

                # Stage 2: Persist transcript, voice, face metrics, DNA and report
                t2 = time.time()
                logger.info("[BG Interview] Stage 2: Saving records to database...")

                transcript_record = Transcript(
                    session_id=session_id,
                    raw_transcript=report_data["original_transcript"],
                    corrected_transcript=report_data["corrected_transcript"],
                    confidence_score=report_data["transcript_confidence"],
                    wpm=report_data["words_per_minute"],
                    pauses_detected=[],
                    word_timings=[]
                )
                bg_db.add(transcript_record)
                logger.info("Transcript Saved")

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
                # [STEP 8] Database save
                logger.info("[STEP 8]\nDatabase save\n- success/failure: success")
                logger.info(f"[BG Interview] Database successfully committed. Stage 2 completed in {time.time() - t2:.2f}s")
                logger.info(f"[BG Interview] Full pipeline done in {time.time() - pipeline_start:.2f}s for session {session_id}")

            except Exception as exc:
                logger.error(f"[BG Interview] Analysis pipeline failed for session {session_id}: {exc}", exc_info=True)
                import traceback
                print("FULL TRACEBACK:")
                traceback.print_exc()
                
                # [STEP 8] Database save
                logger.info("[STEP 8]\nDatabase save\n- success/failure: failure")
                
                error_msg = f"Error Type: {type(exc).__name__}\nError Message: {str(exc)}\nTraceback:\n{traceback.format_exc()}"
                _SESSION_ERRORS[session_id] = error_msg
                
                try:
                    bg_session = bg_db.query(Session).filter(Session.id == session_id).first()
                    if bg_session:
                        bg_session.analysis_status = "failed"
                        bg_db.commit()
                except Exception:
                    pass
            finally:
                bg_db.close()

        # Spawn background analysis thread
        thread = threading.Thread(target=run_interview_analysis_background, daemon=True)
        thread.start()
        logger.info(f"[Interview Upload] Analysis background job started for session {session_id}. Returning session immediately.")

        db.refresh(session)
        logger.info("Response Returned")
        
        # [STEP 9] Final API response
        logger.info(f"[STEP 9]\nFinal API response\n- status: {session.analysis_status}\n- session ID: {session.id}")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in upload_interview_video: {e}")
        import traceback
        print("FULL TRACEBACK:")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
        )


# =========================================================================
# SECURE VIDEO STREAMING & PLAYBACK ROUTER
# =========================================================================
from fastapi import Header, Query, APIRouter
from jose import jwt
import mimetypes

interviews_router = APIRouter(tags=["interviews"])

def get_user_from_token(token_str: str, db: DBSession) -> User:
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token missing",
        )
    # Strip quotes
    if token_str.startswith('"') and token_str.endswith('"'):
        token_str = token_str[1:-1]
    elif token_str.startswith("'") and token_str.endswith("'"):
        token_str = token_str[1:-1]
        
    try:
        payload = jwt.decode(token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


@interviews_router.get("/interviews/{session_id}/video-info")
def get_interview_video_info(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    # Retrieve the session
    session = db.query(Session).filter(Session.id == session_id).first()
    video_path = None
    upload_time = None

    if not session:
        # Check document sessions
        doc_session = db.query(DocumentSession).filter(DocumentSession.id == session_id).first()
        if not doc_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        # Verify ownership
        if doc_session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session's video"
            )
        if doc_session.video_url:
            rel_path = doc_session.video_url.replace("/uploads/", "")
            video_path = os.path.join(settings.UPLOAD_DIR, rel_path)
            upload_time = doc_session.created_at
    else:
        # Verify ownership
        if session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session's video"
            )
        # Check if recording exists in DB
        recording = db.query(SessionRecording).filter(SessionRecording.session_id == session_id).first()
        if recording and recording.video_path and os.path.exists(recording.video_path):
            video_path = recording.video_path
            upload_time = recording.upload_time
        elif session.video_url:
            rel_path = session.video_url.replace("/uploads/", "")
            video_path = os.path.join(settings.UPLOAD_DIR, rel_path)
            upload_time = session.created_at

    if not video_path or not os.path.exists(video_path):
        return {
            "exists": False,
            "video_url": None,
            "message": "No recording available"
        }
        
    # Generate temporary token for playback
    from app.auth import create_access_token
    from datetime import timedelta
    stream_token = create_access_token(
        data={"sub": current_user.id},
        expires_delta=timedelta(minutes=30)
    )
    
    video_stream_url = f"/api/interviews/{session_id}/video?token={stream_token}"
    
    return {
        "exists": True,
        "video_url": video_stream_url,
        "upload_time": upload_time or datetime.utcnow()
    }
 
 
@interviews_router.get("/interviews/{session_id}/video")
def stream_interview_video(
    session_id: str,
    token: Optional[str] = Query(None),
    range: Optional[str] = Header(None),
    db: DBSession = Depends(get_db)
):
    from fastapi.responses import StreamingResponse
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required for streaming."
        )
        
    user = get_user_from_token(token, db)
    
    # Retrieve the session
    session = db.query(Session).filter(Session.id == session_id).first()
    video_path = None

    if not session:
        # Check document sessions
        doc_session = db.query(DocumentSession).filter(DocumentSession.id == session_id).first()
        if not doc_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        # Verify ownership
        if doc_session.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session's video"
            )
        if doc_session.video_url:
            rel_path = doc_session.video_url.replace("/uploads/", "")
            video_path = os.path.join(settings.UPLOAD_DIR, rel_path)
    else:
        # Verify ownership
        if session.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session's video"
            )
        # Check if recording exists
        recording = db.query(SessionRecording).filter(SessionRecording.session_id == session_id).first()
        if recording and recording.video_path and os.path.exists(recording.video_path):
            video_path = recording.video_path
        elif session.video_url:
            rel_path = session.video_url.replace("/uploads/", "")
            video_path = os.path.join(settings.UPLOAD_DIR, rel_path)

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording video file not found."
        )
        
    file_path = video_path
    file_size = os.path.getsize(file_path)
    
    # Parse range header: e.g. "bytes=0-1023"
    start = 0
    end = file_size - 1
    
    if range:
        try:
            range_type, range_val = range.strip().split("=")
            if range_type == "bytes":
                ranges = range_val.split("-")
                if ranges[0]:
                    start = int(ranges[0])
                if len(ranges) > 1 and ranges[1]:
                    end = int(ranges[1])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Range header format."
            )
            
    # clamp values
    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=f"Requested range not satisfiable. File size: {file_size}"
        )
        
    chunk_size = end - start + 1
    
    def file_iterator():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(remaining, 1024 * 64))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
 
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "video/webm"
        
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": mime_type,
    }
    
    return StreamingResponse(
        file_iterator(),
        status_code=206,
        headers=headers
    )
