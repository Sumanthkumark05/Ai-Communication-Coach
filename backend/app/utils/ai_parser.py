import re
import json
import logging
from typing import Any, Dict, List, Type, TypeVar, Union, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("jam_analyzer")

T = TypeVar('T', bound=BaseModel)

# ----------------------------------------------------
# 1. Pydantic Schemas for Strict Validation & Defaults
# ----------------------------------------------------

class DocumentAnalysisModel(BaseModel):
    title: str = "Document"
    summary: str = ""
    key_concepts: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    learning_objectives: List[str] = Field(default_factory=list)
    is_project_report: bool = False
    is_resume: bool = False

class TopicModel(BaseModel):
    topic: str = "Speaking Topic"
    category: str = "General"
    difficulty: str = "Intermediate"
    talking_points: List[str] = Field(default_factory=list)
    estimated_speaking_time: int = 60
    keywords: List[str] = Field(default_factory=list)

class TopicsListModel(BaseModel):
    topics: List[TopicModel] = Field(default_factory=list)

class KnowledgeGapModel(BaseModel):
    concept: str = "Omitted Concept"
    description: str = ""

class SpeechToDocumentEvaluationModel(BaseModel):
    accuracy_score: int = 75
    coverage_score: int = 70
    understanding_score: int = 72
    explanation_quality: int = 74
    technical_correctness: int = 76
    relevance_score: int = 80
    knowledge_gaps: List[KnowledgeGapModel] = Field(default_factory=list)
    suggested_improvements: List[str] = Field(default_factory=list)
    coach_recommendations: List[str] = Field(default_factory=list)
    follow_up_questions: List[str] = Field(default_factory=list)

class VivaQuestionsModel(BaseModel):
    questions: List[str] = Field(default_factory=list)

class VivaEvaluationModel(BaseModel):
    score: int = 70
    feedback: str = ""
    correct_elements: List[str] = Field(default_factory=list)
    incorrect_elements: List[str] = Field(default_factory=list)
    ideal_response: str = ""


# ----------------------------------------------------
# 2. Universal Parsing & Normalization Logic
# ----------------------------------------------------

def clean_raw_string(raw_str: str) -> str:
    """
    Cleans raw response string by removing markdown code blocks,
    stripping whitespace, and resolving common JSON quirks.
    """
    cleaned = raw_str.strip()
    
    # Remove markdown code fences if present (e.g., ```json ... ```)
    code_fence_pattern = re.compile(r"```(?:json|text|xml)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
    match = code_fence_pattern.search(cleaned)
    if match:
        cleaned = match.group(1).strip()
    
    return cleaned

def parse_json_safely(raw_str: str) -> Any:
    """
    Tries to safely load JSON from raw_str. Falls back to regex object/array extraction.
    """
    cleaned = clean_raw_string(raw_str)
    logger.info(f"[AI_PARSER] Cleaned response: {cleaned}")
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[AI_PARSER] JSON parsing failed: {e}. Attempting regex recovery.")
        
        # Regex recovery: Extract content between the first [ or { and the last ] or }
        try:
            match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if match:
                candidate = match.group(1).strip()
                parsed = json.loads(candidate)
                logger.info(f"[AI_PARSER] Parsed after regex recovery: {parsed}")
                return parsed
        except Exception as e2:
            logger.warning(f"[AI_PARSER] Regex object extraction failed: {e2}")
            
        # Last-resort fallback: Simple quote replacements
        try:
            candidate = cleaned.replace("'", '"')
            parsed = json.loads(candidate)
            logger.info(f"[AI_PARSER] Parsed after single-quote replacement fallback: {parsed}")
            return parsed
        except Exception as e3:
            logger.error(f"[AI_PARSER] Parser error: fallback quote replacement failed: {e3}")
            raise ValueError(f"Failed to parse JSON from AI response: {raw_str}")

def normalize_parsed_structure(parsed_obj: Any, model_class: Type[BaseModel]) -> Dict[str, Any]:
    """
    Normalizes parsed list or dictionary objects into standard expected structures 
    to match the target Pydantic schema model.
    """
    if parsed_obj is None:
        return {}

    # If target model is TopicsListModel
    if model_class == TopicsListModel:
        # Handle dict-based topics
        if isinstance(parsed_obj, dict):
            # Extract nested 'response' key
            if "response" in parsed_obj and isinstance(parsed_obj["response"], dict):
                inner = parsed_obj["response"]
                if "topics" in inner:
                    return normalize_parsed_structure(inner, model_class)
            
            # Extract topics array if present
            if "topics" in parsed_obj and isinstance(parsed_obj["topics"], list):
                normalized_topics = []
                for item in parsed_obj["topics"]:
                    if isinstance(item, dict):
                        # Map title -> topic if needed
                        topic_val = item.get("topic") or item.get("title") or "Speaking Topic"
                        normalized_topics.append({
                            "topic": topic_val,
                            "category": item.get("category", "General"),
                            "difficulty": item.get("difficulty", "Intermediate"),
                            "talking_points": item.get("talking_points", []),
                            "estimated_speaking_time": item.get("estimated_speaking_time", 60),
                            "keywords": item.get("keywords", [])
                        })
                return {"topics": normalized_topics}
            
            # What if the dict itself is a topic object? Wrap it in a list
            if "topic" in parsed_obj or "title" in parsed_obj:
                topic_val = parsed_obj.get("topic") or parsed_obj.get("title") or "Speaking Topic"
                return {
                    "topics": [{
                        "topic": topic_val,
                        "category": parsed_obj.get("category", "General"),
                        "difficulty": parsed_obj.get("difficulty", "Intermediate"),
                        "talking_points": parsed_obj.get("talking_points", []),
                        "estimated_speaking_time": parsed_obj.get("estimated_speaking_time", 60),
                        "keywords": parsed_obj.get("keywords", [])
                    }]
                }
            
            return {"topics": []}

        # Handle list-based topics
        elif isinstance(parsed_obj, list):
            normalized_topics = []
            for item in parsed_obj:
                if isinstance(item, dict):
                    topic_val = item.get("topic") or item.get("title") or "Speaking Topic"
                    normalized_topics.append({
                        "topic": topic_val,
                        "category": item.get("category", "General"),
                        "difficulty": item.get("difficulty", "Intermediate"),
                        "talking_points": item.get("talking_points", []),
                        "estimated_speaking_time": item.get("estimated_speaking_time", 60),
                        "keywords": item.get("keywords", [])
                    })
                elif isinstance(item, str):
                    normalized_topics.append({
                        "topic": item,
                        "category": "General",
                        "difficulty": "Intermediate",
                        "talking_points": [],
                        "estimated_speaking_time": 60,
                        "keywords": []
                    })
            return {"topics": normalized_topics}

    # If target model is VivaQuestionsModel
    elif model_class == VivaQuestionsModel:
        if isinstance(parsed_obj, list):
            questions = [str(x) for x in parsed_obj]
            return {"questions": questions}
        elif isinstance(parsed_obj, dict):
            if "questions" in parsed_obj and isinstance(parsed_obj["questions"], list):
                return {"questions": parsed_obj["questions"]}
            if "response" in parsed_obj:
                resp = parsed_obj["response"]
                if isinstance(resp, list):
                    return {"questions": [str(x) for x in resp]}
                elif isinstance(resp, dict) and "questions" in resp:
                    return {"questions": resp["questions"]}
        return {"questions": []}

    # If target model is SpeechToDocumentEvaluationModel
    elif model_class == SpeechToDocumentEvaluationModel:
        if isinstance(parsed_obj, dict):
            if "response" in parsed_obj and isinstance(parsed_obj["response"], dict):
                parsed_obj = parsed_obj["response"]
                
            gaps = parsed_obj.get("knowledge_gaps") or parsed_obj.get("gaps") or []
            normalized_gaps = []
            if isinstance(gaps, list):
                for g in gaps:
                    if isinstance(g, dict):
                        normalized_gaps.append({
                            "concept": g.get("concept") or g.get("title") or "Omitted Concept",
                            "description": g.get("description") or g.get("detail") or ""
                        })
                    elif isinstance(g, str):
                        normalized_gaps.append({
                            "concept": g,
                            "description": ""
                        })
                        
            improvements = parsed_obj.get("suggested_improvements") or parsed_obj.get("improvements") or []
            recommendations = parsed_obj.get("coach_recommendations") or parsed_obj.get("recommendations") or []
            
            acc_score = parsed_obj.get("accuracy_score")
            if acc_score is None:
                acc_score = parsed_obj.get("score")
                
            return {
                "accuracy_score": int(acc_score) if acc_score is not None else 75,
                "coverage_score": int(parsed_obj.get("coverage_score", 70)),
                "understanding_score": int(parsed_obj.get("understanding_score", 72)),
                "explanation_quality": int(parsed_obj.get("explanation_quality", 74)),
                "technical_correctness": int(parsed_obj.get("technical_correctness", 76)),
                "relevance_score": int(parsed_obj.get("relevance_score", 80)),
                "knowledge_gaps": normalized_gaps,
                "suggested_improvements": list(improvements) if isinstance(improvements, list) else [],
                "coach_recommendations": list(recommendations) if isinstance(recommendations, list) else [],
                "follow_up_questions": list(parsed_obj.get("follow_up_questions", [])) if isinstance(parsed_obj.get("follow_up_questions"), list) else []
            }

    if isinstance(parsed_obj, dict):
        return parsed_obj
    return {}

def parse_ai_response(raw_response: Any, model_class: Type[T]) -> Dict[str, Any]:
    """
    Universal response parser. Takes a raw string, dictionary, list or other type,
    safely parses it, normalizes its structure based on target Pydantic model,
    validates the result using Pydantic, and returns a sanitized python dict.
    
    Guarantees no KeyError or AttributeError on model fields.
    """
    logger.info(f"[AI_PARSER] Parser Type: {model_class.__name__}")
    logger.info(f"[AI_PARSER] Raw AI response type: {type(raw_response)}")
    logger.info(f"[AI_PARSER] Raw AI response: {raw_response}")

    if raw_response is None:
        logger.warning("[AI_PARSER] Raw AI response is None.")
        fallback = model_class.model_validate({}).model_dump()
        logger.info(f"[AI_PARSER] Final Normalized Response: {fallback}")
        return fallback

    parsed_obj = None
    if isinstance(raw_response, (dict, list)):
        parsed_obj = raw_response
        logger.info(f"[AI_PARSER] Parsed Response: {parsed_obj}")
    elif isinstance(raw_response, str):
        try:
            parsed_obj = parse_json_safely(raw_response)
            logger.info(f"[AI_PARSER] Parsed Response: {parsed_obj}")
        except Exception as e:
            logger.error(f"[AI_PARSER] Parser error: JSON parsing failed: {e}")
            fallback = model_class.model_validate({}).model_dump()
            logger.info(f"[AI_PARSER] Final Normalized Response: {fallback}")
            return fallback
    else:
        logger.warning(f"[AI_PARSER] Unexpected response type: {type(raw_response)}. Using empty dictionary.")
        parsed_obj = {}

    if not isinstance(parsed_obj, (dict, list)):
        logger.warning(f"[AI_PARSER] Parsed JSON is of type {type(parsed_obj)}, not dict/list. Wrapping in dict.")
        parsed_obj = {}

    normalized = normalize_parsed_structure(parsed_obj, model_class)

    try:
        validated = model_class.model_validate(normalized)
        result = validated.model_dump()
        logger.info(f"[AI_PARSER] Final Normalized Response: {result}")
        return result
    except Exception as e:
        logger.error(f"[AI_PARSER] Parser error: Pydantic validation error for model {model_class.__name__}: {e}")
        try:
            fallback = model_class.model_validate({})
            result = fallback.model_dump()
            logger.info(f"[AI_PARSER] Final Normalized Response: {result}")
            return result
        except Exception as e_fallback:
            logger.critical(f"[AI_PARSER] Fatal default model creation error: {e_fallback}")
            return {}
