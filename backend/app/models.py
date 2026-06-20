import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    dna_records = relationship("CommunicationDNA", back_populates="user", cascade="all, delete-orphan")
    growth_records = relationship("GrowthMetrics", back_populates="user", cascade="all, delete-orphan")
    challenge_records = relationship("ChallengeHistory", back_populates="user", cascade="all, delete-orphan")
    coach_recommendations = relationship("CoachRecommendation", back_populates="user", cascade="all, delete-orphan")
    communication_memories = relationship("CommunicationMemory", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    document_sessions = relationship("DocumentSession", back_populates="user", cascade="all, delete-orphan")
    viva_sessions = relationship("VivaSession", back_populates="user", cascade="all, delete-orphan")

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_type = Column(String(50), nullable=False) # 'jam', 'debate', 'interview'
    topic = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    difficulty = Column(String(50), nullable=True, default="Medium")
    video_url = Column(String(500), nullable=True)
    analysis_status = Column(String(20), nullable=False, default="pending")  # pending | processing | completed | failed
    instant_start = Column(Boolean, nullable=True, default=False)
    preparation_mode = Column(Boolean, nullable=True, default=False)
    skip_preparation = Column(Boolean, nullable=True, default=False)
    final_score = Column(Integer, nullable=False, default=0)
    session_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    transcript = relationship("Transcript", back_populates="session", uselist=False, cascade="all, delete-orphan")
    dna = relationship("CommunicationDNA", back_populates="session", uselist=False, cascade="all, delete-orphan")
    voice_metrics = relationship("VoiceMetrics", back_populates="session", uselist=False, cascade="all, delete-orphan")
    face_metrics = relationship("FaceMetrics", back_populates="session", uselist=False, cascade="all, delete-orphan")
    debate_session = relationship("DebateSession", back_populates="session", uselist=False, cascade="all, delete-orphan")
    interview_session = relationship("InterviewSession", back_populates="session", uselist=False, cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="session", cascade="all, delete-orphan")
    recording = relationship("SessionRecording", back_populates="session", uselist=False, cascade="all, delete-orphan")

class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    raw_transcript = Column(Text, nullable=False)
    corrected_transcript = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    wpm = Column(Integer, nullable=False)
    pauses_detected = Column(JSON, nullable=True) # list of timestamps
    word_timings = Column(JSON, nullable=True) # detailed timings list

    session = relationship("Session", back_populates="transcript")

class CommunicationDNA(Base):
    __tablename__ = "communication_dna"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # 14 dimensions of communication
    confidence = Column(Integer, nullable=False, default=0)
    fluency = Column(Integer, nullable=False, default=0)
    vocabulary = Column(Integer, nullable=False, default=0)
    storytelling = Column(Integer, nullable=False, default=0)
    leadership = Column(Integer, nullable=False, default=0)
    persuasion = Column(Integer, nullable=False, default=0)
    emotional_intelligence = Column(Integer, nullable=False, default=0)
    clarity = Column(Integer, nullable=False, default=0)
    energy_level = Column(Integer, nullable=False, default=0)
    speaking_speed = Column(Integer, nullable=False, default=0)
    eye_contact = Column(Integer, nullable=False, default=0)
    posture = Column(Integer, nullable=False, default=0)
    engagement = Column(Integer, nullable=False, default=0)
    filler_words = Column(Integer, nullable=False, default=0)
    
    # 5 new dimensions for Document Analyzer
    subject_expertise = Column(Integer, nullable=False, default=0)
    technical_communication = Column(Integer, nullable=False, default=0)
    explanation_skill = Column(Integer, nullable=False, default=0)
    knowledge_retention = Column(Integer, nullable=False, default=0)
    teaching_ability = Column(Integer, nullable=False, default=0)
    
    # New requested columns
    technical_communication_skill = Column(Integer, nullable=False, default=0)
    presentation_skill = Column(Integer, nullable=False, default=0)
    subject_knowledge = Column(Integer, nullable=False, default=0)
    explanation_ability = Column(Integer, nullable=False, default=0)
    communication_confidence = Column(Integer, nullable=False, default=0)
    
    profile_summary = Column(Text, nullable=True) # e.g. "Analytical Thinker"
    filler_word_frequency = Column(JSON, nullable=True) # e.g. {"um": 3}
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="dna_records")
    session = relationship("Session", back_populates="dna")

class VoiceMetrics(Base):
    __tablename__ = "voice_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    pitch_variation = Column(Float, nullable=True)
    energy_variation = Column(Float, nullable=True)
    rhythm_score = Column(Float, nullable=True)
    stability_score = Column(Float, nullable=True)
    pause_frequency = Column(Float, nullable=True)
    vocal_verdict = Column(String(50), nullable=True) # "Monotone vs Dynamic"
    raw_metrics = Column(JSON, nullable=True)

    session = relationship("Session", back_populates="voice_metrics")

class FaceMetrics(Base):
    __tablename__ = "face_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    eye_contact_percentage = Column(Float, nullable=True)
    gaze_direction_distribution = Column(JSON, nullable=True)
    head_movement_variance = Column(Float, nullable=True)
    head_tilt_average = Column(Float, nullable=True)
    smile_frequency = Column(Float, nullable=True)
    attention_score = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)
    posture_stability = Column(Float, nullable=True)
    attention_heatmap = Column(JSON, nullable=True)

    session = relationship("Session", back_populates="face_metrics")

class GrowthMetrics(Base):
    __tablename__ = "growth_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    metric_type = Column(String(50), nullable=False) # 'confidence', 'vocabulary', etc.
    score_value = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="growth_records")

class ChallengeHistory(Base):
    __tablename__ = "challenge_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    challenge_type = Column(String(50), nullable=False) # 'storytelling', 'confidence', etc.
    prompt = Column(Text, nullable=False)
    attempts = Column(Integer, default=0)
    best_score = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="challenge_records")

class DebateSession(Base):
    __tablename__ = "debate_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    opponent_difficulty = Column(String(50), nullable=False)
    opponent_argument = Column(Text, nullable=True)
    argument_quality_score = Column(Integer, nullable=True)
    persuasion_score = Column(Integer, nullable=True)
    logical_consistency_score = Column(Integer, nullable=True)
    confidence_score = Column(Integer, nullable=True)
    rebuttal_score = Column(Integer, nullable=True)
    communication_score = Column(Integer, nullable=True)
    eye_contact_percentage = Column(Float, nullable=True)
    speaking_speed_wpm = Column(Integer, nullable=True)
    clarity_score = Column(Integer, nullable=True)
    vocabulary_score = Column(Integer, nullable=True)
    scorecard = Column(JSON, nullable=True)

    session = relationship("Session", back_populates="debate_session")

class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    role = Column(String(100), nullable=False) # 'Software Engineer', etc.
    round_type = Column(String(50), nullable=False) # 'Technical', 'Behavioral', etc.
    question_history = Column(JSON, nullable=True)
    communication_feedback = Column(Text, nullable=True)
    confidence_feedback = Column(Text, nullable=True)

    session = relationship("Session", back_populates="interview_session")

class CoachRecommendation(Base):
    __tablename__ = "coach_recommendations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    weakness_identified = Column(String(255), nullable=False)
    suggestion = Column(Text, nullable=False)
    recommended_challenge_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="coach_recommendations")

class CommunicationMemory(Base):
    __tablename__ = "communication_memory"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pinecone_vector_id = Column(String(255), unique=True, nullable=True)
    memory_text = Column(Text, nullable=False)
    memory_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="communication_memories")

class Report(Base):
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    pdf_url = Column(String(500), nullable=True)
    summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="reports")

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_path = Column(String(500), nullable=False)
    extracted_text = Column(Text, nullable=False)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    key_concepts = Column(JSON, nullable=True) # list of key concepts
    keywords = Column(JSON, nullable=True) # list of keywords
    learning_objectives = Column(JSON, nullable=True) # list of learning objectives
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="documents")
    topics = relationship("DocumentTopic", back_populates="document", cascade="all, delete-orphan")
    sessions = relationship("DocumentSession", back_populates="document", cascade="all, delete-orphan")
    viva_sessions = relationship("VivaSession", back_populates="document", cascade="all, delete-orphan")

class DocumentTopic(Base):
    __tablename__ = "document_topics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    topic = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    difficulty = Column(String(50), nullable=False)
    talking_points = Column(JSON, nullable=True)
    estimated_speaking_time = Column(Integer, nullable=False, default=60)
    keywords = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="topics")

class DocumentSession(Base):
    __tablename__ = "document_video_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(String(36), ForeignKey("document_topics.id", ondelete="SET NULL"), nullable=True)
    session_type = Column(String(50), nullable=False) # 'presentation'
    topic_title = Column(String(255), nullable=False)
    video_url = Column(String(500), nullable=True)
    raw_transcript = Column(Text, nullable=True)
    corrected_transcript = Column(Text, nullable=True)
    instant_start = Column(Boolean, nullable=True, default=False)
    preparation_mode = Column(Boolean, nullable=True, default=False)
    skip_preparation = Column(Boolean, nullable=True, default=False)
    analysis_status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="document_sessions")
    document = relationship("Document", back_populates="sessions")
    report = relationship("DocumentReport", back_populates="session", uselist=False, cascade="all, delete-orphan")
    gaps = relationship("KnowledgeGap", back_populates="session", cascade="all, delete-orphan")
    
    # New relationships for full A/V
    transcript = relationship("DocumentTranscript", back_populates="session", uselist=False, cascade="all, delete-orphan")
    voice_metrics = relationship("DocumentVoiceMetrics", back_populates="session", uselist=False, cascade="all, delete-orphan")
    face_metrics = relationship("DocumentFaceMetrics", back_populates="session", uselist=False, cascade="all, delete-orphan")

class DocumentReport(Base):
    __tablename__ = "document_communication_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("document_video_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    accuracy_score = Column(Integer, nullable=False, default=0)
    coverage_score = Column(Integer, nullable=False, default=0)
    understanding_score = Column(Integer, nullable=False, default=0)
    explanation_quality = Column(Integer, nullable=False, default=0)
    technical_correctness = Column(Integer, nullable=False, default=0)
    relevance_score = Column(Integer, nullable=False, default=0)
    communication_metrics = Column(JSON, nullable=True) # JSON of all standard scores (confidence, fluency, posture, eye_contact, etc.)
    suggested_improvements = Column(JSON, nullable=True)
    coach_recommendations = Column(JSON, nullable=True)
    follow_up_questions = Column(JSON, nullable=True) # list of follow-up questions generated by AI
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("DocumentSession", back_populates="report")

class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("document_video_sessions.id", ondelete="CASCADE"), nullable=False)
    concept = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("DocumentSession", back_populates="gaps")

class VivaSession(Base):
    __tablename__ = "viva_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    mode = Column(String(50), nullable=False) # 'viva', 'project', 'resume'
    questions_answers = Column(JSON, nullable=True) # list of {question: str, user_answer_transcript: str, evaluation: dict}
    overall_score = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="viva_sessions")
    document = relationship("Document", back_populates="viva_sessions")

class DocumentTranscript(Base):
    __tablename__ = "document_transcripts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("document_video_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    raw_transcript = Column(Text, nullable=False)
    corrected_transcript = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    wpm = Column(Integer, nullable=False)
    pauses_detected = Column(JSON, nullable=True)
    word_timings = Column(JSON, nullable=True)

    session = relationship("DocumentSession", back_populates="transcript")

class DocumentVoiceMetrics(Base):
    __tablename__ = "document_voice_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("document_video_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    pitch_variation = Column(Float, nullable=True)
    energy_variation = Column(Float, nullable=True)
    rhythm_score = Column(Float, nullable=True)
    stability_score = Column(Float, nullable=True)
    pause_frequency = Column(Float, nullable=True)
    vocal_verdict = Column(String(50), nullable=True)
    raw_metrics = Column(JSON, nullable=True)

    session = relationship("DocumentSession", back_populates="voice_metrics")

class DocumentFaceMetrics(Base):
    __tablename__ = "document_face_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("document_video_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    eye_contact_percentage = Column(Float, nullable=True)
    gaze_direction_distribution = Column(JSON, nullable=True)
    head_movement_variance = Column(Float, nullable=True)
    head_tilt_average = Column(Float, nullable=True)
    smile_frequency = Column(Float, nullable=True)
    attention_score = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)
    posture_stability = Column(Float, nullable=True)
    attention_heatmap = Column(JSON, nullable=True)

    session = relationship("DocumentSession", back_populates="face_metrics")

class SessionRecording(Base):
    __tablename__ = "session_recordings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    video_path = Column(String(500), nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="recording")
