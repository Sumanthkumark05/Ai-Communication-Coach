import bcrypt
# Monkeypatch bcrypt to truncate passwords > 72 bytes to avoid passlib crash with newer bcrypt versions
_orig_hashpw = bcrypt.hashpw
def _patched_hashpw(password, salt):
    if len(password) > 72:
        password = password[:72]
    return _orig_hashpw(password, salt)
bcrypt.hashpw = _patched_hashpw

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.config import settings
from app.models import User
from main import app

# Setup test database (temporary SQLite file)
import os
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_temp.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the database dependency in FastAPI app
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    # Create tables before each test
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after each test
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    # Remove test database file
    if os.path.exists("./test_temp.db"):
        try:
            os.remove("./test_temp.db")
        except Exception:
            pass

client = TestClient(app)

def test_signup_and_login():
    # 1. Test Signup
    signup_data = {
        "email": "testuser@example.com",
        "password": "testpassword123",
        "name": "Test User"
    }
    response = client.post("/api/auth/signup", json=signup_data)
    assert response.status_code == 201
    json_data = response.json()
    assert json_data["email"] == "testuser@example.com"
    assert json_data["name"] == "Test User"
    assert "id" in json_data

    # 2. Test Signup with existing email (should fail)
    response = client.post("/api/auth/signup", json=signup_data)
    assert response.status_code == 400
    assert response.json()["detail"] == "A user with this email already exists"

    # 3. Test Login
    login_data = {
        "email": "testuser@example.com",
        "password": "testpassword123"
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 4. Test Get Profile (Me)
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    profile_data = response.json()
    assert profile_data["email"] == "testuser@example.com"
    assert profile_data["name"] == "Test User"


from unittest.mock import patch

def test_topic_generation():
    # 1. Signup and login to get auth headers
    signup_data = {
        "email": "testtopic@example.com",
        "password": "testpassword123",
        "name": "Topic User"
    }
    client.post("/api/auth/signup", json=signup_data)
    login_response = client.post("/api/auth/login", json={"email": "testtopic@example.com", "password": "testpassword123"})
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Mock generate_topic_from_oss_120b to avoid external API calls
    mock_topic_data = {
        "topic": "Mock Dynamic AI Topic",
        "category": "Technology",
        "difficulty": "Medium",
        "keywords": ["mock", "test"]
    }
    
    with patch("app.routers.jam.generate_topic_from_llm", return_value=mock_topic_data) as mock_gen:
        # Test new GET /generate-topic endpoint
        response = client.get("/api/generate-topic", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "Mock Dynamic AI Topic"
        assert data["category"] == "Technology"
        assert data["difficulty"] == "Medium"
        assert data["keywords"] == ["mock", "test"]
        mock_gen.assert_called_once()

        # Test old GET /topic backward compatibility endpoint
        mock_gen.reset_mock()
        response = client.get("/api/jam/topic?category=Technology", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "Technology"
        assert data["topic"] == "Mock Dynamic AI Topic"


def test_jam_session_and_analytics():
    # 1. Signup and login
    signup_data = {
        "email": "speaker@example.com",
        "password": "password123",
        "name": "Speaker"
    }
    client.post("/api/auth/signup", json=signup_data)
    login_response = client.post("/api/auth/login", json={"email": "speaker@example.com", "password": "password123"})
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create JAM Session
    session_payload = {
        "topic": "Is AI replacing jobs?",
        "category": "Technology"
    }
    response = client.post("/api/jam/session", json=session_payload, headers=headers)
    assert response.status_code == 200
    session_data = response.json()
    assert session_data["topic"] == "Is AI replacing jobs?"
    assert session_data["category"] == "Technology"
    assert session_data["video_url"] is None
    session_id = session_data["id"]

    # 3. Verify Empty History & Analytics
    response = client.get("/api/jam/history", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1  # The session is created but has no metrics yet
    assert response.json()[0]["overall_score"] == 0

    response = client.get("/api/jam/analytics", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_sessions"] == 0  # No sessions with metrics yet

    # 4. Check Leaderboard
    response = client.get("/api/jam/leaderboard")
    assert response.status_code == 200
    assert len(response.json()) == 0  # No users with completed reports


def test_debate_flow():
    # 1. Signup and login
    signup_data = {
        "email": "debater@example.com",
        "password": "password123",
        "name": "Debater"
    }
    client.post("/api/auth/signup", json=signup_data)
    login_response = client.post("/api/auth/login", json={"email": "debater@example.com", "password": "password123"})
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Start Debate Session
    with patch("app.services.openai_service.OpenAIService.generate_debate_opponent_argument", return_value="Opponent opening statement") as mock_opp:
        response = client.post("/api/debate/start?topic=AI%20vs%20Human&difficulty=Medium", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["opponent_statement"] == "Opponent opening statement"
        session_id = data["session_id"]
        mock_opp.assert_called_once()

    # 3. Argue Debate Round
    mock_scores = {"argument_quality": 85, "persuasion": 80, "logical_consistency": 90}

    with patch("app.services.openai_service.OpenAIService.generate_debate_opponent_argument", return_value="Counter counter-argument") as mock_opp, \
         patch("app.services.groq_service.GroqService.call_groq_json", return_value=mock_scores) as mock_groq, \
         patch("app.config.settings.GROQ_API_KEY", "test_key"):
        
        response = client.post(
            f"/api/debate/{session_id}/argue?user_argument=I%20think%20humans%20have%20creativity", 
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["opponent_statement"] == "Counter counter-argument"
        assert data["scores"]["argument_quality"] == 85
        assert data["scores"]["persuasion"] == 80
        assert data["scores"]["logical_consistency"] == 90


def test_document_recording_endpoints():
    # 1. Signup and login
    signup_data = {
        "email": "docuser@example.com",
        "password": "password123",
        "name": "Doc User"
    }
    client.post("/api/auth/signup", json=signup_data)
    login_response = client.post("/api/auth/login", json={"email": "docuser@example.com", "password": "password123"})
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload document first
    test_file_content = b"# Test Document\nThis is a test document."
    from io import BytesIO
    response = client.post(
        "/api/document/upload",
        files={"file": ("test_doc.md", BytesIO(test_file_content), "text/markdown")},
        headers=headers
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    # 3. Create a Document presentation session
    session_payload = {
        "document_id": doc_id,
        "topic_id": None,
        "topic_title": "Test Topic",
        "category": "Test Category",
        "instant_start": True,
        "preparation_mode": False,
        "skip_preparation": False
    }
    response = client.post("/api/document/session", json=session_payload, headers=headers)
    assert response.status_code == 200
    session_id = response.json()["id"]

    # 4. Upload a mock video/audio file (this triggers creation of DocumentRecording record)
    mock_video_content = b"fake video content bytes"
    response = client.post(
        f"/api/document/session/{session_id}/upload",
        files={"file": ("recording.webm", BytesIO(mock_video_content), "video/webm")},
        headers=headers
    )
    assert response.status_code == 200
    
    # 5. Let's create a report in the database directly to test report endpoint, or verify the recording endpoints
    from app.models import DocumentRecording, DocumentReport
    db = TestingSessionLocal()
    recording = db.query(DocumentRecording).filter(DocumentRecording.session_id == session_id).first()
    assert recording is not None
    assert recording.session_id == session_id
    
    # Create a mock report linked to it
    report = DocumentReport(
        session_id=session_id,
        accuracy_score=90,
        coverage_score=85,
        understanding_score=95,
        explanation_quality=80,
        technical_correctness=88,
        relevance_score=92
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    recording.report_id = report.id
    db.commit()
    
    # Extract IDs to local variables before closing session
    rec_id = str(recording.id)
    rep_id = str(report.id)
    db.close()

    # 6. Test GET /api/document/recording/{recording_id}
    response = client.get(f"/api/document/recording/{rec_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["recording_id"] == rec_id
    assert data["analysis_id"] == session_id
    assert data["report_id"] == rep_id
    assert "token=" in data["recording_url"]

    # 7. Test GET /api/document/report/{report_id}
    response = client.get(f"/api/document/report/{rep_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["recording_id"] == rec_id
    assert data["analysis_id"] == session_id
    assert data["report_id"] == rep_id
    assert "token=" in data["recording_url"]

    # 8. Test GET /api/document/history
    response = client.get("/api/document/history", headers=headers)
    assert response.status_code == 200
    history = response.json()
    assert len(history) >= 1
    assert history[0]["recording_id"] == rec_id
    assert history[0]["analysis_id"] == session_id
    assert history[0]["report_id"] == rep_id
    assert "token=" in history[0]["recording_url"]


