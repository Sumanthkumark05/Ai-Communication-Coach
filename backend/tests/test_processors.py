import pytest
import numpy as np
from app.services.audio_processor import clean_word, analyze_speech_metrics
from app.services.vision_processor import estimate_gaze_hit, estimate_head_pose

def test_clean_word():
    assert clean_word("Hello!!!") == "hello"
    assert clean_word("world,") == "world"
    assert clean_word("  Test's  ") == "test's"
    assert clean_word("...") == ""

def test_analyze_speech_metrics():
    # 5 words in 2 seconds, no fillers, no pauses
    words = [
        {"word": "This", "start": 0.0, "end": 0.3},
        {"word": "is", "start": 0.4, "end": 0.6},
        {"word": "a", "start": 0.7, "end": 0.9},
        {"word": "clean", "start": 1.0, "end": 1.4},
        {"word": "speech", "start": 1.5, "end": 1.9}
    ]
    duration = 2.0
    metrics = analyze_speech_metrics(words, duration)
    
    assert metrics["words_per_minute"] == 150
    assert metrics["filler_words"] == {
        "um": 0, "uh": 0, "ah": 0, "ahh": 0, "uhh": 0, "erm": 0, "like": 0, "you know": 0,
        "actually": 0, "basically": 0, "literally": 0, "sort of": 0, "kind of": 0
    }
    assert metrics["pause_count"] == 0
    assert metrics["pause_duration"] == 0.0
    assert metrics["vocabulary_score"] > 50
    assert metrics["speaking_pace_score"] == 77  # 100 - abs(150-135)*1.5

def test_analyze_speech_metrics_with_fillers():
    # Speech with fillers and pauses
    words = [
        {"word": "So", "start": 0.0, "end": 0.3},
        {"word": "um", "start": 0.4, "end": 0.7},
        {"word": "like", "start": 0.8, "end": 1.1},
        {"word": "you", "start": 3.0, "end": 3.2}, # > 1.5s pause since last end (1.1)
        {"word": "know", "start": 3.3, "end": 3.6}
    ]
    duration = 4.0
    metrics = analyze_speech_metrics(words, duration)
    
    assert metrics["filler_words"]["um"] == 1
    assert metrics["filler_words"]["like"] == 1
    assert metrics["filler_words"]["you know"] == 1
    assert metrics["pause_count"] == 1
    assert metrics["pause_duration"] == 1.9

def test_estimate_gaze_hit():
    # Mock aligned pupil coordinates (Centered)
    left_eye = [np.array([0.1, 0.5]), np.array([0.9, 0.5])]
    left_pupil = np.array([0.5, 0.5])
    
    right_eye = [np.array([0.1, 0.5]), np.array([0.9, 0.5])]
    right_pupil = np.array([0.5, 0.5])
    
    assert estimate_gaze_hit(left_eye, left_pupil, right_eye, right_pupil)[0] is True

    # Mock unaligned pupil coordinates (Looking away)
    left_pupil_away = np.array([0.95, 0.5])
    right_pupil_away = np.array([0.95, 0.5])
    
    assert estimate_gaze_hit(left_eye, left_pupil_away, right_eye, right_pupil_away)[0] is False

def test_local_evaluation_fallback():
    speech = {
        "transcript": "Hello from artificial intelligence. We are testing the code today.",
        "words_per_minute": 130,
        "filler_words": {
            "um": 1, "uh": 0, "ah": 0, "ahh": 0, "uhh": 0, "erm": 0, "like": 0, "you know": 0,
            "actually": 0, "basically": 0, "literally": 0, "sort of": 0, "kind of": 0
        },
        "pause_count": 0,
        "pause_duration": 0.0,
        "vocabulary_score": 85,
        "speaking_pace_score": 95,
        "duration": 10.0
    }
    vision = {
        "eye_contact_percentage": 85.0,
        "posture_score": 90.0,
        "expressions": {"confidence": 70.0, "neutral": 20.0, "nervousness": 10.0, "happiness": 10.0},
        "smile_frequency": 10.0,
        "head_stability": 80.0,
        "hand_movement_frequency": 20.0,
        "gesture_effectiveness": 40.0,
        "hand_detection_rate": 20.0
    }
    voice = {
        "stability_score": 75.0,
        "pitch_variation": 20.0,
        "energy_variation": 0.05
    }
    
    from app.services.scoring_engine import calculate_evidence_scores
    scores = calculate_evidence_scores(speech, vision, voice)
    
    from app.services.ai_analyzer import generate_local_report_fallback
    report = generate_local_report_fallback(
        topic="Is AI replacing jobs?",
        category="Technology",
        transcript=speech["transcript"],
        scores=scores
    )
    
    assert "expected_answer" in report
    assert "detailed_strengths" in report
    assert len(report["detailed_strengths"]) > 0

def test_speech_evaluation_weighted_and_safeguards():
    from app.services.ai_analyzer import analyze_video_speech
    from app.services.scoring_engine import calculate_evidence_scores
    
    speech = {
        "transcript": "hello",
        "transcript_confidence": 90,
        "words_per_minute": 130,
        "filler_words": {"um": 0}
    }
    vision = {
        "eye_contact_percentage": 80.0,
        "posture_score": 80.0,
        "expressions": {"confidence": 80.0, "neutral": 20.0, "nervousness": 0.0, "happiness": 0.0},
        "smile_frequency": 0.0,
        "head_stability": 80.0,
        "hand_movement_frequency": 20.0,
        "gesture_effectiveness": 40.0,
        "hand_detection_rate": 20.0
    }
    voice = {
        "stability_score": 80.0,
        "pitch_variation": 20.0,
        "energy_variation": 0.05
    }
    
    scores = calculate_evidence_scores(speech, vision, voice)
    
    # Confidence Score: 40% Voice Stability (32) + 30% Eye Contact (24) + 20% Posture (16) + 10% Speaking Pace (clamped speaking_pace_score 70 => 7) => 32+24+16+7 = 79
    assert scores["communication_effectiveness"]["confidence"]["score"] == 79
    
    # Professionalism Score: 40% Vocabulary (70 * 0.4 = 28) + 30% Posture (80 * 0.3 = 24) + 20% Fluency (100 * 0.2 = 20) + 10% Filler Word Reduction (100 * 0.1 = 10) => 28 + 24 + 20 + 10 = 82
    assert scores["communication_effectiveness"]["professionalism"]["score"] == 82
    
    # Test safeguards triggering on invalid audio path
    blocked_empty = analyze_video_speech("dummy_path", "Is AI replacing jobs?", "Technology")
    assert blocked_empty["status"] == "NO_SPEECH_DETECTED"
    assert blocked_empty["overall_score"] == 0

def test_speech_analysis_quality_improvements():
    from app.services.audio_processor import count_filler_words, clean_fillers_from_transcript
    
    # 1. Test repeat variations matching
    fillers = count_filler_words("uumm, uhhh, erm, like, you know, actually, basically, literally, kind of, sort of.")
    assert fillers["um"] == 1
    assert fillers["uhh"] == 1
    assert fillers["erm"] == 1
    assert fillers["like"] == 1
    assert fillers["you know"] == 1
    assert fillers["actually"] == 1
    assert fillers["basically"] == 1
    assert fillers["literally"] == 1
    assert fillers["sort of"] == 1
    assert fillers["kind of"] == 1
 
    # 2. Test clean_fillers_from_transcript
    raw = "So, um, like, actually, you know, we should go."
    cleaned = clean_fillers_from_transcript(raw)
    assert cleaned == "So, we should go."
 
    # 3. Test analyze_speech_metrics with filler occurrences
    words = [
        {"word": "So", "start": 0.0, "end": 0.3},
        {"word": "uumm", "start": 0.4, "end": 0.7},
        {"word": "like", "start": 0.8, "end": 1.1},
        {"word": "we", "start": 1.2, "end": 1.5},
        {"word": "should", "start": 1.6, "end": 1.9},
        {"word": "go", "start": 2.0, "end": 2.3}
    ]
    duration = 3.0
    metrics = analyze_speech_metrics(words, duration)
    assert metrics["raw_transcript"] == "So uumm like we should go"
    assert metrics["transcript"] == "So uumm like we should go"
    assert len(metrics["filler_occurrences"]) == 2
    assert metrics["filler_occurrences"][0]["filler"] == "um"
    assert metrics["filler_occurrences"][0]["start"] == 0.4
    assert metrics["filler_occurrences"][1]["filler"] == "like"
    assert metrics["filler_occurrences"][1]["start"] == 0.8

def test_silent_and_low_confidence_scenarios():
    from unittest.mock import patch
    from app.services.ai_analyzer import analyze_video_speech
    
    # Case 1: Silent audio (Empty transcript, speech duration under 2 seconds)
    with patch("app.services.ai_analyzer.process_audio") as mock_process:
        mock_process.return_value = {
            "raw_transcript": "",
            "transcript": "",
            "transcript_confidence": 0,
            "words_per_minute": 0,
            "filler_words": {},
            "duration": 10.0,
            "speech_duration": 0.5  # Under 2 seconds
        }
        res = analyze_video_speech("dummy_path", "Is AI replacing jobs?", "Technology")
        assert res["status"] == "NO_SPEECH_DETECTED"
        assert res["overall_score"] == 0
        assert "under 2.0 seconds" in res["feedback"]

    # Case 4: Very low-confidence audio with low speech duration
    with patch("app.services.ai_analyzer.process_audio") as mock_process:
        mock_process.return_value = {
            "raw_transcript": "hello",
            "transcript": "hello",
            "transcript_confidence": 10,
            "words_per_minute": 6,
            "filler_words": {},
            "duration": 10.0,
            "speech_duration": 0.5  # Under 2 seconds
        }
        res = analyze_video_speech("dummy_path", "Is AI replacing jobs?", "Technology")
        assert res["status"] == "NO_SPEECH_DETECTED"
        assert res["overall_score"] == 0
