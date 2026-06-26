import logging
import json
import requests
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.config import settings

logger = logging.getLogger("jam_analyzer")

class GroqReportOutput(BaseModel):
    executive_summary: str = Field(description="Max 5 concise bullet points covering key strengths, major weaknesses, and overall assessment.")
    
    # Speech analysis reasons/suggestions
    speech_rate_reason: str = Field(description="Reason for speaking rate score.")
    speech_rate_suggestion: str = Field(description="Actionable suggestion to improve speaking rate.")
    
    speech_clarity_reason: str = Field(description="Reason for clarity score.")
    speech_clarity_suggestion: str = Field(description="Actionable suggestion to improve clarity.")
    
    speech_pronunciation_reason: str = Field(description="Reason for pronunciation score.")
    speech_pronunciation_suggestion: str = Field(description="Actionable suggestion to improve pronunciation.")
    
    speech_fluency_reason: str = Field(description="Reason for fluency score.")
    speech_fluency_suggestion: str = Field(description="Actionable suggestion to improve fluency.")
    
    speech_fillers_reason: str = Field(description="Reason for fillers score.")
    speech_fillers_suggestion: str = Field(description="Actionable suggestion to reduce fillers.")
    
    speech_confidence_reason: str = Field(description="Reason for speech confidence score.")
    speech_confidence_suggestion: str = Field(description="Actionable suggestion to improve confidence.")
    
    # Communication effectiveness reasons/suggestions
    effectiveness_confidence_reason: str = Field(description="Reason for communication confidence score.")
    effectiveness_confidence_recommendation: str = Field(description="Actionable recommendation to improve communication confidence.")
    
    effectiveness_professionalism_reason: str = Field(description="Reason for professionalism score.")
    effectiveness_professionalism_recommendation: str = Field(description="Actionable recommendation to improve professionalism.")
    
    effectiveness_engagement_reason: str = Field(description="Reason for audience engagement score.")
    effectiveness_engagement_recommendation: str = Field(description="Actionable recommendation to improve audience engagement.")
    
    effectiveness_persuasiveness_reason: str = Field(description="Reason for persuasiveness score.")
    effectiveness_persuasiveness_recommendation: str = Field(description="Actionable recommendation to improve persuasiveness.")
    
    effectiveness_leadership_reason: str = Field(description="Reason for leadership presence score.")
    effectiveness_leadership_recommendation: str = Field(description="Actionable recommendation to improve leadership presence.")
    
    # Content relevance analysis
    content_relevance_reason: str = Field(description="Reason for content relevance score.")
    content_relevance_suggestion: str = Field(description="Actionable suggestion to improve content relevance.")
    
    # Roadmap actions
    action_immediate: List[str] = Field(description="List of 2-3 immediate action points.")
    action_short_term: List[str] = Field(description="List of 2-3 short-term action points.")
    action_long_term: List[str] = Field(description="List of 2-3 long-term action points.")
    
    expected_answer: str = Field(description="An ideal, comprehensive, expert-level response to the topic question.")
    # NOTE: corrected_transcript is intentionally NOT a Groq output field.
    # The transcript must always remain the raw Whisper-generated text and must
    # never be rewritten, paraphrased, or summarized by the LLM.
    summary: str = Field(description="Concise summary of candidate spoken content.")
    missing_concepts: List[str] = Field(description="List of key technical concepts/definitions missing from candidate response.")

def get_default_report_fallback(topic: str, category: str, transcript: str, scores: Dict[str, Any]) -> Dict[str, Any]:
    wpm = scores["speech_analysis"]["speaking_rate"]["wpm"]
    fillers = scores["speech_analysis"]["fillers"]["filler_count"]
    eye_pct = scores["body_language_analysis"]["eye_contact"]["eye_contact_pct"]
    posture = scores["body_language_analysis"]["posture"]["score"]
    
    summary_bullets = [
        f"Delivered a speech on the topic '{topic}' under category '{category}'.",
        f"Maintained a speaking pace of {wpm} WPM with {fillers} filler word occurrences.",
        f"Visual eye contact was recorded at {eye_pct:.1f}% with posture rating at {posture}%."
    ]
    
    strengths = []
    improvements = []
    
    if 120 <= wpm <= 150:
        strengths.append("Maintained an optimal, highly conversational speaking rate.")
    else:
        improvements.append("Adjust speaking rate closer to the conversational 135 WPM threshold.")
        
    if eye_pct >= 70:
        strengths.append("Established consistent eye contact directly with the camera lens.")
    else:
        improvements.append("Focus gaze forward on the camera lens to project confidence.")
        
    if fillers <= 3:
        strengths.append("Extremely fluent transition phrasing with minimal filler vocalizations.")
    else:
        improvements.append("Reduce vocal filler words by replacing them with silent transition pauses.")

    if len(strengths) < 2:
        strengths.append("Earnest delivery and structural clarity.")
        strengths.append("Addressed the general talking points of the category.")
    if len(improvements) < 2:
        improvements.append("Practice posture stabilization drills.")
        improvements.append("Incorporate rhetorical structural patterns.")

    return {
        "executive_summary": "\n".join([f"- {b}" for b in summary_bullets]),
        "speech_rate_reason": "Pacing was conversational." if 120 <= wpm <= 150 else "Speaking pace deviated from optimal range.",
        "speech_rate_suggestion": "Maintain this comfortable rhythm." if 120 <= wpm <= 150 else "Slow down or speed up practice drills.",
        "speech_clarity_reason": "Transcription was successfully mapped without severe audio dropouts.",
        "speech_clarity_suggestion": "Ensure consistent distance from the microphone.",
        "speech_pronunciation_reason": "Enunciation was clean and words were transcribed successfully.",
        "speech_pronunciation_suggestion": "Speak slowly on multi-syllabic terms.",
        "speech_fluency_reason": "Audible flow was generally smooth.",
        "speech_fluency_suggestion": "Practice structural outlines to reduce hesitation.",
        "speech_fillers_reason": f"Filler word frequency was recorded at {fillers} items.",
        "speech_fillers_suggestion": "Practice locking your mouth during transition gaps.",
        "speech_confidence_reason": "Vocal pitch and loudness indicators remained stable.",
        "speech_confidence_suggestion": "Practice deep breathing prior to recording.",
        "body_eye_contact_evidence": f"Looked directly at the camera {eye_pct:.1f}% of the duration.",
        "body_eye_contact_suggestion": "Anchor visual focus next to the camera lens.",
        "body_expressions_evidence": "Facial movements matched standard active listening patterns.",
        "body_expressions_suggestion": "Utilize warm smiles at opening and closing points.",
        "body_posture_evidence": f"Maintained stable posture alignment scoring {posture}%.",
        "body_posture_suggestion": "Align shoulders and check camera angle height.",
        "body_gestures_evidence": "Gestures were subtle or limited.",
        "body_gestures_suggestion": "Raise hands to chest level during emphasis points.",
        "body_head_movement_evidence": "Head roll and tilt stayed within stable parameters.",
        "body_head_movement_suggestion": "Keep chin level with the camera horizontal frame line.",
        "effectiveness_confidence_reason": "Measurable delivery signals reflect a balanced confidence style.",
        "effectiveness_confidence_recommendation": "Vocalize with clear, assertive projection.",
        "effectiveness_professionalism_reason": "Vocabulary choices and posture alignment were professional.",
        "effectiveness_professionalism_recommendation": "Adopt structured transition terms.",
        "effectiveness_engagement_reason": "Eye contact and expressions kept audience focus.",
        "effectiveness_engagement_recommendation": "Vary tempo dynamically during key sentences.",
        "effectiveness_persuasiveness_reason": "Core vocabulary arguments showed basic logic flow.",
        "effectiveness_persuasiveness_recommendation": "Present claims supported by evidence.",
        "effectiveness_leadership_reason": "Command of physical presence and head posture was positive.",
        "effectiveness_leadership_recommendation": "Deliver transition statements with structural pauses.",
        "content_grammar_quality": "Grammatical structure was simple and direct.",
        "content_vocabulary_richness": "Vocabulary selection was clear, focusing on category keywords.",
        "detailed_strengths": strengths,
        "areas_for_improvement": improvements,
        "action_immediate": ["Implement the Lens-Dot target drill to anchor your visual gaze."],
        "action_short_term": ["Play the 'Pause Game' during discussions to eliminate filler words."],
        "action_long_term": ["Rehearse system architecture talking points aloud to build vocabulary structure."],
        "expected_answer": f"An expert response to '{topic}' should introduce the core concept, explore trade-offs, and outline real-world examples.",
        # Always pass through the raw Whisper transcript unchanged — never AI-generated text
        "corrected_transcript": transcript,
        "summary": f"The speaker presented comments regarding '{topic}' under category '{category}'.",
        "missing_concepts": ["Advanced industrial case studies", "Quantitative statistical evidence"],
        "strengths": strengths,
        "weaknesses": improvements,
        "recommendations": [
            "Implement the Lens-Dot target drill to anchor your visual gaze.",
            "Play the 'Pause Game' during discussions to eliminate filler words.",
            "Rehearse system architecture talking points aloud to build vocabulary structure."
        ],
        "action_plan": [
            "Implement the Lens-Dot target drill to anchor your visual gaze.",
            "Play the 'Pause Game' during discussions to eliminate filler words.",
            "Rehearse system architecture talking points aloud to build vocabulary structure."
        ],
        "coaching_feedback": f"The speaker delivered a good talk on '{topic}' with conversational pace.",
        "final_assessment": f"The speaker delivered a good talk on '{topic}' with conversational pace.",
        "answered_topic": True,
        "content_relevance_score": 70,
        "topic_coverage_score": 70,
        "knowledge_depth_score": 70
    }

def normalize_report_types(report: Dict[str, Any]) -> Dict[str, Any]:
    string_keys = [
        "executive_summary",
        "speech_rate_reason", "speech_rate_suggestion",
        "speech_clarity_reason", "speech_clarity_suggestion",
        "speech_pronunciation_reason", "speech_pronunciation_suggestion",
        "speech_fluency_reason", "speech_fluency_suggestion",
        "speech_fillers_reason", "speech_fillers_suggestion",
        "speech_confidence_reason", "speech_confidence_suggestion",
        "body_eye_contact_evidence", "body_eye_contact_suggestion",
        "body_expressions_evidence", "body_expressions_suggestion",
        "body_posture_evidence", "body_posture_suggestion",
        "body_gestures_evidence", "body_gestures_suggestion",
        "body_head_movement_evidence", "body_head_movement_suggestion",
        "effectiveness_confidence_reason", "effectiveness_confidence_recommendation",
        "effectiveness_professionalism_reason", "effectiveness_professionalism_recommendation",
        "effectiveness_engagement_reason", "effectiveness_engagement_recommendation",
        "effectiveness_persuasiveness_reason", "effectiveness_persuasiveness_recommendation",
        "effectiveness_leadership_reason", "effectiveness_leadership_recommendation",
        "content_grammar_quality", "content_vocabulary_richness",
        "expected_answer", "summary",
        "coaching_feedback", "final_assessment"
    ]
    list_keys = [
        "detailed_strengths", "areas_for_improvement",
        "action_immediate", "action_short_term", "action_long_term",
        "missing_concepts", "strengths", "weaknesses", "recommendations", "action_plan"
    ]
    
    for k in string_keys:
        if k in report:
            val = report[k]
            if isinstance(val, list):
                report[k] = "\n".join([str(item) for item in val])
            elif val is None:
                report[k] = ""
            else:
                report[k] = str(val)
                
    for k in list_keys:
        if k in report:
            val = report[k]
            if isinstance(val, str):
                if "\n" in val:
                    report[k] = [item.strip("- *•").strip() for item in val.split("\n") if item.strip()]
                elif "," in val:
                    report[k] = [item.strip() for item in val.split(",") if item.strip()]
                else:
                    report[k] = [val.strip()]
            elif val is None:
                report[k] = []
            elif not isinstance(val, list):
                report[k] = [str(val)]
            else:
                report[k] = [str(item) for item in val]
                
    return report


def is_placeholder_or_generic(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, list):
        if len(val) == 0:
            return True
        for item in val:
            if is_placeholder_or_generic(item):
                return True
        return False
    if isinstance(val, str):
        val_lower = val.strip().lower()
        if not val_lower or val_lower == "":
            return True
        placeholders = [
            "could not be generated",
            "placeholder",
            "generic",
            "[insert",
            "<insert",
            "observed strength",
            "observed communication",
            "analysis completed but detailed",
            "detailed ai feedback"
        ]
        for p in placeholders:
            if p in val_lower:
                return True
        return False
    return False

def evaluate_speech_with_groq(topic: str, category: str, transcript: str,
                                 scores: Dict[str, Any], python_did_answer: bool = True) -> Dict[str, Any]:
    """
    Calls Groq's openai/gpt-oss-120b model via the centralized GroqService
    to generate the professional qualitative report sections.
    """
    logger.info("Summary Generation Started")
    from app.services.groq_service import GroqService
    groq_service = GroqService()

    # Extract all 23 sub-metrics
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
       How relevant was the user's response to the topic? If they did not answer the topic, asked for information, or said "I don't know" (or if the Python content check result above is True), the score must be under 20.
    
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
    """
    logger.info("Prompt Created")

    default_report = get_default_report_fallback(topic, category, transcript, scores)
    
    try:
        # Call GroqFeedbackService
        res_json = groq_service.call_groq_json(prompt, system_prompt="You are an elite communication twin mentor. Return valid JSON only.")
        
        # Populate the required detailed keys from the Groq JSON response
        result = default_report.copy()
        
        # Helper to validate and fallback
        def get_valid_field(key: str, default_val: Any) -> Any:
            val = res_json.get(key)
            if is_placeholder_or_generic(val):
                return default_val
            return val

        # Map direct keys with strict validation fallbacks
        result["executive_summary"] = get_valid_field("executive_summary", default_report["executive_summary"])
        result["detailed_strengths"] = get_valid_field("strengths", default_report["detailed_strengths"])
        result["areas_for_improvement"] = get_valid_field("areas_for_improvement", default_report["areas_for_improvement"])
        result["expected_answer"] = get_valid_field("expert_response", default_report["expected_answer"])
        result["missing_concepts"] = get_valid_field("missing_concepts", default_report["missing_concepts"])
        result["summary"] = get_valid_field("executive_summary", default_report["summary"])

        # Map new fields directly
        result["strengths"] = get_valid_field("strengths", default_report["strengths"])
        result["weaknesses"] = get_valid_field("areas_for_improvement", default_report["weaknesses"])
        result["recommendations"] = get_valid_field("recommendations", default_report["recommendations"])
        result["action_plan"] = get_valid_field("action_plan", default_report["action_plan"])
        result["coaching_feedback"] = get_valid_field("coaching_feedback", default_report["coaching_feedback"])
        result["final_assessment"] = get_valid_field("coaching_feedback", default_report["final_assessment"])

        # Map new content scores and answered_topic
        ans_top = res_json.get("answered_topic")
        if isinstance(ans_top, str):
            ans_top = ans_top.lower().strip() in ("true", "yes", "1")
        elif ans_top is None:
            ans_top = True
        else:
            ans_top = bool(ans_top)
        result["answered_topic"] = ans_top
        
        try:
            result["content_relevance_score"] = int(res_json.get("content_relevance_score", 70))
        except:
            result["content_relevance_score"] = 70
            
        try:
            result["topic_coverage_score"] = int(res_json.get("topic_coverage_score", 70))
        except:
            result["topic_coverage_score"] = 70
            
        try:
            result["knowledge_depth_score"] = int(res_json.get("knowledge_depth_score", 70))
        except:
            result["knowledge_depth_score"] = 70

        # Map action plans
        actions = get_valid_field("action_plan", default_report["action_plan"])
        if actions:
            # Safely chunk action plan into immediate, short, long
            if len(actions) > 0:
                result["action_immediate"] = [actions[0]]
                if len(actions) > 1:
                    result["action_immediate"].append(actions[1])
            if len(actions) > 2:
                result["action_short_term"] = [actions[2]]
                if len(actions) > 3:
                    result["action_short_term"].append(actions[3])
            if len(actions) > 4:
                result["action_long_term"] = actions[4:]
        
        # Ground and contextualize the specific report sections using the coaching feedback
        coach_feed = get_valid_field("coaching_feedback", default_report["coaching_feedback"])
        if coach_feed:
            # We append or enrich specific reasons to ground them
            result["speech_rate_reason"] = f"{default_report['speech_rate_reason']} {coach_feed[:120]}"
            result["speech_fluency_reason"] = f"{default_report['speech_fluency_reason']} {coach_feed[:120]}"
            result["speech_confidence_reason"] = f"{default_report['speech_confidence_reason']} {coach_feed[:120]}"
            result["effectiveness_confidence_reason"] = f"{default_report['effectiveness_confidence_reason']} {coach_feed[:120]}"
            result["effectiveness_leadership_reason"] = f"{default_report['effectiveness_leadership_reason']} {coach_feed[:120]}"
            
            # Map recommendations to the communication effectiveness section as well
            recs = get_valid_field("recommendations", default_report["recommendations"])
            if recs:
                result["effectiveness_confidence_recommendation"] = recs[0]
                if len(recs) > 1:
                    result["effectiveness_leadership_recommendation"] = recs[1]
                if len(recs) > 2:
                    result["effectiveness_professionalism_recommendation"] = recs[2]

        # CRITICAL: Always pin corrected_transcript to the original raw Whisper transcript.
        # The LLM must never supply or modify the transcript field.
        result["corrected_transcript"] = transcript
        
        logger.info("Summary Created")
        logger.info(f"[ai_evaluator] Whisper Transcript Preserved. Length={len(transcript)} chars. Preview: '{transcript[:100]}'")
        logger.info("Report Built")
        return normalize_report_types(result)
        
    except Exception as e:
        logger.error(f"[ai_evaluator] Error routing report evaluation to Groq: {e}. Returning fallback report.")
        logger.info("Summary Created")
        logger.info("Report Built")
        return normalize_report_types(default_report)
