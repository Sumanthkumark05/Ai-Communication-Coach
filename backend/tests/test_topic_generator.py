import pytest
from unittest.mock import patch, MagicMock
import requests
from app.services.topic_generator import (
    extract_and_parse_json, 
    generate_topic_from_llm,
    validate_topic_data
)
from app.config import settings

def test_extract_and_parse_json_success():
    raw_text = '{"topic": "AI Future", "category": "Tech", "difficulty": "Easy", "keywords": ["ai"]}'
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
      "keywords": ["medicine", "tech"]
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
            "keywords": ["tech"]
        })

def test_generate_topic_from_llm_gemini_success():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "test_gemini_key"
        mock_settings.GROQ_API_KEY = ""
        mock_settings.TOPIC_GENERATOR_MODEL = "gemini-2.5-flash"
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"topic": "Gemini AI Topic", "category": "Technology", "difficulty": "Easy", "keywords": ["gemini"]}'
        mock_client.models.generate_content.return_value = mock_response
        
        with patch("google.genai.Client", return_value=mock_client):
            result = generate_topic_from_llm("Technology")
            assert result["topic"] == "Gemini AI Topic"
            assert result["difficulty"] == "Easy"
            assert result["category"] == "Technology"

def test_generate_topic_from_llm_groq_success():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.GROQ_API_KEY = "test_groq_key"
        mock_settings.TOPIC_GENERATOR_MODEL = "llama-3.3-70b-versatile"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"topic": "Groq Llama Topic", "category": "Technology", "difficulty": "Medium", "keywords": ["groq"]}'
                }
            }]
        }
        
        with patch("requests.post", return_value=mock_response) as mock_post:
            result = generate_topic_from_llm("Technology")
            assert result["topic"] == "Groq Llama Topic"
            assert result["difficulty"] == "Medium"
            
            # Verify payload details
            called_args, called_kwargs = mock_post.call_args
            assert "api.groq.com" in called_args[0]
            payload = called_kwargs["json"]
            assert payload["model"] == "llama-3.3-70b-versatile"

def test_generate_topic_fallback_gemini_to_groq():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "test_gemini_key"
        mock_settings.GROQ_API_KEY = "test_groq_key"
        mock_settings.TOPIC_GENERATOR_MODEL = "gemini-2.5-flash"
        
        # Gemini Client fails
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Gemini API Error")
        
        # Groq succeeds
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"topic": "Groq Fallback Topic", "category": "Technology", "difficulty": "Hard", "keywords": ["fallback"]}'
                }
            }]
        }
        
        with patch("google.genai.Client", return_value=mock_client), patch("requests.post", return_value=mock_response):
            result = generate_topic_from_llm("Technology")
            assert result["topic"] == "Groq Fallback Topic"
            assert result["difficulty"] == "Hard"

def test_generate_topic_fallback_groq_to_gemini():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "test_gemini_key"
        mock_settings.GROQ_API_KEY = "test_groq_key"
        mock_settings.TOPIC_GENERATOR_MODEL = "llama-3.3-70b-versatile"
        
        # Groq fails (500 error)
        mock_groq_res = MagicMock()
        mock_groq_res.status_code = 500
        
        # Gemini succeeds
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"topic": "Gemini Fallback Topic", "category": "Technology", "difficulty": "Medium", "keywords": ["fallback"]}'
        mock_client.models.generate_content.return_value = mock_response
        
        with patch("google.genai.Client", return_value=mock_client), patch("requests.post", return_value=mock_groq_res):
            result = generate_topic_from_llm("Technology")
            assert result["topic"] == "Gemini Fallback Topic"
            assert result["difficulty"] == "Medium"

def test_generate_topic_no_keys_configured():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.GROQ_API_KEY = ""
        mock_settings.TOPIC_GENERATOR_MODEL = ""
        with pytest.raises(ValueError, match="Model unavailable: Neither GEMINI_API_KEY nor GROQ_API_KEY is configured"):
            generate_topic_from_llm("Technology")

def test_generate_topic_api_timeout():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.GROQ_API_KEY = "test_key"
        mock_settings.TOPIC_GENERATOR_MODEL = "llama-3.3-70b-versatile"
        with patch("requests.post", side_effect=requests.exceptions.Timeout("Timeout occurred")):
            with pytest.raises(RuntimeError, match="API timeout"):
                generate_topic_from_llm("Technology")

def test_generate_topic_distribution():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "AIzaFakeKey123"
        mock_settings.GROQ_API_KEY = ""
        mock_settings.TOPIC_GENERATOR_MODEL = "gemini-2.5-flash"
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"topic": "Dummy", "category": "Dummy", "difficulty": "Dummy", "keywords": ["dummy"], "talking_points": ["point"]}'
        mock_client.models.generate_content.return_value = mock_response
        
        with patch("google.genai.Client", return_value=mock_client):
            # Generate 20 Easy topics
            easy_topics = []
            for _ in range(20):
                res = generate_topic_from_llm(difficulty="Easy")
                easy_topics.append(res)
                assert res["difficulty"] == "Easy"
            
            # Generate 20 Medium topics
            medium_topics = []
            for _ in range(20):
                res = generate_topic_from_llm(difficulty="Medium")
                medium_topics.append(res)
                assert res["difficulty"] == "Medium"
                
            # Generate 20 Hard topics
            hard_topics = []
            for _ in range(20):
                res = generate_topic_from_llm(difficulty="Hard")
                hard_topics.append(res)
                assert res["difficulty"] == "Hard"
                
            # Verify no Easy topic appears in Hard
            from app.services.topic_generator import EASY_TOPIC_CATEGORIES
            easy_pool = set(sum(EASY_TOPIC_CATEGORIES.values(), []))
            
            for ht in hard_topics:
                assert ht["topic"] not in easy_pool

def test_generate_topic_category_mapping():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "AIzaFakeKey123"
        mock_settings.GROQ_API_KEY = ""
        mock_settings.TOPIC_GENERATOR_MODEL = "gemini-2.5-flash"
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"topic": "Dummy", "category": "Dummy", "difficulty": "Dummy", "keywords": ["dummy"], "talking_points": ["point"]}'
        mock_client.models.generate_content.return_value = mock_response
        
        with patch("google.genai.Client", return_value=mock_client):
            # Test mapped category "AI"
            res = generate_topic_from_llm(category="AI")
            assert res["category"] == "Technology Topics"
            assert res["topic"] in ["Artificial Intelligence in Daily Life", "Future of Technology", "Future of Artificial Intelligence", "Digital Transformation"]
            
            # Test mapped category "Education"
            res_edu = generate_topic_from_llm(category="Education")
            assert res_edu["category"] in ["Student Topics", "Technology Topics"]

def test_generate_topic_exclusions():
    with patch("app.services.topic_generator.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "AIzaFakeKey123"
        mock_settings.GROQ_API_KEY = ""
        mock_settings.TOPIC_GENERATOR_MODEL = "gemini-2.5-flash"
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"topic": "Dummy", "category": "Dummy", "difficulty": "Dummy", "keywords": ["dummy"], "talking_points": ["point"]}'
        mock_client.models.generate_content.return_value = mock_response
        
        with patch("google.genai.Client", return_value=mock_client):
            # Exclude all topics except one in "AI" Easy pool
            res = generate_topic_from_llm(category="AI", exclude_topics=["Artificial Intelligence in Daily Life"], difficulty="Easy")
            assert res["topic"] == "Future of Technology"
