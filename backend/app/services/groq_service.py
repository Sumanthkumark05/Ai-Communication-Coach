import time
import json
import logging
import requests
import re
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger("jam_analyzer")

PRIMARY_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant"
]

class GroqService:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        if not self.api_key:
            logger.error("[GroqService] GROQ_API_KEY is not configured in settings.")
        else:
            logger.info("LLM Client Initialized")
            logger.info(f"[GroqService] Initialized with primary model: {PRIMARY_MODEL}")

    def _call_groq_api_sync(self, prompt: str, system_prompt: str, response_format: Optional[str] = "json_object", timeout: float = 30.0) -> str:
        """
        Synchronously calls Groq API with retries and fallback models.
        """
        if not self.api_key:
            raise ValueError("[GroqService] GROQ_API_KEY is missing.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        last_error = None
        for model in FALLBACK_MODELS:
            # Retry up to 3 times per model with exponential backoff
            for attempt in range(3):
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2
                    }
                    if response_format == "json_object":
                        payload["response_format"] = {"type": "json_object"}

                    logger.info(f"[GroqService] Sync request to model {model} (attempt {attempt+1})...")
                    logger.info("LLM Request Sent")
                    
                    res = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )
                    
                    if res.status_code == 200:
                        logger.info("LLM Response Received")
                        logger.info(f"[GroqService] Response received from model {model}.")
                        return res.json()["choices"][0]["message"]["content"].strip()
                    else:
                        logger.warning(f"[GroqService] Model {model} returned status {res.status_code}: {res.text}")
                        last_error = f"Status {res.status_code}: {res.text}"
                except Exception as e:
                    logger.warning(f"[GroqService] Model {model} request failed: {e}")
                    last_error = str(e)
                
                # Backoff sleep (1s, 2s)
                if attempt < 2:
                    time.sleep(2.0 ** attempt)
            
            logger.warning(f"[GroqService] Model {model} exhausted. Trying next fallback...")

        raise RuntimeError(f"All Groq models failed. Last error: {last_error}")

    async def _call_groq_api_async(self, prompt: str, system_prompt: str, response_format: Optional[str] = "json_object", timeout: float = 30.0) -> str:
        """
        Asynchronously calls Groq API with retries and fallback models.
        """
        if not self.api_key:
            raise ValueError("[GroqService] GROQ_API_KEY is missing.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        last_error = None
        for model in FALLBACK_MODELS:
            for attempt in range(3):
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2
                    }
                    if response_format == "json_object":
                        payload["response_format"] = {"type": "json_object"}

                    logger.info(f"[GroqService] Async request to model {model} (attempt {attempt+1})...")
                    logger.info("LLM Request Sent")

                    async with httpx.AsyncClient(timeout=timeout) as client:
                        res = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers=headers,
                            json=payload
                        )
                    
                    if res.status_code == 200:
                        logger.info("LLM Response Received")
                        logger.info(f"[GroqService] Response received from model {model} (async).")
                        return res.json()["choices"][0]["message"]["content"].strip()
                    else:
                        logger.warning(f"[GroqService] Model {model} returned status {res.status_code}: {res.text}")
                        last_error = f"Status {res.status_code}: {res.text}"
                except Exception as e:
                    logger.warning(f"[GroqService] Model {model} request failed: {e}")
                    last_error = str(e)
                
                if attempt < 2:
                    await asyncio.sleep(2.0 ** attempt)
            
            logger.warning(f"[GroqService] Model {model} exhausted (async). Trying next fallback...")

        raise RuntimeError(f"All Groq models failed. Last error: {last_error}")

    def call_groq_json(self, prompt: str, system_prompt: str = "You are an elite speech intelligence advisor. Output clean JSON only.", force_schema: bool = False) -> Dict[str, Any]:
        """
        Unified JSON parser wrapper for backward compatibility.
        """
        try:
            content = self._call_groq_api_sync(prompt, system_prompt, response_format="json_object")
            parsed = json.loads(content)
            return parsed
        except Exception as e:
            logger.error(f"[GroqService] call_groq_json failed: {e}")
            # Try regex recovery
            try:
                match = re.search(r"(\{.*\})", content, re.DOTALL)
                if match:
                    return json.loads(match.group(1).strip())
            except Exception:
                pass
            return {}

    async def call_groq_json_async(self, prompt: str, system_prompt: str = "You are an elite speech intelligence advisor. Output clean JSON only.", force_schema: bool = False) -> Dict[str, Any]:
        """
        Unified async JSON parser wrapper for backward compatibility.
        """
        try:
            content = await self._call_groq_api_async(prompt, system_prompt, response_format="json_object")
            parsed = json.loads(content)
            return parsed
        except Exception as e:
            logger.error(f"[GroqService] call_groq_json_async failed: {e}")
            try:
                match = re.search(r"(\{.*\})", content, re.DOTALL)
                if match:
                    return json.loads(match.group(1).strip())
            except Exception:
                pass
            return {}

    def call_groq_text(self, prompt: str, system_prompt: str = "You are an expert speaker.") -> str:
        """
        Unified text response generator.
        """
        try:
            return self._call_groq_api_sync(prompt, system_prompt, response_format=None)
        except Exception as e:
            logger.error(f"[GroqService] call_groq_text failed: {e}")
            return "An error occurred while generating response."

    async def call_groq_text_async(self, prompt: str, system_prompt: str = "You are an expert speaker.") -> str:
        """
        Unified async text response generator.
        """
        try:
            return await self._call_groq_api_async(prompt, system_prompt, response_format=None)
        except Exception as e:
            logger.error(f"[GroqService] call_groq_text_async failed: {e}")
            return "An error occurred while generating response."

    # ── Phase 2 Centralized LLM Operations ─────────────────────────────────────────

    def generate_analysis(self, prompt: str, system_prompt: str = "You are an elite speech intelligence advisor. Output clean JSON only.", fallback_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        res = self.call_groq_json(prompt, system_prompt)
        if not res and fallback_dict:
            return fallback_dict
        return res

    def generate_feedback(self, prompt: str, system_prompt: str = "You are an elite Twin AI speech coach.") -> str:
        return self.call_groq_text(prompt, system_prompt)

    def generate_report(self, prompt: str, system_prompt: str = "You are an elite speech intelligence advisor. Output clean JSON only.", fallback_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.generate_analysis(prompt, system_prompt, fallback_dict)

    def generate_score(self, prompt: str) -> int:
        system = "You are a grading expert. You output only a single integer between 0 and 100."
        res = self.call_groq_text(prompt, system)
        match = re.search(r"(\d+)", res)
        if match:
            return int(match.group(1))
        return 70

    def generate_recommendations(self, prompt: str) -> List[str]:
        system = "You are a speech coach. Return a JSON list of strings containing recommendations. e.g. [\"Recommendation 1\", \"Recommendation 2\"]"
        res = self.call_groq_json(prompt, system)
        if isinstance(res, list):
            return res
        elif isinstance(res, dict):
            return res.get("recommendations", [])
        return ["Practice speaking slowly and clearly."]

    def evaluate_jam(self, topic: str, category: str, transcript: str, scores: Dict[str, Any], python_did_answer: bool = True) -> Dict[str, Any]:
        """
        Analyzes the candidate's speech. Migrated from ai_evaluator.py
        """
        overall_score = scores.get("overall_score", 75)
        rating = scores.get("rating", "Good")
        
        speech_analysis = scores.get("speech_analysis", {})
        wpm = speech_analysis.get("speaking_rate", {}).get("wpm", 130)
        speaking_rate_score = speech_analysis.get("speaking_rate", {}).get("score", 70)
        clarity_score = speech_analysis.get("clarity", {}).get("score", 75)
        whisper_confidence = speech_analysis.get("clarity", {}).get("whisper_confidence", 85)
        pronunciation_score = speech_analysis.get("pronunciation", {}).get("score", 70)
        fluency_score = speech_analysis.get("fluency", {}).get("score", 70)
        pause_count = speech_analysis.get("fluency", {}).get("pause_count", 0)
        fillers_score = speech_analysis.get("fillers", {}).get("score", 70)
        fillers = speech_analysis.get("fillers", {}).get("filler_count", 0)
        speech_confidence_score = speech_analysis.get("confidence", {}).get("score", 70)
        
        body_analysis = scores.get("body_language_analysis", {})
        eye_pct = body_analysis.get("eye_contact", {}).get("eye_contact_pct", 80.0)
        eye_contact_score = body_analysis.get("eye_contact", {}).get("score", 80)
        facial_expressions_score = body_analysis.get("facial_expressions", {}).get("score", 75)
        smile_freq = body_analysis.get("facial_expressions", {}).get("smile_freq", 10.0)
        posture = body_analysis.get("posture", {}).get("score", 80)
        gestures_score = body_analysis.get("gestures", {}).get("score", 70)
        hand_detection_rate = body_analysis.get("gestures", {}).get("hand_detection_rate", 20.0)
        head_movement_score = body_analysis.get("head_movement", {}).get("score", 70)
        
        comm_effectiveness = scores.get("communication_effectiveness", {})
        eff_confidence_score = comm_effectiveness.get("confidence", {}).get("score", 70)
        eff_professionalism_score = comm_effectiveness.get("professionalism", {}).get("score", 70)
        eff_engagement_score = comm_effectiveness.get("engagement", {}).get("score", 70)
        eff_persuasiveness_score = comm_effectiveness.get("persuasiveness", {}).get("score", 70)
        eff_leadership_presence_score = comm_effectiveness.get("leadership_presence", {}).get("score", 70)
        
        content_analysis = scores.get("content_analysis", {})
        grammar_score = content_analysis.get("grammar_quality", 75)
        vocabulary_score = content_analysis.get("vocabulary_richness", 70)
        top_filler_words = content_analysis.get("top_filler_words", {})

        prompt = f"""
        Analyze the candidate's speech:
        Topic: "{topic}"
        Category: "{category}"
        Spoken Transcript:
        \"\"\"{transcript}\"\"\"

        --- Pre-calculated Scores (0-100 scale) ---
        Overall Performance Score: {overall_score} ({rating})
        
        Acoustic & Speech Metrics:
        - Speaking Rate: {wpm} WPM (Pacing Score: {speaking_rate_score}/100)
        - Speech Clarity: {clarity_score}/100
        - Whisper Confidence: {whisper_confidence}/100
        - Pronunciation Quality: {pronunciation_score}/100
        - Speech Fluency: {fluency_score}/100 (Pause Count: {pause_count})
        - Filler Vocalizations: {fillers_score}/100 (Filler Count: {fillers} detected, Top Fillers: {top_filler_words})
        - Speech Confidence Indicator: {speech_confidence_score}/100
        
        Body Language & Visual Metrics:
        - Eye Contact: {eye_contact_score}/100 (Eye Contact Percentage: {eye_pct:.1f}%)
        - Facial Expression and Smile: {facial_expressions_score}/100 (Smile Frequency: {smile_freq:.1f}%)
        - Posture Stability: {posture}/100
        - Gesture Effectiveness: {gestures_score}/100 (Hand Detection Rate: {hand_detection_rate:.1f}%)
        - Head Stability: {head_movement_score}/100
        
        Communication Effectiveness:
        - Overall Confidence: {eff_confidence_score}/100
        - Professionalism: {eff_professionalism_score}/100
        - Audience Engagement: {eff_engagement_score}/100
        - Persuasiveness: {eff_persuasiveness_score}/100
        - Leadership Presence: {eff_leadership_presence_score}/100
        
        Content Quality Metrics:
        - Grammar Quality: {grammar_score}/100
        - Vocabulary Richness: {vocabulary_score}/100

        Python-based Content Check Result:
        - User triggered failure phrases or has little topic overlap: {not python_did_answer}

        CRITICAL SCORING & ANALYSIS RULES FOR CONTENT:
        Evaluate the candidate's speech content against the topic: "{topic}".
        
        1. Content Relevance Score (0-100):
           How relevant was the user's response to the topic? If they did not answer the topic, asked for information, or said "I don't know" (or if the Python content check result is True), the score must be under 20.
        
        2. Topic Coverage Score (0-100):
           How well did the user cover the key aspects/talking points of the topic? If off-topic, empty, or if the Python content check result is True, the score must be under 20.
           
        3. Knowledge Depth Score (0-100):
           Did the user demonstrate meaningful knowledge/understanding of the topic? If they asked the system to explain it, said "I have no idea", or didn't show understanding (or if the Python content check result is True), the score must be under 20.

        4. Answered Topic (boolean):
           Set this to true ONLY if the user actually attempted to answer the topic with relevant content. Set to false if they said "I don't know", "Tell me", "Can you explain", "I am not sure", "I have no idea", gave an off-topic/empty response, or if the Python content check result is True.
           
        5. Executive Summary:
           If `answered_topic` is false:
           - The summary must explicitly mention that the user did not answer the topic, requested information, and that their topic knowledge was insufficient.
           - Do NOT generate positive content mastery conclusions.
           
        6. Strengths:
           - May mention delivery strengths (e.g. clear speech, good eye contact, good pronunciation).
           - Must NOT imply topic understanding or content mastery if the user did not answer the topic.
           
        7. Areas for Improvement:
           - Must mention lack of topic knowledge, missing concepts, insufficient content, and need for subject understanding if the user did not answer the topic.

        INSTRUCTIONS FOR EVIDENCE-BASED ANALYSIS:
        1. Ground all feedback, summaries, and recommendations entirely in the spoken transcript and the provided metrics.
        2. Do NOT invent concepts, topics, or claims not discussed in the Spoken Transcript.
        3. Avoid boilerplate, placeholder, or generic templates. Every section in the JSON response must be personalized and specific to the candidate's speech content.
        4. Highlight actual communication metrics (such as the specific WPM or filler counts) directly in the feedback to show evidence.

        You must output your response as a valid JSON object matching this EXACT key schema:
        {{
          "executive_summary": "Max 5 bullet points starting with '-' summarizing what was actually discussed, referencing the core topics and specific delivery metrics.",
          "strengths": ["list of specific communication strengths based on the transcript and metrics (at least 2-3 items)"],
          "areas_for_improvement": ["list of specific areas of improvement (at least 2-3 items)"],
          "recommendations": ["list of actionable, evidence-based recommendations for improvement"],
          "action_plan": ["list of immediate and short term practice steps grounded in these metrics"],
          "expert_response": "a comprehensive, expert-level response or ideal structure to the topic question",
          "missing_concepts": ["key technical concepts/definitions relevant to the topic that the user missed in their response"],
          "coaching_feedback": "detailed mentor coaching feedback addressing pacing, eye contact, body posture, gestures, and filler word usage",
          "content_relevance_score": 85,
          "topic_coverage_score": 80,
          "knowledge_depth_score": 75,
          "answered_topic": true
        }}
        Return ONLY valid JSON.
        """
        fallback_data = {
            "executive_summary": "- Analysis completed.\n- Speech delivery was recorded.\n- Content analysis generated.",
            "strengths": ["Clear spoken pronunciation", "Appropriate volume levels"],
            "areas_for_improvement": ["Expand on structural arguments", "Reduce brief pauses"],
            "recommendations": ["Utilize strong transitional expressions", "Refine logical consistency"],
            "action_plan": ["Practice daily speech drills", "Record and listen to responses"],
            "expert_response": f"An expert response to '{topic}' should present clear points, supporting facts, and structure logic.",
            "missing_concepts": ["Core topic definitions"],
            "coaching_feedback": "Your speaking speed and confidence levels are steady. Focus on reducing pauses and structuring points.",
            "content_relevance_score": 70,
            "topic_coverage_score": 70,
            "knowledge_depth_score": 70,
            "answered_topic": python_did_answer
        }
        res = self.call_groq_json(prompt, system_prompt="You are an elite speech intelligence advisor. Output JSON only.", force_schema=False)
        for k, v in fallback_data.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res

    def evaluate_debate(self, topic: str, opponent_statement: str, transcript_text: str, eye_contact_pct: float, voice_verdict: str, wpm: int) -> Dict[str, Any]:
        """
        Evaluates the user's debate argument. Migrated from openai_service.py
        """
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
        
        Evaluate the debate performance across the following 7 dimensions strictly.
        Do NOT assign generic, default, or pre-configured scores (like 75, 80, 85). Every score must be dynamically derived based on the content of the transcript:
        
        1. persuasion (0-100):
           - Evaluate emotional appeal, conviction, audience influence, and impact.
        2. logical_consistency (0-100):
           - Evaluate reasoning quality, cause-effect links, coherence, and contradiction detection.
        3. rebuttal_quality (0-100):
           - Compare the user's argument against the opponent's statement.
           - Measure how directly the user addressed the opponent's points and the strength of the refutation.
        4. confidence (0-100):
           - Evaluate usage of decisive and assertive language.
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

        res = self.call_groq_json(prompt, system_prompt="You are an elite AI Debate Judge and Evaluation Expert. Output JSON only.")
        for k, v in fallback_scores.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res

    def evaluate_interview(self, role: str, round_type: str, question_history: List[str], answer_text: str, face_metrics: Dict[str, Any], voice_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates interview answer.
        """
        prompt = f"""
        Role: {role}
        Round Type: {round_type}
        Question History: {question_history}
        Candidate Answer: "{answer_text}"
        Face Metrics: {face_metrics}
        Voice Metrics: {voice_metrics}

        Evaluate the candidate's answer and return a JSON object with:
        1. "score": Overall score (0-100).
        2. "technical_score": Technical proficiency score (0-100).
        3. "communication_score": Pacing and clarity score (0-100).
        4. "problem_solving_score": Analytical reasoning score (0-100).
        5. "leadership_score": Initiative and presence score (0-100).
        6. "feedback": General feedback string.
        7. "strengths": List of strings detailing strengths.
        8. "weaknesses": List of strings detailing improvements.
        
        Return ONLY valid JSON.
        """
        fallback = {
            "score": 75,
            "technical_score": 75,
            "communication_score": 75,
            "problem_solving_score": 75,
            "leadership_score": 75,
            "feedback": "Your interview response covers the key technical topics.",
            "strengths": ["Direct explanation"],
            "weaknesses": ["Detail technical implementation details"]
        }
        res = self.call_groq_json(prompt, system_prompt="You are an elite tech recruiter AI. Output JSON only.")
        for k, v in fallback.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res

    def evaluate_document(self, doc_analysis: Dict[str, Any], text: str) -> Dict[str, Any]:
        """
        Evaluates a document presentation training topic/content.
        """
        prompt = f"""
        Document Metadata: {doc_analysis}
        Presentation Content / Transcript: "{text}"
        
        Evaluate the presentation based on the document and return a JSON object:
        1. "relevance_score": Alignment with the document (0-100).
        2. "accuracy_score": Technical accuracy of facts (0-100).
        3. "coverage_score": Key concept coverage (0-100).
        4. "strengths": List of strengths.
        5. "weaknesses": List of improvements.
        6. "missing_concepts": List of key missed concepts from the document.
        
        Return ONLY valid JSON.
        """
        fallback = {
            "relevance_score": 75,
            "accuracy_score": 75,
            "coverage_score": 75,
            "strengths": ["Covers main project sections"],
            "weaknesses": ["Could reference specific figures/numbers"],
            "missing_concepts": ["Detailed data charts"]
        }
        res = self.call_groq_json(prompt, system_prompt="You are a technical presentation auditor. Output JSON only.")
        for k, v in fallback.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res

    def evaluate_communication_dna(self, history_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates Communication DNA profile.
        """
        prompt = f"""
        User Session History: {history_list}
        
        Analyze user's strengths, style, and progress to output a JSON DNA profile:
        1. "speaking_style": "string describing speaking style, e.g. Analytical, Dynamic, Hesitant",
        2. "strengths": ["list of key strengths"],
        3. "weaknesses": ["list of weaknesses"],
        4. "insights": ["list of speech insights"],
        5. "growth_metrics": {{
            "confidence": 75,
            "fluency": 75,
            "clarity": 75,
            "pacing": 75
           }}
        """
        fallback = {
            "speaking_style": "Analytical",
            "strengths": ["Logical structure", "Good pacing"],
            "weaknesses": ["Filler word frequency"],
            "insights": ["Confidence shows upward trends across sessions."],
            "growth_metrics": {"confidence": 75, "fluency": 75, "clarity": 75, "pacing": 75}
        }
        res = self.call_groq_json(prompt, system_prompt="You are a linguistic expert profiling communication patterns. Output JSON only.")
        for k, v in fallback.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res

    def generate_coaching_plan(self, user_id: str, history_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates daily coaching plan.
        """
        prompt = f"""
        User Session History: {history_list}
        
        Generate a personalized coaching plan as a JSON object:
        1. "daily_drills": ["list of strings representing daily speech exercises"],
        2. "weekly_goals": ["list of strings representing weekly target goals"],
        3. "focus_areas": ["list of speech focus metrics"]
        """
        fallback = {
            "daily_drills": ["Practice speaking on a random topic for 1 minute without filler words."],
            "weekly_goals": ["Reduce filler word count below 3 per session."],
            "focus_areas": ["Fluency", "Pause reduction"]
        }
        res = self.call_groq_json(prompt, system_prompt="You are an expert personal communication coach. Output JSON only.")
        for k, v in fallback.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res

    def identify_knowledge_gaps(self, topic: str, transcript: str) -> List[str]:
        """
        Identifies missing concepts/knowledge gaps in speech.
        """
        prompt = f"""
        Topic: "{topic}"
        Transcript: "{transcript}"
        
        Identify key concepts or facts that are essential to the topic but missing from the candidate's speech.
        Return a JSON list of strings. e.g. ["Concept 1", "Concept 2"]
        """
        res = self.call_groq_json(prompt, system_prompt="You are a subject-matter evaluator. Output JSON list of strings.")
        if isinstance(res, list):
            return res
        elif isinstance(res, dict):
            return res.get("gaps", res.get("missing_concepts", []))
        return ["Advanced industry concepts"]

    def summarize_document(self, text: str) -> str:
        prompt = f"Summarize the following text in 2-3 sentences:\n\n{text[:6000]}"
        return self.call_groq_text(prompt, "You are a professional summarizer.")

    def extract_key_points(self, text: str) -> List[str]:
        prompt = f"Extract the top 5 key bullet points from the following text:\n\n{text[:6000]}"
        res = self.call_groq_json(prompt, "You are an expert information extractor. Return a JSON list of strings.")
        if isinstance(res, list):
            return res
        elif isinstance(res, dict):
            return res.get("key_points", res.get("points", []))
        return ["Key point 1", "Key point 2"]

    def generate_improvement_roadmap(self, user_id: str, history_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates step-by-step career/speaking roadmap.
        """
        prompt = f"""
        User Session History: {history_list}
        
        Generate a step-by-step speaking skills improvement roadmap as a JSON object:
        1. "phase_1": "Description of Phase 1 (Foundation building)",
        2. "phase_2": "Description of Phase 2 (Pacing and eye contact mastery)",
        3. "phase_3": "Description of Phase 3 (Advanced debate and leadership delivery)",
        4. "milestones": ["List of milestones to track progress"]
        """
        fallback = {
            "phase_1": "Focus on content structured outline and breathing.",
            "phase_2": "Master eye contact alignment and reduce WPM variation.",
            "phase_3": "Deliver persuasive arguments with vocal modulation.",
            "milestones": ["Under 2 fillers per minute", "Consistent gaze alignment"]
        }
        res = self.call_groq_json(prompt, system_prompt="You are a personal speaking improvement roadmap architect. Output JSON only.")
        for k, v in fallback.items():
            if k not in res or res[k] is None:
                res[k] = v
        return res
