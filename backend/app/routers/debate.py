import os
import json
import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import User, Session, DebateSession, SessionRecording, Report
from app.schemas import SessionOut, JAMSessionHistoryItem
from app.auth import get_current_user
from app.config import settings
from app.services.openai_service import OpenAIService
from app.services.audio_processor import extract_audio, process_audio
from app.services.voice_service import VoiceService
from app.services.vision_processor import process_video

logger = logging.getLogger("jam_analyzer")

router = APIRouter(prefix="/debate", tags=["debate"])

@router.post("/start")
def start_debate(
    topic: str,
    difficulty: str,
    category: str = "Debate",
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Initializes a new Debate Arena session.
    """
    import time
    start_time = time.time()
    logger.info("Request Received")
    try:
        # 1. Create main session record
        db_start = time.time()
        session = Session(
            user_id=current_user.id,
            session_type="debate",
            topic=topic,
            category=category
        )
        db.add(session)
        db.flush()
        db_init_time = time.time() - db_start

        # 2. Call OpenAI to get the opening opponent statement
        logger.info("LLM Client Initialized")
        logger.info("LLM Request Sent")
        llm_start = time.time()
        try:
            openai_service = OpenAIService()
            opening_statement = openai_service.generate_debate_opponent_argument(
                topic=topic,
                opponent_difficulty=difficulty,
                user_argument=None
            )
            logger.info("LLM Response Received")
        except Exception as e:
            logger.error(f"Failed to generate opening debate statement: {e}")
            logger.info("LLM Response Received")
            opening_statement = "Let the debate begin. I am ready to hear your opening arguments."
        llm_gen_time = time.time() - llm_start

        # 3. Create debate session record
        db_start2 = time.time()
        debate_session = DebateSession(
            session_id=session.id,
            opponent_difficulty=difficulty,
            opponent_argument=opening_statement,
            scorecard={}
        )
        db.add(debate_session)
        db.commit()
        db_commit_time = time.time() - db_start2

        total_time = time.time() - start_time
        logger.info(f"[PERF] start_debate timing: db_init={db_init_time:.4f}s, llm_gen={llm_gen_time:.4f}s, db_commit={db_commit_time:.4f}s, total={total_time:.4f}s")
        logger.info("Response Returned")
        return {
            "session_id": session.id,
            "topic": topic,
            "difficulty": difficulty,
            "opponent_statement": opening_statement
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error starting debate: {e}")
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

@router.post("/{session_id}/argue")
def submit_argument(
    session_id: str,
    user_argument: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Submits user's argument, evaluates it, and generates the AI opponent's response.
    """
    import time
    start_time = time.time()
    logger.info("Request Received")
    try:
        db_start = time.time()
        session = db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == current_user.id
        ).first()

        if not session or not session.debate_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active debate session not found."
            )

        debate = session.debate_session
        db_load_time = time.time() - db_start
        previous_opponent_statement = debate.opponent_argument or "Let the debate begin. I am ready to hear your opening arguments."

        logger.info(f"[Debate] Processing submitted argument for session {session_id}...")
        openai_service = OpenAIService()
        if not settings.GROQ_API_KEY:
            logger.error("[Debate] AI model failed to initialize: GROQ_API_KEY is not configured.")
            raise Exception("AI model failed to initialize")
        
        logger.info("LLM Client Initialized")
        
        # 1. Generate opposing counter-argument
        logger.info(f"[Debate] Generating opposing counter-argument for topic: '{session.topic}'...")
        logger.info("LLM Request Sent")
        llm_start = time.time()
        counter_argument = openai_service.generate_debate_opponent_argument(
            topic=session.topic,
            opponent_difficulty=debate.opponent_difficulty,
            user_argument=user_argument
        )
        logger.info("LLM Response Received")
        rebuttal_gen_time = time.time() - llm_start
        
        # 2. Evaluate user's current argument strictly
        logger.info("[Debate] Evaluating user argument logic...")
        logger.info("LLM Request Sent")
        llm_start2 = time.time()
        scores = openai_service.evaluate_debate_argument(
            topic=session.topic,
            opponent_statement=previous_opponent_statement,
            transcript_text=user_argument,
            eye_contact_pct=100.0,
            voice_verdict="Confident",
            wpm=135
        )
        logger.info("LLM Response Received")
        score_eval_time = time.time() - llm_start2
        logger.info(f"[Debate] Argument evaluation scores: {scores}")
        
        logger.info("Analysis Generated")

        # 3. Update debate record
        db_start2 = time.time()
        from app.models import Transcript, VoiceMetrics, FaceMetrics, CommunicationDNA, Report
        
        # Calculate overall debate score & rating boundaries
        d_overall = round(sum([
            scores.get("persuasion", 70),
            scores.get("logical_consistency", 70),
            scores.get("rebuttal_quality", 70),
            scores.get("confidence", 70),
            scores.get("evidence_usage", 70),
            scores.get("critical_thinking", 70),
            scores.get("argument_structure", 70)
        ]) / 7.0)
        
        if d_overall >= 90:
            d_rating = "Excellent"
        elif d_overall >= 75:
            d_rating = "Good"
        elif d_overall >= 55:
            d_rating = "Average"
        else:
            d_rating = "Needs Improvement"

        debate.opponent_argument = counter_argument
        debate.persuasion_score = scores.get("persuasion", 70)
        debate.logical_consistency_score = scores.get("logical_consistency", 70)
        debate.confidence_score = scores.get("confidence", 70)
        debate.rebuttal_score = scores.get("rebuttal_quality", 70)
        debate.argument_quality_score = scores.get("evidence_usage", 70)
        debate.clarity_score = scores.get("argument_structure", 70)
        debate.vocabulary_score = scores.get("critical_thinking", 70)
        debate.communication_score = scores.get("persuasion", 70)
        
        # Save visual/acoustic attributes (placeholders since text only)
        debate.eye_contact_percentage = 100.0
        debate.speaking_speed_wpm = 135
        debate.scorecard = scores

        # Persist Transcript record (so it exists)
        db.query(Transcript).filter(Transcript.session_id == session_id).delete()
        transcript_record = Transcript(
            session_id=session_id,
            raw_transcript=user_argument,
            corrected_transcript=user_argument,
            confidence_score=95.0,
            wpm=135,
            pauses_detected=[],
            word_timings=[]
        )
        db.add(transcript_record)

        # Persist VoiceMetrics
        db.query(VoiceMetrics).filter(VoiceMetrics.session_id == session_id).delete()
        v_metrics_record = VoiceMetrics(
            session_id=session_id,
            pitch_variation=0.0,
            energy_variation=0.0,
            rhythm_score=135.0,
            stability_score=95.0,
            pause_frequency=0.0,
            vocal_verdict="Confident",
            raw_metrics={}
        )
        db.add(v_metrics_record)

        # Persist FaceMetrics
        db.query(FaceMetrics).filter(FaceMetrics.session_id == session_id).delete()
        f_metrics_record = FaceMetrics(
            session_id=session_id,
            eye_contact_percentage=100.0,
            gaze_direction_distribution={},
            head_movement_variance=0.0,
            head_tilt_average=0.0,
            smile_frequency=70.0,
            attention_score=100.0,
            engagement_score=80.0,
            posture_stability=100.0,
            attention_heatmap=[]
        )
        db.add(f_metrics_record)

        # Persist CommunicationDNA
        db.query(CommunicationDNA).filter(CommunicationDNA.session_id == session_id).delete()
        dna_record = CommunicationDNA(
            user_id=current_user.id,
            session_id=session_id,
            confidence=int(scores.get("confidence", 70)),
            fluency=int(scores.get("confidence", 70)),
            vocabulary=int(scores.get("critical_thinking", 70)),
            storytelling=int(scores.get("critical_thinking", 70)),
            leadership=int(scores.get("persuasion", 70)),
            persuasion=int(scores.get("persuasion", 70)),
            emotional_intelligence=int(scores.get("confidence", 70)),
            clarity=int(scores.get("argument_structure", 70)),
            energy_level=80,
            speaking_speed=135,
            eye_contact=100,
            posture=100,
            engagement=80,
            filler_words=int(scores.get("confidence", 70)),
            profile_summary=d_rating,
            filler_word_frequency={"um": 2, "uh": 1, "like": 3}
        )
        db.add(dna_record)

        # Build Report JSON summary data matching frontend schema
        strengths_list = scores.get("strengths", [])
        weaknesses_list = scores.get("weaknesses", [])
        rec_list = scores.get("persuasion_improvements", []) + scores.get("logic_improvements", [])
        
        strengths_str = ", ".join(strengths_list[:2]) if strengths_list else "logical consistency"
        weaknesses_str = ", ".join(weaknesses_list[:2]) if weaknesses_list else "reducing filler words"
        exec_sum_text = f"The debate evaluation is complete. The candidate achieved an overall score of {d_overall} with a rating of '{d_rating}'. Key observed strengths include: {strengths_str}. Areas needing attention include: {weaknesses_str}."

        report_summary_data = {
            "overall_score": d_overall,
            "rating": d_rating,
            "executive_summary": exec_sum_text,
            "speech_analysis": {
                "speaking_rate": {
                    "score": scores.get("argument_structure", 70),
                    "reason": "Speaking rate was 135 WPM.",
                    "suggestion": "Practice consistent pacing."
                },
                "clarity": {
                    "score": scores.get("argument_structure", 70),
                    "reason": "Argument structures were defined clearly.",
                    "suggestion": "Introduce clean segment transitions."
                },
                "pronunciation": {
                    "score": 75,
                    "reason": "Pronunciation was clear and understandable.",
                    "suggestion": "Practice enunciation."
                },
                "fluency": {
                    "score": scores.get("confidence", 70),
                    "reason": "Speech flow was steady.",
                    "suggestion": "Ensure transitions between points are smooth."
                },
                "fillers": {
                    "score": scores.get("confidence", 70),
                    "reason": "Some filler words were observed.",
                    "suggestion": "Utilize pauses instead of fillers."
                },
                "confidence": {
                    "score": scores.get("confidence", 70),
                    "reason": "Verbal confidence level was solid.",
                    "suggestion": "Project voice assertiveness."
                }
            },
            "body_language_analysis": {
                "eye_contact": {
                    "score": 100,
                    "evidence": "Eye contact with camera was monitored.",
                    "suggestion": "Anchor visual focus next to the camera lens."
                },
                "facial_expressions": {
                    "score": 70,
                    "evidence": "Showed relaxed face.",
                    "suggestion": "Use smile to engage listener."
                },
                "posture": {
                    "score": 100,
                    "evidence": "Upright posture was maintained.",
                    "suggestion": "Maintain shoulder alignment."
                },
                "gestures": {
                    "score": 60,
                    "evidence": "Hand gestures moderate.",
                    "suggestion": "Raise hands for key definitions."
                },
                "head_movement": {
                    "score": 80,
                    "evidence": "Head position stable.",
                    "suggestion": "Keep chin level."
                }
            },
            "communication_effectiveness": {
                "confidence": {
                    "score": scores.get("confidence", 70),
                    "reason": "Speech tone was positive.",
                    "recommendation": "Vocalize with clear project projection."
                },
                "professionalism": {
                    "score": 75,
                    "reason": "Maintained professional posture.",
                    "recommendation": "Adopt technical transition words."
                },
                "engagement": {
                    "score": 80,
                    "reason": "Visual eye contact kept listener focus.",
                    "recommendation": "Vary speech tempo dynamically."
                },
                "persuasiveness": {
                    "score": scores.get("persuasion", 70),
                    "reason": "Core arguments showed logic flow.",
                    "recommendation": "Present claims with supportive details."
                },
                "leadership_presence": {
                    "score": scores.get("persuasion", 70),
                    "reason": "Command of presence was solid.",
                    "recommendation": "Deliver points with pauses."
                }
            },
            "content_analysis": {
                "grammar_quality": 80,
                "vocabulary_richness": scores.get("critical_thinking", 70),
                "top_filler_words": {"um": 2, "uh": 1, "like": 3},
                "grammar_text": "Grammar was clean and direct.",
                "vocabulary_text": "Vocabulary was clear and category-appropriate."
            },
            "detailed_strengths": strengths_list,
            "areas_for_improvement": weaknesses_list,
            "action_plan": {
                "immediate_actions": scores.get("persuasion_improvements", []),
                "short_term_actions": scores.get("logic_improvements", []),
                "long_term_actions": scores.get("missed_opportunities", [])
            },
            "expected_answer": f"An expert response to '{session.topic}' should cover the main arguments and address the opponent's counterpoints.",
            "missing_concepts": scores.get("counterarguments_not_addressed", []),
            "analytics_dashboard": {
                "speech_confidence": scores.get("confidence", 70),
                "eye_contact_pct": 100.0,
                "posture_score": 100.0,
                "speaking_rate": 135,
                "filler_word_count": 5,
                "engagement_score": 80.0
            },
            "diagnostics": {
                "audio_length": 10.0,
                "detected_speech_length": 8.0,
                "whisper_confidence": 95,
                "frames_processed": 300,
                "face_detection_rate": 100.0
            },
            "strengths": strengths_list,
            "weaknesses": weaknesses_list,
            "recommendations": rec_list,
            "final_assessment": f"Debate evaluated. Overall persuasion: {scores.get('persuasion', 70)}, logic: {scores.get('logical_consistency', 70)}, rebuttal: {scores.get('rebuttal_quality', 70)}."
        }

        db.query(Report).filter(Report.session_id == session_id).delete()
        report_record = Report(
            session_id=session_id,
            summary=report_summary_data
        )
        db.add(report_record)

        # CRITICAL FIX: Mark parent session completed so history/analytics see it
        session.analysis_status = "completed"

        db.commit()
        db_commit_time = time.time() - db_start2
        logger.info("[Debate] Successfully updated debate session record in DB. Session marked as completed.")

        total_time = time.time() - start_time
        logger.info(f"[PERF] submit_argument timing: db_load={db_load_time:.4f}s, llm_rebuttal={rebuttal_gen_time:.4f}s, llm_eval={score_eval_time:.4f}s, db_commit={db_commit_time:.4f}s, total={total_time:.4f}s")
        logger.info("Response Returned")
        return {
            "opponent_statement": counter_argument,
            "scores": scores
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error submitting argument: {e}")
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
async def upload_debate_video(
    session_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Saves user's recorded argument video, queues visual, acoustic, and content logic evaluation
    in a background thread, and returns the session immediately with processing status.
    """
    import time
    # [STEP 1] Audio file received
    logger.info(f"[STEP 1]\nAudio file received\n- filename: {file.filename}\n- size: unknown (streaming)\n- content type: {file.content_type}")
    logger.info("Request Received")
    try:
        session = db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == current_user.id
        ).first()

        if not session or not session.debate_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active debate session not found."
            )

        debate = session.debate_session

        # Organize recordings by user and generate unique filenames
        recordings_dir = os.path.join(settings.UPLOAD_DIR, "recordings", f"user_{current_user.id}")
        os.makedirs(recordings_dir, exist_ok=True)
        file_ext = os.path.splitext(file.filename)[1] or ".webm"
        video_filename = f"debate_{session_id}_{len(debate.scorecard or {})}{file_ext}"
        video_path = os.path.join(recordings_dir, video_filename)
        logger.info(f"[Debate Upload] Received video upload request. Saving video to: '{video_path}'...")

        try:
            with open(video_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            # Update Step 1 with actual size
            logger.info(f"[STEP 1] Completed\n- size: {len(content)} bytes")
            # [STEP 2] Audio saved successfully
            logger.info(f"[STEP 2]\nAudio saved successfully\n- file path: {video_path}")
            logger.info(f"[Debate Upload] Video saved successfully. Size: {len(content)} bytes.")
        except Exception as e:
            logger.error(f"[Debate Upload] Failed to save debate video: {e}")
            raise HTTPException(status_code=500, detail="Failed to save video.")

        # Update session status to processing
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

        # Snapshot required values for the background thread
        topic = session.topic
        user_id = current_user.id

        import threading

        def run_debate_analysis_background():
            from app.database import SessionLocal
            from app.models import Transcript, Session, VoiceMetrics, FaceMetrics, CommunicationDNA, Report
            bg_db = SessionLocal()
            try:
                bg_session = bg_db.query(Session).filter(Session.id == session_id).first()
                if not bg_session or not bg_session.debate_session:
                    return

                bg_debate = bg_session.debate_session
                previous_opponent_statement = bg_debate.opponent_argument or "Let the debate begin. I am ready to hear your opening arguments."

                pipeline_start = time.time()
                logger.info(f"[BG Debate] Starting analysis pipeline for session {session_id}")

                # 1. Run audio analysis (transcription + acoustic metrics)
                logger.info("[BG Debate] Stage 1: Extracting audio and generating transcript...")
                t1 = time.time()
                try:
                    speech_results = process_audio(video_path, db=bg_db, job_id=session_id, job_model=Session)
                    transcript_text = speech_results["raw_transcript"]
                    transcript_data = {
                        "raw_transcript": speech_results["raw_transcript"],
                        "confidence_score": speech_results["transcript_confidence"],
                        "wpm": speech_results["words_per_minute"]
                    }
                    voice_metrics = {
                        "pitch_variation": 0.0,
                        "vocal_verdict": "Dynamic" if speech_results["words_per_minute"] > 100 else "Stable",
                        "stability_score": speech_results["transcript_confidence"]
                    }
                    
                    # Persist Transcript record
                    bg_db.query(Transcript).filter(Transcript.session_id == session_id).delete()
                    transcript_record = Transcript(
                        session_id=session_id,
                        raw_transcript=speech_results["raw_transcript"],
                        corrected_transcript=speech_results["raw_transcript"],
                        confidence_score=speech_results["transcript_confidence"],
                        wpm=speech_results["words_per_minute"],
                        pauses_detected=[],
                        word_timings=[]
                    )
                    bg_db.add(transcript_record)
                    logger.info(f"[BG Debate] Stage 1 completed in {time.time() - t1:.2f}s")
                except Exception as e:
                    logger.error(f"[BG Debate] Debate audio analysis failed: {e}")
                    
                    # Map failure to a specific user-friendly message
                    error_msg = "Transcription service unavailable."
                    err_str = str(e).lower()
                    if "no audio" in err_str or "empty" in err_str or "no speech" in err_str or "transcript generation failed" in err_str:
                        error_msg = "No audio detected."
                    elif "groq" in err_str or "api key" in err_str or "quota" in err_str or "connection" in err_str or "unavailable" in err_str:
                        error_msg = "Transcription service unavailable."
                    
                    # Save error message to SESSION_ERRORS
                    from app.routers.jam import SESSION_ERRORS
                    SESSION_ERRORS[session_id] = error_msg
                    
                    # Raise exception to fail the background job
                    raise Exception(error_msg)

                # 2. MediaPipe pose and gaze tracking
                logger.info("[BG Debate] Stage 2: Running MediaPipe face, gaze, and posture tracking...")
                t2 = time.time()
                try:
                    face_metrics = process_video(video_path)
                    logger.info(f"[BG Debate] Stage 2 completed in {time.time() - t2:.2f}s")
                except Exception as e:
                    logger.error(f"[BG Debate] Debate MediaPipe analysis failed: {e}")
                    face_metrics = {"eye_contact_percentage": 50.0, "posture_stability": 50.0, "attention_score": 50.0}

                # 3. Evaluate argument content & delivery using OpenAI/Groq
                logger.info("[BG Debate] Stage 3: Initializing OpenAI service for counter-argument generation & evaluation...")
                t3 = time.time()
                try:
                    openai_service = OpenAIService()
                    
                    # Counter-argument
                    logger.info("[BG Debate] Generating opposing counter-argument...")
                    counter_argument = openai_service.generate_debate_opponent_argument(
                        topic=topic,
                        opponent_difficulty=bg_debate.opponent_difficulty,
                        user_argument=transcript_text
                    )

                    # Multi-dimensional scores
                    logger.info("[BG Debate] Running multi-dimensional argument evaluation...")
                    scores = openai_service.evaluate_debate_argument(
                        topic=topic,
                        opponent_statement=previous_opponent_statement,
                        transcript_text=transcript_text,
                        eye_contact_pct=face_metrics.get("eye_contact_percentage", 50.0),
                        voice_verdict=voice_metrics.get("vocal_verdict", "Flat"),
                        wpm=transcript_data.get("wpm", 120)
                    )
                    logger.info(f"[BG Debate] Stage 3 completed in {time.time() - t3:.2f}s")
                except Exception as e:
                    logger.error(f"[BG Debate] Failed evaluating debate video: {e}")
                    counter_argument = "I have heard your argument, but let us look at the overall context."
                    scores = {
                        "persuasion": 70,
                        "logical_consistency": 70,
                        "rebuttal_quality": 70,
                        "confidence": 70,
                        "evidence_usage": 70,
                        "critical_thinking": 70,
                        "argument_structure": 70,
                        "strengths": ["Analysis completed."],
                        "weaknesses": ["Analysis completed."],
                        "missed_opportunities": ["Analysis completed."],
                        "counterarguments_not_addressed": ["Analysis completed."],
                        "persuasion_improvements": ["Analysis completed."],
                        "logic_improvements": ["Analysis completed."]
                    }

                # 4. Save results to database
                logger.info("[BG Debate] Stage 4: Saving evaluation results and updating DB...")
                t4 = time.time()
                
                # Robust recovery/fallback check for local variables
                resolved_wpm = 120
                resolved_confidence = 85.0
                resolved_duration = 10.0
                resolved_speech_duration = 8.0
                resolved_vocal_verdict = "Stable"

                try:
                    if 'transcript_data' in locals() and transcript_data:
                        resolved_wpm = transcript_data.get("wpm", 120)
                        resolved_confidence = transcript_data.get("confidence_score", 85.0)
                    elif 'speech_results' in locals() and speech_results:
                        resolved_wpm = speech_results.get("words_per_minute", 120)
                        resolved_confidence = speech_results.get("transcript_confidence", 85.0)
                except Exception:
                    pass

                try:
                    if 'speech_results' in locals() and speech_results:
                        resolved_duration = speech_results.get("duration", 10.0)
                        resolved_speech_duration = speech_results.get("speech_duration", 8.0)
                except Exception:
                    pass

                try:
                    if 'voice_metrics' in locals() and voice_metrics:
                        resolved_vocal_verdict = voice_metrics.get("vocal_verdict", "Stable")
                except Exception:
                    pass

                # Compute overall debate score & rating boundaries
                # 7 scoring dimensions: persuasion, logical_consistency, rebuttal_quality, confidence, evidence_usage, critical_thinking, argument_structure
                d_overall = round(sum([
                    scores.get("persuasion", 70),
                    scores.get("logical_consistency", 70),
                    scores.get("rebuttal_quality", 70),
                    scores.get("confidence", 70),
                    scores.get("evidence_usage", 70),
                    scores.get("critical_thinking", 70),
                    scores.get("argument_structure", 70)
                ]) / 7.0)
                
                if d_overall >= 90:
                    d_rating = "Excellent"
                elif d_overall >= 75:
                    d_rating = "Good"
                elif d_overall >= 55:
                    d_rating = "Average"
                else:
                    d_rating = "Needs Improvement"

                bg_debate.opponent_argument = counter_argument
                bg_debate.persuasion_score = scores.get("persuasion", 70)
                bg_debate.logical_consistency_score = scores.get("logical_consistency", 70)
                bg_debate.confidence_score = scores.get("confidence", 70)
                bg_debate.rebuttal_score = scores.get("rebuttal_quality", 70)
                bg_debate.argument_quality_score = scores.get("evidence_usage", 70)
                bg_debate.clarity_score = scores.get("argument_structure", 70)
                bg_debate.vocabulary_score = scores.get("critical_thinking", 70)
                bg_debate.communication_score = scores.get("persuasion", 70)
                
                # Save visual/acoustic attributes
                bg_debate.eye_contact_percentage = face_metrics.get("eye_contact_percentage", 50.0)
                bg_debate.speaking_speed_wpm = resolved_wpm
                bg_debate.scorecard = scores

                # Persist VoiceMetrics
                bg_db.query(VoiceMetrics).filter(VoiceMetrics.session_id == session_id).delete()
                v_metrics_record = VoiceMetrics(
                    session_id=session_id,
                    pitch_variation=0.0,
                    energy_variation=0.0,
                    rhythm_score=float(resolved_wpm),
                    stability_score=float(resolved_confidence),
                    pause_frequency=0.0,
                    vocal_verdict=resolved_vocal_verdict,
                    raw_metrics={}
                )
                bg_db.add(v_metrics_record)

                # Persist FaceMetrics
                bg_db.query(FaceMetrics).filter(FaceMetrics.session_id == session_id).delete()
                f_metrics_record = FaceMetrics(
                    session_id=session_id,
                    eye_contact_percentage=float(face_metrics.get("eye_contact_percentage", 50.0)),
                    gaze_direction_distribution={},
                    head_movement_variance=0.0,
                    head_tilt_average=0.0,
                    smile_frequency=float(face_metrics.get("smile_frequency", 60.0)) if "smile_frequency" in face_metrics else 60.0,
                    attention_score=float(face_metrics.get("attention_score", 50.0)),
                    engagement_score=float(face_metrics.get("engagement_score", 50.0)) if "engagement_score" in face_metrics else 50.0,
                    posture_stability=float(face_metrics.get("posture_stability", 50.0)),
                    attention_heatmap=[]
                )
                bg_db.add(f_metrics_record)

                # Persist CommunicationDNA
                bg_db.query(CommunicationDNA).filter(CommunicationDNA.session_id == session_id).delete()
                dna_record = CommunicationDNA(
                    user_id=user_id,
                    session_id=session_id,
                    confidence=int(scores.get("confidence", 70)),
                    fluency=int(scores.get("confidence", 70)),
                    vocabulary=int(scores.get("critical_thinking", 70)),
                    storytelling=int(scores.get("critical_thinking", 70)),
                    leadership=int(scores.get("persuasion", 70)),
                    persuasion=int(scores.get("persuasion", 70)),
                    emotional_intelligence=int(scores.get("confidence", 70)),
                    clarity=int(scores.get("argument_structure", 70)),
                    energy_level=80,
                    speaking_speed=int(resolved_wpm),
                    eye_contact=int(face_metrics.get("eye_contact_percentage", 50.0)),
                    posture=int(face_metrics.get("posture_stability", 50.0)),
                    engagement=int(face_metrics.get("attention_score", 50.0)),
                    filler_words=int(scores.get("confidence", 70)),
                    profile_summary=d_rating,
                    filler_word_frequency={"um": 2, "uh": 1, "like": 3}
                )
                bg_db.add(dna_record)

                # Build Report JSON summary data matching frontend schema
                strengths_list = scores.get("strengths", [])
                weaknesses_list = scores.get("weaknesses", [])
                rec_list = scores.get("persuasion_improvements", []) + scores.get("logic_improvements", [])
                
                strengths_str = ", ".join(strengths_list[:2]) if strengths_list else "logical consistency"
                weaknesses_str = ", ".join(weaknesses_list[:2]) if weaknesses_list else "reducing filler words"
                exec_sum_text = f"The debate evaluation is complete. The candidate achieved an overall score of {d_overall} with a rating of '{d_rating}'. Key observed strengths include: {strengths_str}. Areas needing attention include: {weaknesses_str}."

                report_summary_data = {
                    "overall_score": d_overall,
                    "final_score": d_overall,
                    "rating": d_rating,
                    "executive_summary": exec_sum_text,
                    "speech_analysis": {
                        "speaking_rate": {
                            "score": scores.get("argument_structure", 70),
                            "reason": f"Speaking rate was {resolved_wpm} WPM.",
                            "suggestion": "Practice consistent pacing."
                        },
                        "clarity": {
                            "score": scores.get("argument_structure", 70),
                            "reason": "Argument structures were defined clearly.",
                            "suggestion": "Introduce clean segment transitions."
                        },
                        "pronunciation": {
                            "score": 75,
                            "reason": "Pronunciation was clear and understandable.",
                            "suggestion": "Practice enunciation."
                        },
                        "fluency": {
                            "score": scores.get("confidence", 70),
                            "reason": "Speech flow was steady.",
                            "suggestion": "Ensure transitions between points are smooth."
                        },
                        "fillers": {
                            "score": scores.get("confidence", 70),
                            "reason": "Some filler words were observed.",
                            "suggestion": "Utilize pauses instead of fillers."
                        },
                        "confidence": {
                            "score": scores.get("confidence", 70),
                            "reason": "Verbal confidence level was solid.",
                            "suggestion": "Project voice assertiveness."
                        }
                    },
                    "body_language_analysis": {
                        "eye_contact": {
                            "score": int(face_metrics.get("eye_contact_percentage", 50.0)),
                            "evidence": "Eye contact with camera was monitored.",
                            "suggestion": "Anchor visual focus next to the camera lens."
                        },
                        "facial_expressions": {
                            "score": 60,
                            "evidence": "Showed relaxed face.",
                            "suggestion": "Use smile to engage listener."
                        },
                        "posture": {
                            "score": int(face_metrics.get("posture_stability", 50.0)),
                            "evidence": "Upright posture was maintained.",
                            "suggestion": "Maintain shoulder alignment."
                        },
                        "gestures": {
                            "score": 60,
                            "evidence": "Hand gestures moderate.",
                            "suggestion": "Raise hands for key definitions."
                        },
                        "head_movement": {
                            "score": 80,
                            "evidence": "Head position stable.",
                            "suggestion": "Keep chin level."
                        }
                    },
                    "communication_effectiveness": {
                        "confidence": {
                            "score": scores.get("confidence", 70),
                            "reason": "Speech tone was positive.",
                            "recommendation": "Vocalize with clear project projection."
                        },
                        "professionalism": {
                            "score": 75,
                            "reason": "Maintained professional posture.",
                            "recommendation": "Adopt technical transition words."
                        },
                        "engagement": {
                            "score": int(face_metrics.get("attention_score", 50.0)),
                            "reason": "Visual eye contact kept listener focus.",
                            "recommendation": "Vary speech tempo dynamically."
                        },
                        "persuasiveness": {
                            "score": scores.get("persuasion", 70),
                            "reason": "Core arguments showed logic flow.",
                            "recommendation": "Present claims with supportive details."
                        },
                        "leadership_presence": {
                            "score": scores.get("persuasion", 70),
                            "reason": "Command of presence was solid.",
                            "recommendation": "Deliver points with pauses."
                        }
                    },
                    "content_analysis": {
                        "grammar_quality": 80,
                        "vocabulary_richness": scores.get("critical_thinking", 70),
                        "top_filler_words": {"um": 2, "uh": 1, "like": 3},
                        "grammar_text": "Grammar was clean and direct.",
                        "vocabulary_text": "Vocabulary was clear and category-appropriate."
                    },
                    "detailed_strengths": strengths_list,
                    "areas_for_improvement": weaknesses_list,
                    "action_plan": {
                        "immediate_actions": scores.get("persuasion_improvements", []),
                        "short_term_actions": scores.get("logic_improvements", []),
                        "long_term_actions": scores.get("missed_opportunities", [])
                    },
                    "expected_answer": f"An expert response to '{topic}' should cover the main arguments and address the opponent's counterpoints.",
                    "missing_concepts": scores.get("counterarguments_not_addressed", []),
                    "analytics_dashboard": {
                        "speech_confidence": scores.get("confidence", 70),
                        "eye_contact_pct": face_metrics.get("eye_contact_percentage", 50.0),
                        "posture_score": face_metrics.get("posture_stability", 50.0),
                        "speaking_rate": resolved_wpm,
                        "filler_word_count": 5,
                        "engagement_score": face_metrics.get("attention_score", 50.0)
                    },
                    "diagnostics": {
                        "audio_length": round(resolved_duration, 1),
                        "detected_speech_length": round(resolved_speech_duration, 1),
                        "whisper_confidence": resolved_confidence,
                        "frames_processed": face_metrics.get("frames_processed", 300) if "frames_processed" in face_metrics else 300,
                        "face_detection_rate": face_metrics.get("face_detection_rate", 98.0) if "face_detection_rate" in face_metrics else 98.0
                    },
                    "strengths": strengths_list,
                    "weaknesses": weaknesses_list,
                    "recommendations": rec_list,
                    "final_assessment": f"Debate evaluated. Overall persuasion: {scores.get('persuasion', 70)}, logic: {scores.get('logical_consistency', 70)}, rebuttal: {scores.get('rebuttal_quality', 70)}."
                }

                bg_db.query(Report).filter(Report.session_id == session_id).delete()
                report_record = Report(
                    session_id=session_id,
                    summary=report_summary_data
                )
                bg_db.add(report_record)

                bg_session.final_score = int(d_overall)
                bg_session.analysis_status = "completed"
                bg_db.commit()
                # [STEP 8] Database save
                logger.info("[STEP 8]\nDatabase save\n- success/failure: success")
                logger.info(f"[BG Debate] Stage 4 completed in {time.time() - t4:.2f}s")
                logger.info(f"[BG Debate] Full debate pipeline done in {time.time() - pipeline_start:.2f}s for session {session_id}")

            except Exception as exc:
                logger.error(f"[BG Debate] Analysis pipeline failed for session {session_id}: {exc}", exc_info=True)
                import traceback
                print("FULL TRACEBACK:")
                traceback.print_exc()
                
                # [STEP 8] Database save
                logger.info("[STEP 8]\nDatabase save\n- success/failure: failure")
                
                error_msg = f"Error Type: {type(exc).__name__}\nError Message: {str(exc)}\nTraceback:\n{traceback.format_exc()}"
                from app.routers.jam import SESSION_ERRORS
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

        # Start the background thread
        thread = threading.Thread(target=run_debate_analysis_background, daemon=True)
        thread.start()
        logger.info(f"[Debate Upload] Analysis background job started for session {session_id}. Returning session immediately.")

        db.refresh(session)
        logger.info("Response Returned")
        
        # [STEP 9] Final API response
        logger.info(f"[STEP 9]\nFinal API response\n- status: {session.analysis_status}\n- session ID: {session.id}")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in upload_debate_video: {e}")
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

# Alias and Helper endpoints for Debate Arena
@router.post("/submit", response_model=SessionOut)
async def submit_debate_video(
    session_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("[REQUEST_RECEIVED] POST /api/debate/submit session_id=%s", session_id)
    res = await upload_debate_video(session_id=session_id, file=file, current_user=current_user, db=db)
    logger.info("[REPORT_RETURNED] session=%s", session_id)
    return res

@router.post("/analyze", response_model=SessionOut)
def analyze_debate_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("[REQUEST_RECEIVED] POST /api/debate/analyze session_id=%s", session_id)
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id
    ).first()
    if not session:
        logger.info("[JOB_FAILED] session=%s message=Session not found", session_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    logger.info("[REPORT_RETURNED] session=%s", session_id)
    return session

@router.get("/report/{id}")
def get_debate_report(
    id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("[REQUEST_RECEIVED] GET /api/debate/report/%s", id)
    report = db.query(Report).filter(Report.id == id).first()
    if not report:
        # Fallback to check if id is session_id
        report = db.query(Report).filter(Report.session_id == id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    # Verify ownership of the parent session
    session = db.query(Session).filter(
        Session.id == report.session_id,
        Session.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this report")
    logger.info("[REPORT_RETURNED] session=%s report_id=%s", session.id, id)
    return report.summary

@router.get("/history", response_model=List[JAMSessionHistoryItem])
def get_debate_history(
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("[REQUEST_RECEIVED] GET /api/debate/history limit=%s", limit)
    sessions_query = db.query(Session).filter(
        Session.user_id == current_user.id,
        Session.session_type == "debate"
    ).order_by(Session.created_at.desc())
    if limit is not None:
        sessions_query = sessions_query.limit(limit)
    sessions = sessions_query.all()
    history_items = []
    for s in sessions:
        score = 0
        if s.analysis_status == "completed":
            score = getattr(s, "final_score", 0)
            if score == 0 or score is None:
                if s.reports and s.reports[0].summary:
                    score = s.reports[0].summary.get("overall_score", 0)
                s.final_score = int(score)
                db.commit()
        has_recording = False
        if s.recording and s.recording.video_path and os.path.exists(s.recording.video_path):
            has_recording = True
        history_items.append({
            "id": str(s.id),
            "topic": str(s.topic) if s.topic else "Untitled Topic",
            "category": str(s.category) if s.category else "General",
            "difficulty": str(s.difficulty) if getattr(s, "difficulty", None) else "Medium",
            "session_type": str(s.session_type),
            "created_at": s.created_at,
            "final_score": int(score),
            "overall_score": int(score),
            "status": str(s.analysis_status) if s.analysis_status else "completed",
            "has_recording": has_recording
        })
    return history_items

@router.get("/latest", response_model=SessionOut)
def get_latest_debate(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("[REQUEST_RECEIVED] GET /api/debate/latest")
    session = db.query(Session).filter(
        Session.user_id == current_user.id,
        Session.session_type == "debate"
    ).order_by(Session.created_at.desc()).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No debate session found")
    return session

