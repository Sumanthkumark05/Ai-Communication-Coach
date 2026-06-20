from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

# User Auth Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=1)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[str] = None

# General Session Schemas
class TopicRequest(BaseModel):
    category: Optional[str] = None

class TopicResponse(BaseModel):
    topic: str
    category: str
    difficulty: Optional[str] = "Medium"
    instant_start: Optional[bool] = False
    preparation_mode: Optional[bool] = False
    skip_preparation: Optional[bool] = False

class GenerateTopicResponse(BaseModel):
    topic: str
    category: str
    difficulty: str
    keywords: List[str]
    talking_points: List[str]
    estimated_speaking_time: int

class TranscriptSchema(BaseModel):
    raw_transcript: str
    corrected_transcript: str
    confidence_score: float
    wpm: int
    pauses_detected: Optional[List[float]] = []
    word_timings: Optional[List[Dict[str, Any]]] = []

    class Config:
        from_attributes = True

class CommunicationDNASchema(BaseModel):
    confidence: int
    fluency: int
    vocabulary: int
    storytelling: int
    leadership: int
    persuasion: int
    emotional_intelligence: int
    clarity: int
    energy_level: int
    speaking_speed: int
    eye_contact: int
    posture: int
    engagement: int
    filler_words: int
    profile_summary: Optional[str] = None
    filler_word_frequency: Optional[Dict[str, int]] = {}
    
    # Document Analyzer specific dimensions
    subject_expertise: Optional[int] = 0
    technical_communication: Optional[int] = 0
    explanation_skill: Optional[int] = 0
    knowledge_retention: Optional[int] = 0
    teaching_ability: Optional[int] = 0
    
    # New requested columns
    technical_communication_skill: Optional[int] = 0
    presentation_skill: Optional[int] = 0
    subject_knowledge: Optional[int] = 0
    explanation_ability: Optional[int] = 0
    communication_confidence: Optional[int] = 0

    class Config:
        from_attributes = True

class VoiceMetricsSchema(BaseModel):
    pitch_variation: Optional[float] = None
    energy_variation: Optional[float] = None
    rhythm_score: Optional[float] = None
    stability_score: Optional[float] = None
    pause_frequency: Optional[float] = None
    vocal_verdict: Optional[str] = None

    class Config:
        from_attributes = True

class FaceMetricsSchema(BaseModel):
    eye_contact_percentage: Optional[float] = None
    gaze_direction_distribution: Optional[Dict[str, float]] = {}
    head_movement_variance: Optional[float] = None
    head_tilt_average: Optional[float] = None
    smile_frequency: Optional[float] = None
    attention_score: Optional[float] = None
    engagement_score: Optional[float] = None
    posture_stability: Optional[float] = None
    attention_heatmap: Optional[List[Dict[str, Any]]] = []

    class Config:
        from_attributes = True

class ReportSchema(BaseModel):
    id: str
    session_id: str
    pdf_url: Optional[str] = None
    summary: Optional[Dict[str, Any]] = {}
    created_at: datetime

    class Config:
        from_attributes = True

class DebateSessionSchema(BaseModel):
    opponent_difficulty: str
    opponent_argument: Optional[str] = None
    argument_quality_score: Optional[int] = None
    persuasion_score: Optional[int] = None
    logical_consistency_score: Optional[int] = None
    confidence_score: Optional[int] = None
    rebuttal_score: Optional[int] = None
    communication_score: Optional[int] = None
    eye_contact_percentage: Optional[float] = None
    speaking_speed_wpm: Optional[int] = None
    clarity_score: Optional[int] = None
    vocabulary_score: Optional[int] = None
    scorecard: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class SessionOut(BaseModel):
    id: str
    user_id: str
    session_type: str
    topic: str
    category: str
    difficulty: Optional[str] = "Medium"
    video_url: Optional[str] = None
    analysis_status: Optional[str] = "pending"  # pending | processing | completed | failed
    status: Optional[str] = "pending"
    progress: Optional[int] = 0
    message: Optional[str] = ""
    instant_start: Optional[bool] = False
    preparation_mode: Optional[bool] = False
    skip_preparation: Optional[bool] = False
    final_score: Optional[int] = 0
    created_at: datetime
    transcript: Optional[TranscriptSchema] = None
    dna: Optional[CommunicationDNASchema] = None
    voice_metrics: Optional[VoiceMetricsSchema] = None
    face_metrics: Optional[FaceMetricsSchema] = None
    reports: Optional[List[ReportSchema]] = []
    debate_session: Optional[DebateSessionSchema] = None
    session_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

# History and Leaderboard
class JAMSessionHistoryItem(BaseModel):
    id: str
    topic: str
    category: str
    difficulty: Optional[str] = "Medium"
    session_type: str
    created_at: datetime
    final_score: Optional[int] = 0
    overall_score: Optional[int] = 0
    status: Optional[str] = "completed"

class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    average_score: float
    sessions_count: int

# Growth & Dashboards
class ProgressPoint(BaseModel):
    date: str
    confidence: float
    fluency: float
    vocabulary: float
    storytelling: float
    leadership: float
    persuasion: float
    engagement: float

class DashboardStats(BaseModel):
    total_sessions: int
    avg_confidence: float
    avg_fluency: float
    avg_communication: float
    streak: int
    progress_data: List[ProgressPoint]

# Challenges
class ChallengeCreate(BaseModel):
    challenge_type: str
    prompt: str

class ChallengeOut(BaseModel):
    id: str
    challenge_type: str
    prompt: str
    attempts: int
    best_score: int
    is_completed: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Debates
class DebateSessionOut(BaseModel):
    id: str
    session_id: str
    opponent_difficulty: str
    opponent_argument: Optional[str] = None
    argument_quality_score: Optional[int] = None
    persuasion_score: Optional[int] = None
    logical_consistency_score: Optional[int] = None
    scorecard: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

# Interviews
class InterviewSessionOut(BaseModel):
    id: str
    session_id: str
    role: str
    round_type: str
    question_history: Optional[List[str]] = []
    communication_feedback: Optional[str] = None
    confidence_feedback: Optional[str] = None

    class Config:
        from_attributes = True

# Document Analyzer Schemas
class DocumentTopicOut(BaseModel):
    id: str
    document_id: str
    topic: str
    category: str
    difficulty: str
    talking_points: Optional[List[str]] = []
    estimated_speaking_time: int
    keywords: Optional[List[str]] = []

    class Config:
        from_attributes = True

class DocumentOut(BaseModel):
    id: str
    user_id: str
    filename: str
    file_type: str
    file_path: str
    title: Optional[str] = None
    summary: Optional[str] = None
    key_concepts: Optional[List[str]] = []
    keywords: Optional[List[str]] = []
    learning_objectives: Optional[List[str]] = []
    created_at: datetime
    topics: List[DocumentTopicOut] = []

    class Config:
        from_attributes = True

class DocumentSessionCreate(BaseModel):
    document_id: str
    topic_id: Optional[str] = None
    topic_title: str
    category: str
    instant_start: Optional[bool] = False
    preparation_mode: Optional[bool] = False
    skip_preparation: Optional[bool] = False

class KnowledgeGapOut(BaseModel):
    id: str
    session_id: str
    concept: str
    description: Optional[str] = None

    class Config:
        from_attributes = True

class DocumentReportOut(BaseModel):
    id: str
    session_id: str
    accuracy_score: int
    coverage_score: int
    understanding_score: int
    explanation_quality: int
    technical_correctness: int
    relevance_score: int
    communication_metrics: Optional[Dict[str, Any]] = {}
    suggested_improvements: Optional[List[str]] = []
    coach_recommendations: Optional[List[str]] = []
    follow_up_questions: Optional[List[str]] = []
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentSessionOut(BaseModel):
    id: str
    user_id: str
    document_id: str
    topic_id: Optional[str] = None
    session_type: str
    topic_title: str
    video_url: Optional[str] = None
    raw_transcript: Optional[str] = None
    corrected_transcript: Optional[str] = None
    analysis_status: Optional[str] = "pending"
    status: Optional[str] = "pending"
    progress: Optional[int] = 0
    message: Optional[str] = ""
    instant_start: Optional[bool] = False
    preparation_mode: Optional[bool] = False
    skip_preparation: Optional[bool] = False
    created_at: datetime
    report: Optional[DocumentReportOut] = None
    gaps: List[KnowledgeGapOut] = []
    transcript: Optional[TranscriptSchema] = None
    voice_metrics: Optional[VoiceMetricsSchema] = None
    face_metrics: Optional[FaceMetricsSchema] = None

    class Config:
        from_attributes = True

class VivaSessionStart(BaseModel):
    document_id: str
    mode: str

class VivaSessionOut(BaseModel):
    id: str
    user_id: str
    document_id: str
    mode: str
    questions_answers: Optional[List[Dict[str, Any]]] = []
    overall_score: int
    created_at: datetime

    class Config:
        from_attributes = True
