import os
import logging
import json
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.config import settings
from app.services.groq_service import GroqService

logger = logging.getLogger("jam_analyzer")

class StructuredEvaluation(BaseModel):
    summary: str = Field(description="A concise summary of what the candidate said.")
    corrected_transcript: str = Field(description="The transcript with speech/filler words cleaned up grammatically. Keep the original text structure.")
    
    # 0-100 scores
    confidence: int = Field(description="Confidence score between 0 and 100 based on word choices, pauses, and speech delivery context.")
    fluency: int = Field(description="Fluency score between 0 and 100.")
    vocabulary: int = Field(description="Vocabulary score between 0 and 100.")
    storytelling: int = Field(description="Storytelling score between 0 and 100.")
    leadership: int = Field(description="Leadership and command score between 0 and 100.")
    persuasion: int = Field(description="Persuasion and argument strength score between 0 and 100.")
    emotional_intelligence: int = Field(description="Emotional intelligence score between 0 and 100.")
    clarity: int = Field(description="Clarity and structure score between 0 and 100.")
    energy_level: int = Field(description="Auditory energy score between 0 and 100.")
    speaking_speed: int = Field(description="Speaking pace score between 0 and 100.")
    eye_contact: int = Field(description="Estimated visual delivery score based on context between 0 and 100.")
    posture: int = Field(description="Estimated posture score between 0 and 100.")
    engagement: int = Field(description="Total audience engagement score between 0 and 100.")
    filler_words: int = Field(description="Penalty score where 100 is no filler words, and lower scores indicate high filler usage.")

    profile_summary: str = Field(description="Categorical twin type (e.g. 'Analytical Thinker', 'Emerging Leader', 'Expressive Narrator').")
    
    # Lists
    strengths: List[str] = Field(description="List of 2-3 specific communication strengths observed.")
    weaknesses: List[str] = Field(description="List of 2-3 communication weaknesses observed.")
    missed_opportunities: List[str] = Field(description="Concepts or delivery opportunities the speaker missed.")
    suggestions: List[str] = Field(description="Actionable improvement suggestions.")
    
    expected_answer: str = Field(description="An ideal, expert-level response to the topic question.")
    missing_concepts: List[str] = Field(description="Key concepts missing from the candidate's speech that are critical to an expert response.")
    final_verdict: str = Field(description="Verdict: 'Excellent', 'Good', 'Average', or 'Poor'.")
    filler_word_frequency: Dict[str, int] = Field(description="Estimated filler words count for words like 'um', 'uh', 'like', 'you know', 'actually'.")

class OpenAIService:
    def __init__(self):
        logger.info("[OpenAIService] Initializing Unified GroqService wrapper...")
        self.groq_service = GroqService()

    def call_llm_json(self, prompt: str, system_prompt: str = "You are an elite communication twin mentor. Output clean JSON only.", fallback_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Orchestrates LLM calls through centralized GroqService.
        """
        try:
            res_json = self.groq_service.call_groq_json(prompt, system_prompt)
            
            # Map keys for interview coach feedback
            if "communication_feedback" not in res_json:
                res_json["communication_feedback"] = res_json.get("coaching_feedback", "")
            if "confidence_feedback" not in res_json:
                res_json["confidence_feedback"] = res_json.get("executive_summary", "")

            # Map keys for debate scoring
            search_text = (res_json.get("coaching_feedback", "") + " " + res_json.get("executive_summary", "")).lower()
            
            for score_key in ["argument_quality", "persuasion", "logical_consistency", "rebuttal_quality", "rebuttal", "clarity", "vocabulary", "confidence"]:
                if score_key not in res_json:
                    match = re.search(rf"{score_key}[:\s\-]*(\d+)", search_text)
                    if match:
                        res_json[score_key] = int(match.group(1))
                    else:
                        res_json[score_key] = fallback_dict.get(score_key, 75) if fallback_dict else 75
                        
            return res_json
        except Exception as e:
            logger.error(f"[OpenAIService] call_llm_json failed: {e}")
            return fallback_dict or {}

    def evaluate_debate_argument(self, topic: str, opponent_statement: str, transcript_text: str,
                                 eye_contact_pct: float, voice_verdict: str, wpm: int) -> Dict[str, Any]:
        """
        Delegates debate evaluation to centralized GroqService.
        """
        return self.groq_service.evaluate_debate(
            topic=topic,
            opponent_statement=opponent_statement,
            transcript_text=transcript_text,
            eye_contact_pct=eye_contact_pct,
            voice_verdict=voice_verdict,
            wpm=wpm
        )

    def evaluate_session(self, session_type: str, topic: str, category: str, transcript: str,
                         voice_data: Optional[Dict[str, Any]] = None, face_data: Optional[Dict[str, Any]] = None) -> StructuredEvaluation:
        """
        Evaluates the speech recording transcript.
        """
        scores = {
            "overall_score": 75,
            "rating": "Good",
            "speech_analysis": {
                "speaking_rate": {"score": 75, "wpm": int(voice_data.get("speaking_rate", 130)) if voice_data else 130},
                "clarity": {"score": 75},
                "pronunciation": {"score": 75},
                "fluency": {"score": 75, "pause_count": 2},
                "fillers": {"score": 75, "filler_count": 2},
                "confidence": {"score": 75}
            },
            "body_language_analysis": {
                "eye_contact": {"score": int(face_data.get("eye_contact_percentage", 80)) if face_data else 80, "eye_contact_pct": float(face_data.get("eye_contact_percentage", 80)) if face_data else 80.0},
                "facial_expressions": {"score": 75},
                "posture": {"score": int(face_data.get("posture_stability", 80)) if face_data else 80},
                "gestures": {"score": 75},
                "head_movement": {"score": 75}
            },
            "communication_effectiveness": {
                "confidence": {"score": 75},
                "professionalism": {"score": 75},
                "engagement": {"score": 75},
                "persuasiveness": {"score": 75},
                "leadership_presence": {"score": 75}
            },
            "content_analysis": {
                "grammar_quality": 75,
                "vocabulary_richness": 75,
                "top_filler_words": {}
            }
        }
        res = self.groq_service.evaluate_jam(topic, category, transcript, scores)
        
        return StructuredEvaluation(
            summary=res.get("summary", ""),
            corrected_transcript=res.get("corrected_transcript", transcript),
            confidence=75,
            fluency=75,
            vocabulary=75,
            storytelling=75,
            leadership=75,
            persuasion=75,
            emotional_intelligence=75,
            clarity=75,
            energy_level=75,
            speaking_speed=75,
            eye_contact=75,
            posture=75,
            engagement=75,
            filler_words=75,
            profile_summary=res.get("executive_summary", "")[:100],
            strengths=res.get("strengths", []),
            weaknesses=res.get("areas_for_improvement", []),
            missed_opportunities=res.get("missing_concepts", []),
            suggestions=res.get("recommendations", []),
            expected_answer=res.get("expected_answer", ""),
            missing_concepts=res.get("missing_concepts", []),
            final_verdict="Good",
            filler_word_frequency={}
        )

    def generate_debate_opponent_argument(self, topic: str, opponent_difficulty: str, user_argument: Optional[str] = None) -> str:
        """
        Generates a counter-argument representing the AI opponent in the Debate Arena.
        """
        prompt = f"""
        You are an opposing debater in a friendly public arena.
        Debate Topic: "{topic}"
        Opponent Difficulty: {opponent_difficulty.upper()}
        
        User's Previous Argument (if any):
        \"\"\"{user_argument or "No argument yet. Open the debate with an initiating point."}\"\"\"
        
        Generate a sharp, respectful counter-argument or opening statement opposing the user.
        - Beginner: Simple arguments, clear statements, easy counter-points.
        - Intermediate: Well-reasoned arguments, structured structure.
        - Advanced: Hard to counter, uses logic, rhetorical questions, and analytical framing.
        - Expert: Flawless debate structure, extremely structured counterarguments, challenging questions.
        
        Keep your argument under 120 words. Speak directly as the opponent (do not include meta-text or intro notes).
        """
        return self.groq_service.call_groq_text(prompt, system_prompt="You are an expert debater opponent.")

    def generate_interview_question(self, role: str, round_type: str, question_history: List[str]) -> str:
        """
        Generates the next dynamic interview question in the Interview Simulator.
        """
        history_str = "\n".join([f"- {q}" for q in question_history]) if question_history else "No questions asked yet."
        
        prompt = f"""
        You are an elite interviewer for the following role:
        Role: {role}
        Round Type: {round_type}
        
        Previous Questions Asked:
        {history_str}
        
        Generate the next highly relevant interview question.
        - Technical: Ask coding, system design, architectural, or domain concepts.
        - Behavioral: Ask situational questions, conflict resolution, or leadership scenarios.
        - HR: Ask about culture fit, career aspirations, salary expectations.
        
        Output ONLY the question itself. Keep it concise, professional, and clear.
        """
        return self.groq_service.call_groq_text(prompt, system_prompt="You are a professional hiring manager.")
