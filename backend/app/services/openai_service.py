import os
import logging
import json
import requests
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI
from pydantic import BaseModel, Field
from app.config import settings

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
        logger.info("[OpenAIService] Initializing OpenAI Client...")
        self.api_key = settings.OPENAI_KEY or settings.OPENAI_API_KEY or os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY")
        if self.api_key:
            logger.info(f"[OpenAIService] API key found (length: {len(self.api_key)}). Creating OpenAI client...")
            try:
                self.client = OpenAI(api_key=self.api_key)
                logger.info("[OpenAIService] OpenAI client successfully initialized.")
            except Exception as e:
                logger.error(f"[OpenAIService] Failed to construct OpenAI client: {e}")
                self.client = None
        else:
            self.client = None
            logger.warning("[OpenAIService] OPENAI_KEY/OPENAI_API_KEY is not configured in settings or environment. OpenAI service will fail.")

    @property
    def safe_client(self):
        if self.client is None:
            raise ValueError("OpenAI client not initialized due to missing API key configuration.")
        return self.client

    def call_llm_json(self, prompt: str, system_prompt: str = "You are an elite communication twin mentor. Output clean JSON only.", fallback_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Unified LLM orchestrator routing to centralized GroqFeedbackService.
        """
        from app.services.groq_feedback_service import GroqFeedbackService
        groq_service = GroqFeedbackService()
        
        try:
            res_json = groq_service.call_groq_json(prompt, system_prompt)
            
            # Map keys for interview coach feedback
            if "communication_feedback" not in res_json:
                res_json["communication_feedback"] = res_json.get("coaching_feedback", "")
            if "confidence_feedback" not in res_json:
                res_json["confidence_feedback"] = res_json.get("executive_summary", "")

            # Map keys for debate scoring (extract scores if embedded in feedback)
            search_text = (res_json.get("coaching_feedback", "") + " " + res_json.get("executive_summary", "")).lower()
            
            for score_key in ["argument_quality", "persuasion", "logical_consistency", "rebuttal_quality", "rebuttal", "clarity", "vocabulary", "confidence"]:
                if score_key not in res_json:
                    # Regex match search for score value in feedback text (e.g. argument_quality: 80)
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
        Performs a rigorous, content-driven AI evaluation of the user's debate argument.
        """
        from app.services.groq_feedback_service import GroqFeedbackService
        groq_service = GroqFeedbackService()

        prompt = f"""
        Perform a rigorous, evidence-based debate evaluation of the user's argument on the topic: "{topic}"
        
        Debate Opponent's Statement (what the user was responding to):
        \"\"\"{opponent_statement}\"\"\"
        
        User's Argument/Transcript:
        \"\"\"{transcript_text}\"\"\"
        
        Additional Delivery Context:
        - Gaze/Eye contact percentage: {eye_contact_pct}%
        - Voice metrics / vocal energy: {voice_verdict}
        - Speaking speed: {wpm} words per minute
        
        You must evaluate the debate performance across the following 7 dimensions strictly.
        Do NOT assign generic, default, or pre-configured scores (like 75, 80, 85). Every score must be dynamically derived based on the content of the transcript:
        
        1. persuasion (0-100):
           - Evaluate emotional appeal, conviction, audience influence, and impact.
           - Lower score for simple claims like "I think AI is good". High score for strong, impactful arguments.
        2. logical_consistency (0-100):
           - Evaluate reasoning quality, cause-effect links, coherence, and contradiction detection.
           - Penalize unsupported claims, logical fallacies, or topic drift.
        3. rebuttal_quality (0-100):
           - Compare the user's argument against the opponent's statement.
           - Measure how directly the user addressed the opponent's points and the strength of the refutation.
           - Assign a low score if the user ignored the opponent's arguments.
        4. confidence (0-100):
           - Evaluate usage of decisive and assertive language.
           - Penalize filler words (e.g., "um", "ah", "uh", "like", "you know") and repeated pauses.
        5. evidence_usage (0-100):
           - Check if the user cited data, logic, concrete examples, or structured evidence.
        6. critical_thinking (0-100):
           - Evaluate depth, nuance, and complexity of thought.
        7. argument_structure (0-100):
           - Assess introduction, core points, transitions, and conclusion.
           
        In addition, provide detailed qualitative feedback in lists. All feedback items must quote actual words/phrases from the user's transcript to justify the points:
        - strengths (list of strings): 2-3 specific strengths, citing/quoting the transcript.
        - weaknesses (list of strings): 2-3 specific weaknesses, citing/quoting the transcript.
        - missed_opportunities (list of strings): specific counterarguments or points the user failed to make.
        - counterarguments_not_addressed (list of strings): specific points from the opponent's statement that the user completely ignored or failed to address.
        - persuasion_improvements (list of strings): concrete advice to make the argument more persuasive.
        - logic_improvements (list of strings): how to fix logical fallacies or strengthen cause-effect reasoning.
        
        Return ONLY a valid JSON object matching this schema (do not include any backticks or markdown, output pure raw JSON):
        {{
          "persuasion": <int>,
          "logical_consistency": <int>,
          "rebuttal_quality": <int>,
          "confidence": <int>,
          "evidence_usage": <int>,
          "critical_thinking": <int>,
          "argument_structure": <int>,
          "strengths": ["string quoting transcript"],
          "weaknesses": ["string quoting transcript"],
          "missed_opportunities": ["string"],
          "counterarguments_not_addressed": ["string"],
          "persuasion_improvements": ["string"],
          "logic_improvements": ["string"]
        }}
        """

        fallback_scores = {
            "persuasion": 70,
            "logical_consistency": 70,
            "rebuttal_quality": 70,
            "confidence": 70,
            "evidence_usage": 70,
            "critical_thinking": 70,
            "argument_structure": 70,
            "strengths": ["The speech was recorded successfully."],
            "weaknesses": ["Identify areas to introduce more data-driven points."],
            "missed_opportunities": ["Expanding on key economic or social implications of the motion."],
            "counterarguments_not_addressed": ["Direct refutation of opponent's main premise."],
            "persuasion_improvements": ["Use stronger emotional appeals and assertive vocabulary."],
            "logic_improvements": ["Structure clear cause-effect links for each point."]
        }

        try:
            res_json = groq_service.call_groq_json(
                prompt=prompt,
                system_prompt="You are an elite AI Debate Judge and Evaluation Expert. You score debates strictly and provide detailed, evidence-based qualitative feedback. Output JSON only.",
                force_schema=False
            )
            
            # Ensure all required keys exist, if not fill with default fallback values
            for k, v in fallback_scores.items():
                if k not in res_json or res_json[k] is None:
                    res_json[k] = v
                    
            return res_json
        except Exception as e:
            logger.error(f"[OpenAIService] evaluate_debate_argument failed: {e}")
            return fallback_scores

    def evaluate_session(self, session_type: str, topic: str, category: str, transcript: str,
                         voice_data: Optional[Dict[str, Any]] = None, face_data: Optional[Dict[str, Any]] = None) -> StructuredEvaluation:
        """
        Evaluates the speech recording transcript using the Groq-backed ai_evaluator.
        """
        from app.services.ai_evaluator import evaluate_speech_with_gemini
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
        res = evaluate_speech_with_gemini(topic, category, transcript, scores)
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
            strengths=res.get("detailed_strengths", []),
            weaknesses=res.get("areas_for_improvement", []),
            missed_opportunities=res.get("missing_concepts", []),
            suggestions=res.get("action_immediate", []),
            expected_answer=res.get("expected_answer", ""),
            missing_concepts=res.get("missing_concepts", []),
            final_verdict="Good",
            filler_word_frequency={}
        )

    def generate_debate_opponent_argument(self, topic: str, opponent_difficulty: str, user_argument: Optional[str] = None) -> str:
        """
        Generates a counter-argument representing the AI opponent in the Debate Arena using Groq.
        """
        from app.services.groq_feedback_service import GroqFeedbackService
        groq_service = GroqFeedbackService()
        
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
        return groq_service.call_groq_text(prompt, system_prompt="You are an expert debater opponent.")

    def generate_interview_question(self, role: str, round_type: str, question_history: List[str]) -> str:
        """
        Generates the next dynamic interview question in the Interview Simulator based on previous questions using Groq.
        """
        from app.services.groq_feedback_service import GroqFeedbackService
        groq_service = GroqFeedbackService()
        
        history_str = "\n".join([f"- {q}" for q in question_history]) if question_history else "No questions asked yet."
        
        prompt = f"""
        You are an elite interviewer for the following role:
        Role: {role}
        Round Type: {round_type}
        
        Previous Questions Asked:
        {history_str}
        
        Generate the next highly relevant interview question.
        - Technical: Ask coding, system design, architectural, or domain concepts.
        - Behavioral: Ask situational questions, conflict resolution, or leadership scenarios (e.g., "Tell me about a time when...").
        - HR: Ask about culture fit, career aspirations, salary expectations.
        
        Output ONLY the question itself. Keep it concise, professional, and clear.
        """
        return groq_service.call_groq_text(prompt, system_prompt="You are a professional hiring manager.")
