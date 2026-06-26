import pytest
from unittest.mock import patch, MagicMock
import requests
import json
from app.services.topic_generator import (
    extract_and_parse_json, 
    generate_topic_from_llm,
    validate_topic_data
)
from app.config import settings

def test_extract_and_parse_json_success():
    raw_text = '{"topic": "AI Future", "category": "Tech", "difficulty": "Easy", "keywords": ["ai"], "talking_points": ["point 1"], "estimated_speaking_time": 60}'
    parsed = extract_and_parse_json(raw_text)
    assert parsed["topic"] == "AI Future"
    assert parsed["difficulty"] == "Easy"

def test_extract_and_parse_json_with_markdown_and_text():
    raw_text = """
    Here is the response:
    ```json
    {
      "topic": "AI in healthcare",
      "category": "Artificial Intelligence",
      "difficulty": "Medium",
      "keywords": ["medicine", "tech"],
      "talking_points": ["point 1"],
      "estimated_speaking_time": 60
    }
    ```
    Hope this helps!
    """
    parsed = extract_and_parse_json(raw_text)
    assert parsed["topic"] == "AI in healthcare"
    assert parsed["difficulty"] == "Medium"

def test_validate_topic_data_invalid():
    with pytest.raises(ValueError, match="missing the required key"):
        validate_topic_data({"wrong_key": "val"})

    with pytest.raises(ValueError, match="invalid field types"):
        validate_topic_data({
            "topic": 123,  # should be string
            "category": "Tech",
            "difficulty": "Easy",
            "keywords": ["tech"],
            "talking_points": ["point 1"],
            "estimated_speaking_time": 60
        })

def test_generate_topic_from_llm_groq_success():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GROQ_API_KEY = "test_groq_key"
        mock_settings.TOPIC_GENERATOR_MODEL = "llama-3.3-70b-versatile"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"topic": "Groq Llama Topic", "category": "Technology", "difficulty": "Medium", "keywords": ["groq"], "talking_points": ["point 1"], "estimated_speaking_time": 60}'
                }
            }]
        }
        
        with patch("requests.post", return_value=mock_response) as mock_post:
            result = generate_topic_from_llm("Technology")
            assert result["topic"] == "Groq Llama Topic"
            assert result["difficulty"] == "Medium"
            assert result["category"] == "Technology"
