import pytest
from app.utils.ai_parser import (
    parse_ai_response,
    TopicsListModel,
    DocumentAnalysisModel,
    SpeechToDocumentEvaluationModel,
    VivaQuestionsModel,
    VivaEvaluationModel
)

def test_format_1_dict():
    # Format 1: Standard dictionary with 'topics'
    raw = {
        "topics": [
            {
                "topic": "AI Introduction",
                "category": "Technology",
                "difficulty": "Beginner",
                "talking_points": ["What is AI", "History of AI"],
                "estimated_speaking_time": 90,
                "keywords": ["AI", "Intro"]
            }
        ]
    }
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 1
    assert res["topics"][0]["topic"] == "AI Introduction"
    assert res["topics"][0]["category"] == "Technology"

def test_format_2_list_of_dicts():
    # Format 2: List of dictionaries with 'title' instead of 'topic'
    raw = [
        {"title": "Machine Learning", "category": "Data Science"},
        {"topic": "Deep Learning", "difficulty": "Advanced"}
    ]
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 2
    assert res["topics"][0]["topic"] == "Machine Learning"
    assert res["topics"][0]["category"] == "Data Science"
    assert res["topics"][1]["topic"] == "Deep Learning"
    assert res["topics"][1]["difficulty"] == "Advanced"

def test_format_3_list_of_strings():
    # Format 3: List of strings directly
    raw = ["Introduction to AI", "Neural Networks"]
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 2
    assert res["topics"][0]["topic"] == "Introduction to AI"
    assert res["topics"][0]["category"] == "General"
    assert res["topics"][1]["topic"] == "Neural Networks"

def test_format_4_markdown_json_fence():
    # Format 4: Markdown wrapped json string
    raw = """
```json
{
  "topics": [
    {"topic": "Prompt Engineering", "estimated_speaking_time": 120}
  ]
}
```
"""
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 1
    assert res["topics"][0]["topic"] == "Prompt Engineering"
    assert res["topics"][0]["estimated_speaking_time"] == 120

def test_format_5_markdown_text_fence():
    # Format 5: Markdown text fence wrapping a list
    raw = """
```text
[
  {"title": "Transformers"}
]
```
"""
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 1
    assert res["topics"][0]["topic"] == "Transformers"

def test_format_6_raw_json_string():
    # Format 6: Standard JSON string
    raw = '{"topics":[{"topic": "Reinforcement Learning"}]}'
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 1
    assert res["topics"][0]["topic"] == "Reinforcement Learning"

def test_format_7_markdown_wrapped_response():
    # Format 7: Text surrounding JSON block
    raw = """
Sure! Here is the JSON data you requested:
```json
{
  "topics": [
    {"topic": "Generative AI"}
  ]
}
```
Hope this is helpful!
"""
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 1
    assert res["topics"][0]["topic"] == "Generative AI"

def test_format_8_nested_response():
    # Format 8: Nested under a "response" key
    raw = {
        "response": {
            "topics": [
                {"topic": "Fine-Tuning"}
            ]
        }
    }
    res = parse_ai_response(raw, TopicsListModel)
    assert len(res["topics"]) == 1
    assert res["topics"][0]["topic"] == "Fine-Tuning"

def test_document_analysis_model():
    raw = {
        "title": "My Document",
        "summary": "This is a summary",
        "key_concepts": ["concept1"],
        "keywords": ["keyword1"],
        "learning_objectives": ["objective1"],
        "is_project_report": True
    }
    res = parse_ai_response(raw, DocumentAnalysisModel)
    assert res["title"] == "My Document"
    assert res["is_project_report"] is True
    assert res["is_resume"] is False  # default value

def test_speech_to_document_evaluation_model():
    raw = {
        "accuracy_score": 85,
        "knowledge_gaps": [
            {"concept": "Gap 1", "description": "Detail 1"},
            "Simple Gap String"
        ]
    }
    res = parse_ai_response(raw, SpeechToDocumentEvaluationModel)
    assert res["accuracy_score"] == 85
    assert len(res["knowledge_gaps"]) == 2
    assert res["knowledge_gaps"][0]["concept"] == "Gap 1"
    assert res["knowledge_gaps"][1]["concept"] == "Simple Gap String"
    assert res["coverage_score"] == 70  # default value

def test_validation_fallback():
    # Invalid data structures should not raise errors, but fall back gracefully to default schemas.
    raw = {"invalid_field": 123}
    res_topics = parse_ai_response(raw, TopicsListModel)
    assert isinstance(res_topics, dict)
    assert "topics" in res_topics
    assert isinstance(res_topics["topics"], list)
    
    res_eval = parse_ai_response(None, SpeechToDocumentEvaluationModel)
    assert isinstance(res_eval, dict)
    assert res_eval["accuracy_score"] == 75
    assert res_eval["coverage_score"] == 70
