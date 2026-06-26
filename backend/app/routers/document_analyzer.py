import os
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query, Header
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models import User, Document, DocumentTopic, DocumentSession, DocumentReport, KnowledgeGap, VivaSession, CommunicationDNA, DocumentTranscript, DocumentVoiceMetrics, DocumentFaceMetrics
from app.schemas import DocumentOut, DocumentSessionOut, DocumentSessionCreate, VivaSessionStart, VivaSessionOut, DocumentRecordingOut
from app.auth import get_current_user
from app.config import settings
from app.services.document_service import DocumentService
from app.services.ai_analyzer import analyze_video_speech
from app.services.audio_processor import process_audio
from app.routers.jam import SESSION_ERRORS

logger = logging.getLogger("jam_analyzer")

router = APIRouter(prefix="/document", tags=["document"])

doc_service = DocumentService()

@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    import time
    start_time = time.time()
    logger.info("Document Upload Started")
    logger.info("Request Received")
    try:
        # 1. Validate file extension
        filename = file.filename
        ext = os.path.splitext(filename.lower())[1]
        if ext not in [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'. Must be PDF, Word, PowerPoint, TXT, or MD."
            )

        # 2. Check size (50 MB limit)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        if size_mb > 50:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds maximum allowed size of 50 MB."
            )

        # Save to uploads directory
        db_start = time.time()
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        temp_filepath = os.path.join(settings.UPLOAD_DIR, f"{current_user.id}_{filename}")
        try:
            with open(temp_filepath, "wb") as f:
                f.write(contents)
        except Exception as e:
            logger.error(f"Failed to save uploaded document: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not save file to disk."
            )
        io_time = time.time() - db_start

        # 3. Parse and analyze document text
        logger.info("Analysis Started")
        logger.info("Processing Started")
        try:
            ext_start = time.time()
            extracted_text = doc_service.extract_text(temp_filepath, filename)
            extraction_time = time.time() - ext_start
            
            logger.info("LLM Client Initialized")
            logger.info("LLM Request Sent")
            llm_start1 = time.time()
            doc_analysis = doc_service.analyze_document_content(extracted_text)
            llm_time1 = time.time() - llm_start1
            logger.info("LLM Response Received")
            
            logger.info("LLM Request Sent")
            llm_start2 = time.time()
            generated_topics = doc_service.generate_topics(doc_analysis, extracted_text)
            llm_time2 = time.time() - llm_start2
            logger.info("LLM Response Received")
        except Exception as e:
            logger.error(f"Document analysis service failure: {e}")
            # Clean up file
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process and analyze document content: {str(e)}"
            )

        # 4. Save to database
        db_start2 = time.time()
        db_doc = Document(
            user_id=current_user.id,
            filename=filename,
            file_type=ext,
            file_path=temp_filepath,
            extracted_text=extracted_text,
            title=doc_analysis.get("title", filename),
            summary=doc_analysis.get("summary", ""),
            key_concepts=doc_analysis.get("key_concepts", []),
            keywords=doc_analysis.get("keywords", []),
            learning_objectives=doc_analysis.get("learning_objectives", [])
        )
        db.add(db_doc)
        db.flush() # populate db_doc.id

        db_topics = []
        for topic in generated_topics:
            db_topic = DocumentTopic(
                document_id=db_doc.id,
                topic=topic.get("topic"),
                category=topic.get("category", "General"),
                difficulty=topic.get("difficulty", "Intermediate"),
                talking_points=topic.get("talking_points", []),
                estimated_speaking_time=topic.get("estimated_speaking_time", 60),
                keywords=topic.get("keywords", [])
            )
            db.add(db_topic)
            db_topics.append(db_topic)

        db.commit()
        db_commit_time = time.time() - db_start2
        db.refresh(db_doc)
        
        total_time = time.time() - start_time
        logger.info(f"[PERF] upload_document timing: io={io_time:.4f}s, extract={extraction_time:.4f}s, llm_anal={llm_time1:.4f}s, llm_topics={llm_time2:.4f}s, db_persist={db_commit_time:.4f}s, total={total_time:.4f}s")
        logger.info("Document Uploaded")
        logger.info("Analysis Generated")
        logger.info("Analysis Completed")
        logger.info("Response Returned")
        return db_doc
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in upload_document: {e}")
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

@router.post("/session", response_model=DocumentSessionOut)
def create_document_session(
    payload: DocumentSessionCreate,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    try:
        # Verify document exists
        doc = db.query(Document).filter(Document.id == payload.document_id, Document.user_id == current_user.id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied."
            )

        # Verify topic exists if topic_id is provided
        if payload.topic_id:
            topic = db.query(DocumentTopic).filter(DocumentTopic.id == payload.topic_id, DocumentTopic.document_id == payload.document_id).first()
            if not topic:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Topic not found on selected document."
                )

        db_session = DocumentSession(
            user_id=current_user.id,
            document_id=payload.document_id,
            topic_id=payload.topic_id,
            session_type="presentation",
            topic_title=payload.topic_title,
            instant_start=payload.instant_start,
            preparation_mode=payload.preparation_mode,
            skip_preparation=payload.skip_preparation
        )
        db.add(db_session)
        db.commit()
        db.refresh(db_session)
        logger.info("Response Returned")
        return db_session
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in create_document_session: {e}")
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

@router.post("/session/{session_id}/upload", response_model=DocumentSessionOut)
async def upload_document_session_video(
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
        # Verify session
        session = db.query(DocumentSession).filter(
            DocumentSession.id == session_id,
            DocumentSession.user_id == current_user.id
        ).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document session not found."
            )

        # Organize recordings by user and generate unique filenames
        recordings_dir = os.path.join(settings.UPLOAD_DIR, "recordings", f"user_{current_user.id}")
        os.makedirs(recordings_dir, exist_ok=True)
        file_ext = os.path.splitext(file.filename)[1] or ".webm"
        video_filename = f"doc_sess_{session_id}{file_ext}"
        video_path = os.path.join(recordings_dir, video_filename)
        logger.info(f"[Document Session Upload] Video upload received. Saving video to: {video_path}...")
        try:
            with open(video_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            # Update Step 1 with actual size
            logger.info(f"[STEP 1] Completed\n- size: {len(content)} bytes")
            # [STEP 2] Audio saved successfully
            logger.info(f"[STEP 2]\nAudio saved successfully\n- file path: {video_path}")
            logger.info(f"[Document Session Upload] Saved {len(content):,} bytes.")
        except Exception as e:
            logger.error(f"[Document Session Upload] Failed to save document session video: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not save video file: {str(e)}"
            )

        session.video_url = f"/uploads/recordings/user_{current_user.id}/{video_filename}"
        session.analysis_status = "processing"
        db.commit()
        db.refresh(session)

        # Check if DocumentRecording exists, if not create one
        from app.models import DocumentRecording
        recording = db.query(DocumentRecording).filter(DocumentRecording.session_id == session_id).first()
        if not recording:
            recording = DocumentRecording(
                session_id=session_id,
                user_id=current_user.id,
                document_id=session.document_id,
                recording_path=video_path,
                recording_url=session.video_url,
                recording_duration=0.0
            )
            db.add(recording)
            db.commit()
            db.refresh(recording)
            recording.recording_id = recording.id
            recording.analysis_id = session_id
        else:
            recording.recording_path = video_path
            recording.recording_url = session.video_url
        db.commit()

        # Snapshot parameters for the background thread
        topic_title = session.topic_title
        document_id = session.document_id
        user_id = current_user.id

        import threading

        def run_doc_session_analysis_background():
            from app.database import SessionLocal
            from app.models import DocumentSession, DocumentReport, KnowledgeGap, DocumentTranscript, DocumentVoiceMetrics, DocumentFaceMetrics, CommunicationDNA
            bg_db = SessionLocal()
            try:
                bg_session = bg_db.query(DocumentSession).filter(DocumentSession.id == session_id).first()
                if not bg_session:
                    return

                pipeline_start = time.time()
                logger.info(f"[BG Doc Session] Starting analysis pipeline for session {session_id}")

                # Stage 1: Run standard speech analysis (Whisper + MediaPipe + Groq)
                t1 = time.time()
                try:
                    analysis_result = analyze_video_speech(video_path, topic_title, "Document Presentation", db=bg_db, job_id=session_id, job_model=DocumentSession)
                    logger.info(f"[BG Doc Session] Stage 1 completed in {time.time() - t1:.2f}s")
                except Exception as e:
                    logger.error(f"A/V speech analysis failed for document session: {e}")
                    import traceback
                    print("FULL TRACEBACK:")
                    traceback.print_exc()
                    error_msg = f"Error Type: {type(e).__name__}\nError Message: {str(e)}\nTraceback:\n{traceback.format_exc()}"
                    SESSION_ERRORS[session_id] = error_msg
                    
                    bg_session.analysis_status = "failed"
                    bg_db.commit()
                    return

                if analysis_result.get("status") == "NO_SPEECH_DETECTED":
                    bg_session.analysis_status = "failed"
                    bg_db.commit()
                    return

                raw_transcript = analysis_result.get("original_transcript", "")
                corrected_transcript = analysis_result.get("corrected_transcript", "")
                bg_session.raw_transcript = raw_transcript
                bg_session.corrected_transcript = corrected_transcript
                bg_db.commit()

                # Consolidate standard communication metrics
                comm_metrics = {
                    "confidence": analysis_result.get("confidence_score", 80),
                    "fluency": analysis_result.get("fluency_score", 80),
                    "eye_contact": analysis_result.get("eye_contact_score", 80),
                    "posture": analysis_result.get("posture_score", 80),
                    "vocabulary": analysis_result.get("vocabulary_score", 80),
                    "speaking_speed": analysis_result.get("speaking_pace_score", 80),
                    "wpm": analysis_result.get("words_per_minute", 130),
                    "leadership": analysis_result.get("communication_score", 80),
                    "persuasion": analysis_result.get("content_quality_score", 80),
                    "engagement": analysis_result.get("engagement_score", 80),
                    "filler_words": analysis_result.get("overall_score", 80)
                }

                # Stage 2: Run Comparative Speech-to-Document Analysis
                doc = bg_session.document
                t2 = time.time()
                logger.info("[BG Doc Session] Stage 2: Running Comparative Speech-to-Document Analysis...")
                try:
                    comp_result = doc_service.evaluate_speech_against_document(
                        doc.extracted_text, topic_title, raw_transcript, comm_metrics
                    )
                    logger.info(f"[BG Doc Session] Stage 2 completed in {time.time() - t2:.2f}s")
                except Exception as e:
                    logger.error(f"Speech to document comparison failed: {e}")
                    import traceback
                    print("FULL TRACEBACK:")
                    traceback.print_exc()
                    error_msg = f"Error Type: {type(e).__name__}\nError Message: {str(e)}\nTraceback:\n{traceback.format_exc()}"
                    SESSION_ERRORS[session_id] = error_msg
                    
                    bg_session.analysis_status = "failed"
                    bg_db.commit()
                    return

                # Stage 3: Create report & gaps & metrics records
                t3 = time.time()
                logger.info("[BG Doc Session] Stage 3: Saving metrics & reports to database...")
                db_report = DocumentReport(
                    session_id=session_id,
                    accuracy_score=comp_result.get("accuracy_score", 75),
                    coverage_score=comp_result.get("coverage_score", 70),
                    understanding_score=comp_result.get("understanding_score", 72),
                    explanation_quality=comp_result.get("explanation_quality", 74),
                    technical_correctness=comp_result.get("technical_correctness", 76),
                    relevance_score=comp_result.get("relevance_score", 80),
                    communication_metrics=comm_metrics,
                    suggested_improvements=comp_result.get("suggested_improvements", []),
                    coach_recommendations=comp_result.get("coach_recommendations", []),
                    follow_up_questions=comp_result.get("follow_up_questions", [])
                )
                bg_db.add(db_report)

                for gap in comp_result.get("knowledge_gaps", []):
                    db_gap = KnowledgeGap(
                        session_id=session_id,
                        concept=gap.get("concept", "Omitted Concept"),
                        description=gap.get("description", "")
                    )
                    bg_db.add(db_gap)

                db_transcript = DocumentTranscript(
                    session_id=session_id,
                    raw_transcript=raw_transcript,
                    corrected_transcript=corrected_transcript,
                    confidence_score=analysis_result.get("transcript_confidence", 80),
                    wpm=comm_metrics["wpm"],
                    pauses_detected=[],
                    word_timings=[]
                )
                bg_db.add(db_transcript)

                db_voice = DocumentVoiceMetrics(
                    session_id=session_id,
                    pitch_variation=0.0,
                    energy_variation=0.0,
                    rhythm_score=float(comm_metrics["wpm"]),
                    stability_score=float(analysis_result.get("transcript_confidence", 80)),
                    pause_frequency=0.0,
                    vocal_verdict="Dynamic" if analysis_result.get("overall_score", 80) >= 75 else "Stable",
                    raw_metrics={}
                )
                bg_db.add(db_voice)

                db_face = DocumentFaceMetrics(
                    session_id=session_id,
                    eye_contact_percentage=float(comm_metrics["eye_contact"]),
                    gaze_direction_distribution={},
                    head_movement_variance=0.0,
                    head_tilt_average=0.0,
                    smile_frequency=float(analysis_result.get("emotion_stability_score", 80)),
                    attention_score=float(comm_metrics["eye_contact"]),
                    engagement_score=float(comm_metrics["engagement"]),
                    posture_stability=float(comm_metrics["posture"]),
                    attention_heatmap=[]
                )
                bg_db.add(db_face)

                dna = bg_db.query(CommunicationDNA).filter(
                    CommunicationDNA.user_id == user_id,
                    CommunicationDNA.session_id == session_id
                ).first()

                if not dna:
                    dna = CommunicationDNA(
                        user_id=user_id,
                        session_id=session_id,
                        confidence=comm_metrics["confidence"],
                        fluency=comm_metrics["fluency"],
                        vocabulary=comm_metrics["vocabulary"],
                        storytelling=comm_metrics["persuasion"],
                        leadership=comm_metrics["leadership"],
                        persuasion=comm_metrics["persuasion"],
                        emotional_intelligence=80,
                        clarity=analysis_result.get("clarity_score", 8) * 10,
                        energy_level=80,
                        speaking_speed=comm_metrics["speaking_speed"],
                        eye_contact=comm_metrics["eye_contact"],
                        posture=comm_metrics["posture"],
                        engagement=comm_metrics["engagement"],
                        filler_words=comm_metrics["filler_words"],
                        profile_summary="Technical Twin Presenter",
                        filler_word_frequency=analysis_result.get("filler_words", {})
                    )
                    bg_db.add(dna)

                dna.subject_expertise = comp_result.get("accuracy_score", 75)
                dna.technical_communication = comp_result.get("technical_correctness", 76)
                dna.explanation_skill = comp_result.get("explanation_quality", 74)
                dna.knowledge_retention = comp_result.get("understanding_score", 72)
                dna.teaching_ability = comp_result.get("coverage_score", 70)

                dna.technical_communication_skill = comp_result.get("technical_correctness", 76)
                dna.presentation_skill = comm_metrics["fluency"]
                dna.subject_knowledge = comp_result.get("accuracy_score", 75)
                dna.explanation_ability = comp_result.get("explanation_quality", 74)
                dna.communication_confidence = comm_metrics["confidence"]

                # Update recording details
                from app.models import DocumentRecording
                recording = bg_db.query(DocumentRecording).filter(DocumentRecording.session_id == session_id).first()
                if recording:
                    recording.report_id = db_report.id
                    audio_length = analysis_result.get("diagnostics", {}).get("audio_length", 0.0)
                    if audio_length > 0:
                        recording.recording_duration = float(audio_length)

                bg_session.analysis_status = "completed"
                bg_db.commit()
                # [STEP 8] Database save
                logger.info("[STEP 8]\nDatabase save\n- success/failure: success")
                logger.info(f"[BG Doc Session] Stage 3 completed in {time.time() - t3:.2f}s")
                logger.info(f"[BG Doc Session] Full pipeline done in {time.time() - pipeline_start:.2f}s for session {session_id}")
            except Exception as exc:
                logger.error(f"[BG Doc Session] Analysis pipeline failed for session {session_id}: {exc}", exc_info=True)
                import traceback
                print("FULL TRACEBACK:")
                traceback.print_exc()
                
                # [STEP 8] Database save
                logger.info("[STEP 8]\nDatabase save\n- success/failure: failure")
                
                error_msg = f"Error Type: {type(exc).__name__}\nError Message: {str(exc)}\nTraceback:\n{traceback.format_exc()}"
                SESSION_ERRORS[session_id] = error_msg
                
                try:
                    bg_session = bg_db.query(DocumentSession).filter(DocumentSession.id == session_id).first()
                    if bg_session:
                        bg_session.analysis_status = "failed"
                        bg_db.commit()
                except Exception:
                    pass
            finally:
                bg_db.close()

        # Start the background thread
        thread = threading.Thread(target=run_doc_session_analysis_background, daemon=True)
        thread.start()
        logger.info(f"[Document Session Upload] Analysis background job started for session {session_id}. Returning session immediately.")

        db.refresh(session)
        logger.info("Response Returned")
        
        # [STEP 9] Final API response
        logger.info(f"[STEP 9]\nFinal API response\n- status: {session.analysis_status}\n- session ID: {session.id}")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in upload_document_session_video: {e}")
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

@router.get("/session/{session_id}", response_model=DocumentSessionOut)
def get_document_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    try:
        session = db.query(DocumentSession).filter(
            DocumentSession.id == session_id,
            DocumentSession.user_id == current_user.id
        ).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found."
            )
        # Convert to Pydantic object
        from app.schemas import DocumentSessionOut
        session_data = DocumentSessionOut.from_orm(session)
        
        from datetime import datetime
        elapsed = (datetime.utcnow() - session.created_at).total_seconds()
        if session.analysis_status == "completed":
            session_data.status = "completed"
            session_data.progress = 100
            session_data.message = "Analysis completed."
        elif session.analysis_status == "failed":
            session_data.status = "failed"
            session_data.progress = 100
            session_data.message = SESSION_ERRORS.get(session_id, "Analysis failed.")
        else:
            session_data.status = "processing"
            session_data.progress = min(90, int(10 + (elapsed / 45.0) * 80.0))
            session_data.message = "Analysis is still running."

        # Dynamically secure the video URL with a stream token
        if session.video_url:
            relative_path = session.video_url.replace("/uploads/", "", 1)
            file_path = os.path.join(settings.UPLOAD_DIR, relative_path)
            if os.path.exists(file_path):
                from app.auth import create_access_token
                from datetime import timedelta
                stream_token = create_access_token(
                    data={"sub": current_user.id},
                    expires_delta=timedelta(minutes=30)
                )
                session_data.video_url = f"/api/document-analyzer/{session_id}/recording?token={stream_token}"
            else:
                session_data.video_url = None

        logger.info("Response Returned")
        return session_data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_document_session: {e}")
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

@router.post("/viva/start", response_model=VivaSessionOut)
def start_viva_session(
    payload: VivaSessionStart,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    try:
        # Verify document
        doc = db.query(Document).filter(Document.id == payload.document_id, Document.user_id == current_user.id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found."
            )

        # Generate questions based on mode
        logger.info("LLM Client Initialized")
        logger.info("LLM Request Sent")
        try:
            questions = doc_service.generate_viva_questions(doc.extracted_text, payload.mode)
            logger.info("LLM Response Received")
        except Exception as e:
            logger.error(f"Failed to generate viva questions: {e}")
            logger.info("LLM Response Received")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate viva questions from the document."
            )

        qa_list = [{"question": q, "user_answer_transcript": "", "evaluation": None} for q in questions]

        viva = VivaSession(
            user_id=current_user.id,
            document_id=payload.document_id,
            mode=payload.mode,
            questions_answers=qa_list,
            overall_score=0
        )
        db.add(viva)
        db.commit()
        db.refresh(viva)
        logger.info("Response Returned")
        return viva
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in start_viva_session: {e}")
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

@router.post("/viva/{viva_id}/answer", response_model=VivaSessionOut)
async def submit_viva_answer(
    viva_id: str,
    question_index: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    logger.info("Recording Received")
    try:
        # Verify viva session
        viva = db.query(VivaSession).filter(
            VivaSession.id == viva_id,
            VivaSession.user_id == current_user.id
        ).first()
        if not viva:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Viva session not found."
            )

        # Save audio/video file temporarily
        file_ext = os.path.splitext(file.filename)[1] or ".webm"
        temp_ans_path = os.path.join(settings.UPLOAD_DIR, f"viva_{viva_id}_q{question_index}{file_ext}")
        logger.info(f"[Viva Upload] Answer upload received. Saving file to: {temp_ans_path}")
        try:
            with open(temp_ans_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            logger.info(f"[Viva Upload] Saved viva answer file {temp_ans_path} with size: {len(content)} bytes")
        except Exception as e:
            logger.error(f"[Viva Upload] Failed to save viva audio response: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not save answer audio file."
            )

        # Transcribe speech
        logger.info("Processing Started")
        try:
            speech_results = process_audio(temp_ans_path, db=db, job_id=None, job_model=None)
            logger.warning(f"Speech results for Viva answer: {speech_results}")
        except Exception as e:
            logger.error(f"Speech enunciation failed: {e}")
            if os.path.exists(temp_ans_path):
                os.remove(temp_ans_path)
            import traceback
            print("FULL TRACEBACK:")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc()
                }
            )

        answer_transcript = speech_results.get("raw_transcript", "") or speech_results.get("transcript", "")
        if not answer_transcript.strip():
            if os.path.exists(temp_ans_path):
                os.remove(temp_ans_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No speech detected in your answer."
            )
        logger.info("Transcript Generated")
        logger.info("Metrics Generated")

        # Grade response
        doc = viva.document
        questions_answers = list(viva.questions_answers or [])
        if question_index < 0 or question_index >= len(questions_answers):
            if os.path.exists(temp_ans_path):
                os.remove(temp_ans_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid question index."
            )

        question = questions_answers[question_index]["question"]
        logger.info("LLM Client Initialized")
        logger.info("LLM Request Sent")
        try:
            evaluation = doc_service.evaluate_viva_response(
                doc.extracted_text, question, answer_transcript
            )
            logger.info("LLM Response Received")
        except Exception as e:
            logger.error(f"Failed to grade viva response: {e}")
            logger.info("LLM Response Received")
            if os.path.exists(temp_ans_path):
                os.remove(temp_ans_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to evaluate your response against the document."
            )

        # Clean up file
        if os.path.exists(temp_ans_path):
            os.remove(temp_ans_path)

        # Update database
        questions_answers[question_index]["user_answer_transcript"] = answer_transcript
        questions_answers[question_index]["evaluation"] = evaluation
        viva.questions_answers = questions_answers
        flag_modified(viva, "questions_answers")

        # Re-calculate overall score
        graded_scores = [qa["evaluation"]["score"] for qa in questions_answers if qa.get("evaluation") is not None]
        if graded_scores:
            viva.overall_score = sum(graded_scores) // len(graded_scores)

        db.commit()
        db.refresh(viva)
        logger.info("Analysis Generated")
        logger.info("Response Returned")
        return viva
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in submit_viva_answer: {e}")
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

@router.get("/viva/{viva_id}", response_model=VivaSessionOut)
def get_viva_session(
    viva_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    logger.info("Request Received")
    try:
        viva = db.query(VivaSession).filter(
            VivaSession.id == viva_id,
            VivaSession.user_id == current_user.id
        ).first()
        if not viva:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Viva session not found."
            )
        logger.info("Response Returned")
        return viva
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_viva_session: {e}")
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


document_analyzer_recording_router = APIRouter(tags=["document-analyzer"])

@document_analyzer_recording_router.get("/document-analyzer/{session_id}/recording")
def stream_document_recording(
    session_id: str,
    token: Optional[str] = None,
    range: Optional[str] = Header(None),
    db: DBSession = Depends(get_db)
):
    from fastapi.responses import StreamingResponse
    import mimetypes
    from jose import jwt
    
    # 1. Authenticate user from query parameter
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required for streaming."
        )
    
    token_str = token
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
        
    # 2. Retrieve session
    session = db.query(DocumentSession).filter(DocumentSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
        
    # 3. Verify ownership
    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session's video"
        )
        
    # 4. Check if recording file exists
    if not session.video_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recording associated with this session."
        )
        
    relative_path = session.video_url.replace("/uploads/", "", 1)
    file_path = os.path.join(settings.UPLOAD_DIR, relative_path)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording video file not found."
        )
        
    file_size = os.path.getsize(file_path)
    
    # Parse range header
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


@router.get("/recording/{recording_id}", response_model=DocumentRecordingOut)
def get_document_recording(
    recording_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    from app.models import DocumentRecording
    recording = db.query(DocumentRecording).filter(DocumentRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this recording")

    from app.auth import create_access_token
    from datetime import timedelta
    stream_token = create_access_token(
        data={"sub": current_user.id},
        expires_delta=timedelta(minutes=30)
    )

    return {
        "recording_id": str(recording.id),
        "recording_url": f"/api/document-analyzer/{recording.session_id}/recording?token={stream_token}",
        "duration": str(recording.recording_duration or 0.0),
        "analysis_id": str(recording.session_id),
        "report_id": str(recording.report_id or "")
    }

@router.get("/report/{report_id}", response_model=DocumentRecordingOut)
def get_document_report_recording(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    from app.models import DocumentReport, DocumentRecording
    report = db.query(DocumentReport).filter(DocumentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    session = report.session
    if not session:
        raise HTTPException(status_code=404, detail="Session not found for report")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    recording = db.query(DocumentRecording).filter(DocumentRecording.session_id == session.id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found for this report")

    from app.auth import create_access_token
    from datetime import timedelta
    stream_token = create_access_token(
        data={"sub": current_user.id},
        expires_delta=timedelta(minutes=30)
    )

    return {
        "recording_id": str(recording.id),
        "recording_url": f"/api/document-analyzer/{recording.session_id}/recording?token={stream_token}",
        "duration": str(recording.recording_duration or 0.0),
        "analysis_id": str(recording.session_id),
        "report_id": str(recording.report_id or report_id)
    }

@router.get("/history", response_model=List[DocumentRecordingOut])
def get_document_history(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    from app.models import DocumentRecording
    recordings = db.query(DocumentRecording).filter(DocumentRecording.user_id == current_user.id).all()
    from app.auth import create_access_token
    from datetime import timedelta
    stream_token = create_access_token(
        data={"sub": current_user.id},
        expires_delta=timedelta(minutes=30)
    )
    res = []
    for r in recordings:
        res.append({
            "recording_id": str(r.id),
            "recording_url": f"/api/document-analyzer/{r.session_id}/recording?token={stream_token}",
            "duration": str(r.recording_duration or 0.0),
            "analysis_id": str(r.session_id),
            "report_id": str(r.report_id or "")
        })
    return res
