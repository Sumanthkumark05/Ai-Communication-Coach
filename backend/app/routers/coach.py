import logging
import time
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session as DBSession

from app.database import get_db, SessionLocal
from app.models import User, CommunicationDNA, CoachRecommendation, ChallengeHistory, GrowthMetrics, Session, Transcript, BackgroundJob
from app.schemas import CommunicationDNASchema, ChallengeOut
from app.auth import get_current_user
from app.services.groq_service import GroqService

logger = logging.getLogger("jam_analyzer")

router = APIRouter(prefix="/coach", tags=["coach"])
api_router = APIRouter(tags=["coach"])

# ---------------------------------------------------------------------------
# DB-backed job helpers — replaces the ephemeral COACH_JOBS in-memory dict
# ---------------------------------------------------------------------------

def _db_create_job(user_id: str, job_id: str) -> None:
    """Insert a new pending job row into background_jobs."""
    db = SessionLocal()
    try:
        job = BackgroundJob(
            id=job_id,
            user_id=user_id,
            job_type="coach_recommendations",
            status="pending",
            progress=0,
            message="Queueing recommendations background job...",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
    finally:
        db.close()


def _db_update_job(job_id: str, **kwargs) -> None:
    """Patch fields on an existing job row."""
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _db_get_job(job_id: str) -> Optional[BackgroundJob]:
    """Return a BackgroundJob row or None."""
    db = SessionLocal()
    try:
        return db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    finally:
        db.close()


def _db_find_active_job(user_id: str) -> Optional[str]:
    """Return the ID of an in-flight job for this user, or None."""
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(
            BackgroundJob.user_id == user_id,
            BackgroundJob.job_type == "coach_recommendations",
            BackgroundJob.status.in_(["pending", "processing"]),
        ).order_by(BackgroundJob.created_at.desc()).first()
        return job.id if job else None
    finally:
        db.close()


@router.get("/dna", response_model=CommunicationDNASchema)
def get_current_dna(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Retrieves the user's latest aggregated Communication DNA profile.
    """
    logger.info("Request Received")
    try:
        dna = db.query(CommunicationDNA).filter(
            CommunicationDNA.user_id == current_user.id
        ).order_by(CommunicationDNA.created_at.desc()).first()
        
        if not dna:
            # Return base placeholder DNA
            res = {
                "confidence": 50,
                "fluency": 50,
                "vocabulary": 50,
                "storytelling": 50,
                "leadership": 50,
                "persuasion": 50,
                "emotional_intelligence": 50,
                "clarity": 50,
                "energy_level": 50,
                "speaking_speed": 50,
                "eye_contact": 50,
                "posture": 50,
                "engagement": 50,
                "filler_words": 50,
                "profile_summary": "Unclassified Twin",
                "filler_word_frequency": {},
                "subject_expertise": 50,
                "technical_communication": 50,
                "explanation_skill": 50,
                "knowledge_retention": 50,
                "teaching_ability": 50,
                "technical_communication_skill": 50,
                "presentation_skill": 50,
                "subject_knowledge": 50,
                "explanation_ability": 50,
                "communication_confidence": 50
            }
            logger.info("Response Returned")
            return res
            
        logger.info("Response Returned")
        return dna
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_current_dna: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )

async def run_recommendations_generation_job(user_id: str, job_id: str):
    """
    Asynchronous background task to generate recommendations.
    Writes all state to the `background_jobs` table so it survives restarts.
    """
    start_time = time.time()
    logger.info("Starting recommendation generation")
    _db_update_job(job_id, status="processing", progress=10, message="Fetching user session history from database...")

    db_load_start = time.time()
    def load_data():
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            sessions = db.query(Session).filter(
                Session.user_id == user_id,
                Session.analysis_status == "completed"
            ).order_by(Session.created_at.desc()).all()
            
            user_name = user.name if user else ""
            user_email = user.email if user else ""
            
            history_text = ""
            for idx, s in enumerate(sessions[:5]):
                transcript_text = s.transcript.corrected_transcript if s.transcript else "No transcript available."
                dna_info = ""
                if s.dna:
                    dna_info = (
                        f"Scores - Confidence: {s.dna.confidence}, Fluency: {s.dna.fluency}, "
                        f"Vocabulary: {s.dna.vocabulary}, Storytelling: {s.dna.storytelling}, "
                        f"Leadership: {s.dna.leadership}, Persuasion: {s.dna.persuasion}, "
                        f"Clarity: {s.dna.clarity}, Eye Contact: {s.dna.eye_contact}, Posture: {s.dna.posture}."
                    )
                history_text += f"\nSession {idx+1}: Topic: '{s.topic}' (Category: {s.category}, Type: {s.session_type})\nTranscript: \"{transcript_text}\"\n{dna_info}\n"
            
            return user_name, user_email, len(sessions), history_text, bool(sessions)
        finally:
            db.close()

    try:
        user_name, user_email, total_sessions, history_text, has_sessions = await asyncio.to_thread(load_data)
        db_load_time = time.time() - db_load_start
        logger.info(f"[PERF] Database queries execution time: {db_load_time:.4f}s")
        
        _db_update_job(job_id, progress=30, message="Preparing speaking habit profile...")

        if not has_sessions:
            logger.info("[AI Coach] User has no completed sessions. Returning onboarding fallback.")
            fallback_res = {
                "executive_summary": "Welcome to Twin AI! Complete your first JAM Analyzer or Document presentation to generate active coaching insights and personalized metrics.",
                "strengths": ["Eager to practice", "Ready to learn"],
                "weaknesses": ["No sessions recorded yet"],
                "recommendations": ["Record your first JAM session or Document-based viva response to evaluate your speaking Twin."],
                "immediate_actions": ["Navigate to JAM Analyzer and speak on a Technology or Education topic."],
                "short_term_plan": ["Complete 3 sessions in your first week to build a communication profile."],
                "long_term_plan": ["Consistently reduce filler words and keep eye contact above 80%."],
                "coaching_feedback": "Record your voice and camera streams so the Twin AI Coach can evaluate your pace, posture, and vocabulary usage."
            }
            
            def init_default_challenges():
                db = SessionLocal()
                try:
                    existing_challenges = db.query(ChallengeHistory).filter(ChallengeHistory.user_id == user_id).all()
                    if not existing_challenges:
                        default_challenges = [
                            ("vocabulary", "Explain how a refrigerator works using simple, non-technical words. Keep it highly fluent and engaging."),
                            ("confidence", "Defend an unpopular opinion (e.g. 'Social media should be blocked on weekends') without using any filler vocalizations."),
                            ("storytelling", "Narrate your favorite childhood memory in exactly 2 minutes, using sensory descriptions and structural resolution.")
                        ]
                        for ch_type, prompt_text in default_challenges:
                            db_challenge = ChallengeHistory(
                                user_id=user_id,
                                challenge_type=ch_type,
                                prompt=prompt_text
                            )
                            db.add(db_challenge)
                        db.commit()
                finally:
                    db.close()

            db_save_start = time.time()
            await asyncio.to_thread(init_default_challenges)
            db_save_time = time.time() - db_save_start
            
            total_db_time = db_load_time + db_save_time
            total_execution = time.time() - start_time
            
            # Log all performance metrics
            logger.info(f"[PERF] Database queries: {total_db_time:.4f}s")
            logger.info(f"[PERF] External API calls: 0.0000s")
            logger.info(f"[PERF] LLM responses: 0.0000s")
            logger.info(f"[PERF] Embedding generation: 0.0000s")
            logger.info(f"[PERF] Vector search: 0.0000s")
            logger.info(f"[PERF] Recommendation generation: {total_execution:.4f}s")
            logger.info(f"[PERF] Total endpoint execution: {total_execution:.4f}s")

            _db_update_job(job_id, progress=100, status="completed", result=fallback_res, message="Onboarding recommendations generated.")
            return

        _db_update_job(job_id, progress=40, message="Constructing analysis coach prompt...")

        prompt = f"""
        You are the Twin AI Communications Coach. Analyze the user's communication history and generate personalized coaching feedback, suggestions, action plans, and practice challenges.

        USER PROFILE:
        Name: {user_name}
        Email: {user_email}
        Total Completed Sessions: {total_sessions}

        SESSION HISTORY DATA:
        {history_text}
        
        Analyze the patterns across these sessions to extract their strengths, persistent weaknesses, and actionable recommendations.
        
        You must output your response as a valid JSON object matching this EXACT key schema:
        {{
          "executive_summary": "a narrative summary of the candidate's speaking habits, pacing, and overall progress",
          "strengths": ["list of at least 2 key communication strengths observed"],
          "weaknesses": ["list of at least 2 key communication weaknesses observed"],
          "recommendations": ["list of actionable recommendations, each item must be a short string suggestion"],
          "immediate_actions": ["list of immediate drills or exercises (e.g. within 24 hours)"],
          "short_term_plan": ["list of goals for the next 1-2 weeks"],
          "long_term_plan": ["list of goals for the next 1-2 months"],
          "coaching_feedback": "detailed mentor-style guidance summarizing their path forward"
        }}

        Return ONLY clean, raw JSON matching this schema. Do not enclose the output in markdown code blocks.
        """

        _db_update_job(job_id, progress=60, message="Requesting insights from Groq Coach API...")

        llm_start = time.time()
        groq_service = GroqService()
        
        try:
            async with asyncio.timeout(60):
                parsed_data = await groq_service.call_groq_json_async(
                    prompt=prompt,
                    system_prompt="You are an elite Twin AI speech coach. Return JSON only.",
                    force_schema=False
                )
            llm_time = time.time() - llm_start
            logger.info(f"[PERF] External API calls: {llm_time:.4f}s")
            logger.info(f"[PERF] LLM responses: {llm_time:.4f}s")
            
            required_keys = [
                "executive_summary", "strengths", "weaknesses", "recommendations",
                "immediate_actions", "short_term_plan", "long_term_plan", "coaching_feedback"
            ]
            for k in required_keys:
                if k not in parsed_data or not parsed_data[k]:
                    if isinstance(parsed_data.get(k), list):
                        parsed_data[k] = ["Practice daily speech drills to improve communication dimensions."]
                    else:
                        parsed_data[k] = "No feedback generated. Practice more to analyze trends."
            logger.info("JSON Parsed Successfully")
        except asyncio.TimeoutError:
            llm_time = time.time() - llm_start
            logger.error("LLM Call Timed Out")
            raise HTTPException(
                status_code=504,
                detail="Recommendation generation timed out"
            )
        except Exception as exc:
            llm_time = time.time() - llm_start
            logger.error(f"Failed to generate coaching insights via Groq: {exc}")
            parsed_data = {
                "executive_summary": "Coaching analysis could not be generated. Please try again.",
                "strengths": ["Session completed"],
                "weaknesses": ["Review details in history tab"],
                "recommendations": ["Coaching analysis could not be generated. Please try again."],
                "immediate_actions": ["Coaching analysis could not be generated. Please try again."],
                "short_term_plan": ["Coaching analysis could not be generated. Please try again."],
                "long_term_plan": ["Coaching analysis could not be generated. Please try again."],
                "coaching_feedback": "Coaching analysis could not be generated. Please try again."
            }

        _db_update_job(job_id, progress=80, message="Persisting personalized roadmap to database...")

        db_save_start = time.time()
        def save_roadmap():
            db = SessionLocal()
            try:
                # Populate challenges
                existing_challenges = db.query(ChallengeHistory).filter(ChallengeHistory.user_id == user_id).all()
                if not existing_challenges:
                    for weakness in parsed_data.get("weaknesses", []):
                        w_lower = weakness.lower()
                        if "story" in w_lower or "narrat" in w_lower:
                            ch_type = "storytelling"
                            prompt_text = "Narrate your favorite childhood memory in exactly 2 minutes, using sensory descriptions and structural resolution (STAR method)."
                        elif "confidence" in w_lower or "hesitat" in w_lower or "filler" in w_lower:
                            ch_type = "confidence"
                            prompt_text = "Defend an unpopular opinion (e.g. 'Social media should be blocked on weekends') without using any filler vocalizations."
                        elif "lead" in w_lower or "conflict" in w_lower:
                            ch_type = "leadership"
                            prompt_text = "Lead a mock team meeting addressing a critical bug delay. Convince stakeholders about the recovery plan."
                        elif "persua" in w_lower or "pitch" in w_lower:
                            ch_type = "persuasion"
                            prompt_text = "Convince a customer to buy a generic paperclip for $100. Focus on emotional framing and value propositions."
                        else:
                            ch_type = "vocabulary"
                            prompt_text = "Explain how a refrigerator works using simple, non-technical words. Keep it highly fluent and engaging."
                        
                        db_challenge = ChallengeHistory(
                            user_id=user_id,
                            challenge_type=ch_type,
                            prompt=prompt_text
                        )
                        db.add(db_challenge)
                    
                    if not parsed_data.get("weaknesses"):
                        db_challenge = ChallengeHistory(
                            user_id=user_id,
                            challenge_type="vocabulary",
                            prompt="Explain how a refrigerator works using simple, non-technical words. Keep it highly fluent and engaging."
                        )
                        db.add(db_challenge)
                    db.commit()

                # Populate coach_recommendations
                existing_recs = db.query(CoachRecommendation).filter(CoachRecommendation.user_id == user_id).all()
                if not existing_recs:
                    db_challenges = db.query(ChallengeHistory).filter(ChallengeHistory.user_id == user_id).all()
                    for idx, weakness in enumerate(parsed_data.get("weaknesses", [])):
                        suggestion = parsed_data.get("recommendations", ["Practice daily drills."])[idx] if idx < len(parsed_data.get("recommendations", [])) else "Practice daily drills."
                        matching_ch = next((ch for ch in db_challenges if ch.challenge_type in weakness.lower()), None)
                        challenge_id = matching_ch.id if matching_ch else (db_challenges[0].id if db_challenges else None)
                        
                        coach_rec = CoachRecommendation(
                            user_id=user_id,
                            weakness_identified=weakness,
                            suggestion=suggestion,
                            recommended_challenge_id=challenge_id
                        )
                        db.add(coach_rec)
                    db.commit()
            except Exception as db_exc:
                logger.error(f"[AI Coach] Database persistence failed: {db_exc}")
                db.rollback()
            finally:
                db.close()

        await asyncio.to_thread(save_roadmap)
        db_save_time = time.time() - db_save_start
        
        total_db_time = db_load_time + db_save_time
        total_execution = time.time() - start_time
        
        # Log performance timing summary
        logger.info(f"[PERF] Database queries: {total_db_time:.4f}s")
        logger.info(f"[PERF] External API calls: {llm_time:.4f}s")
        logger.info(f"[PERF] LLM responses: {llm_time:.4f}s")
        logger.info(f"[PERF] Embedding generation: 0.0000s")
        logger.info(f"[PERF] Vector search: 0.0000s")
        logger.info(f"[PERF] Recommendation generation: {total_execution:.4f}s")
        logger.info(f"[PERF] Total endpoint execution: {total_execution:.4f}s")

        _db_update_job(job_id, progress=100, status="completed", result=parsed_data, message="Recommendations generated successfully.")

    except Exception as e:
        logger.exception(f"Error in background task for recommendations: {e}")
        _db_update_job(job_id, status="failed", progress=100, message="Coaching recommendation generation failed.", error=str(e))


@router.get("/recommendations")
async def get_recommendations(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Returns recent AI Coach actionable suggestions, dynamically generated on-the-fly using Groq.
    Initiates a background job to handle the intensive API and database load.
    Jobs are persisted in the `background_jobs` table so they survive restarts.
    """
    logger.info("Request Received")
    logger.info("AI Coach Request Started")
    
    # Check if there is an active job for this user in the DB
    active_job_id = _db_find_active_job(current_user.id)
    if active_job_id:
        logger.info(f"Reusing active DB job {active_job_id} for user {current_user.id}")
        return {"job_id": active_job_id, "status": "processing"}

    job_id = str(uuid.uuid4())
    _db_create_job(user_id=current_user.id, job_id=job_id)
    
    background_tasks.add_task(
        run_recommendations_generation_job,
        user_id=current_user.id,
        job_id=job_id
    )
    
    logger.info(f"Job {job_id} successfully queued (DB-persisted).")
    return {"job_id": job_id, "status": "pending"}


@api_router.get("/job-status/{job_id}")
async def get_job_status(job_id: str):
    """
    Returns the execution status, progress, and results of a coach recommendations job.
    Reads from the persistent `background_jobs` table — survives backend restarts.
    """
    job = _db_get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found."
        )
    return {
        "job_id": job.id,
        "user_id": job.user_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message or "",
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }

@router.get("/challenges", response_model=List[ChallengeOut])
def get_challenges(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Lists the history of personalized coaching challenges.
    """
    logger.info("Request Received")
    try:
        challenges = db.query(ChallengeHistory).filter(
            ChallengeHistory.user_id == current_user.id
        ).order_by(ChallengeHistory.created_at.desc()).all()
        
        # If empty, add default onboarding challenges
        if not challenges:
            default_challenges = [
                ("vocabulary", "Explain how a refrigerator works using simple, non-technical words. Keep it highly fluent and engaging."),
                ("confidence", "Defend an unpopular opinion (e.g. 'Social media should be blocked on weekends') without using any filler vocalizations."),
                ("storytelling", "Narrate your favorite childhood memory in exactly 2 minutes, using sensory descriptions and structural resolution.")
            ]
            for ch_type, prompt_text in default_challenges:
                db_challenge = ChallengeHistory(
                    user_id=current_user.id,
                    challenge_type=ch_type,
                    prompt=prompt_text
                )
                db.add(db_challenge)
            db.commit()
            
            challenges = db.query(ChallengeHistory).filter(
                ChallengeHistory.user_id == current_user.id
            ).order_by(ChallengeHistory.created_at.desc()).all()
            
        logger.info("Response Returned")
        return challenges
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_challenges: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )

@router.post("/challenge/{challenge_id}/attempt")
def attempt_challenge(
    challenge_id: str,
    score: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    """
    Logs an attempt for a specific verbal challenge and updates scores.
    """
    logger.info("Request Received")
    try:
        challenge = db.query(ChallengeHistory).filter(
            ChallengeHistory.id == challenge_id,
            ChallengeHistory.user_id == current_user.id
        ).first()
        
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Challenge not found."
            )
            
        challenge.attempts += 1
        if score > challenge.best_score:
            challenge.best_score = score
            
        if score >= 75: # completion threshold
            challenge.is_completed = True
            challenge.completed_at = datetime.utcnow()
            
        db.commit()
        db.refresh(challenge)
        logger.info("Response Returned")
        return challenge
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in attempt_challenge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis generation or display error. Please try again."
        )

