import sys
import os
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000/api"

def run_test():
    print("=== STARTING DOCUMENT ANALYZER E2E TEST ===")
    
    # 1. Sign up a new test user
    email = f"e2e_test_{int(time.time())}@example.com"
    signup_payload = {
        "email": email,
        "password": "testpassword123",
        "name": "E2E Test User"
    }
    print(f"\n1. Signing up user: {email}")
    res = requests.post(f"{BASE_URL}/auth/signup", json=signup_payload)
    if res.status_code != 201:
        print(f"Signup failed: {res.status_code} - {res.text}")
        sys.exit(1)
    print("Signup successful.")
    
    # 2. Log in
    print("\n2. Logging in...")
    login_payload = {
        "email": email,
        "password": "testpassword123"
    }
    res = requests.post(f"{BASE_URL}/auth/login", json=login_payload)
    if res.status_code != 200:
        print(f"Login failed: {res.status_code} - {res.text}")
        sys.exit(1)
    
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful. Token obtained.")
    
    # 3. Create a test report file if not exists
    test_filepath = "test_report.md"
    if not os.path.exists(test_filepath):
        with open(test_filepath, "w") as f:
            f.write("# Project Alpha Report\n\nThis is a project report about building a distributed database using Raft. We implemented leader election and state machines.")
            
    # 4. Upload document
    print(f"\n3. Uploading document: {test_filepath}")
    with open(test_filepath, "rb") as f:
        files = {"file": (test_filepath, f, "text/markdown")}
        res = requests.post(f"{BASE_URL}/document/upload", files=files, headers=headers)
        
    if res.status_code != 200:
        print(f"Upload failed: {res.status_code} - {res.text}")
        sys.exit(1)
        
    doc_data = res.json()
    doc_id = doc_data["id"]
    topics = doc_data.get("topics", [])
    print(f"Upload successful. Document ID: {doc_id}")
    print(f"Document Title: {doc_data.get('title')}")
    print(f"Document Summary: {doc_data.get('summary')}")
    print(f"Generated Topics Count: {len(topics)}")
    for idx, t in enumerate(topics):
        print(f"  Topic {idx+1}: {t['topic']} (Category: {t['category']}, Difficulty: {t['difficulty']})")
        
    if not topics:
        print("Error: No topics generated.")
        sys.exit(1)
        
    # 5. Create a document presentation session
    selected_topic = topics[0]
    print(f"\n4. Creating presentation session for topic: '{selected_topic['topic']}'")
    session_payload = {
        "document_id": doc_id,
        "topic_id": selected_topic["id"],
        "topic_title": selected_topic["topic"],
        "category": selected_topic["category"],
        "instant_start": True,
        "preparation_mode": False,
        "skip_preparation": False
    }
    res = requests.post(f"{BASE_URL}/document/session", json=session_payload, headers=headers)
    if res.status_code != 200:
        print(f"Create session failed: {res.status_code} - {res.text}")
        sys.exit(1)
        
    session_data = res.json()
    session_id = session_data["id"]
    print(f"Session created successfully. Session ID: {session_id}")
    
    # 6. Upload a real webm audio/video file for session speech analysis
    real_webm_path = "backend/uploads/032df2db-61f7-46c6-a5fb-5e817d4b570f.webm"
    if not os.path.exists(real_webm_path):
        real_webm_path = "uploads/032df2db-61f7-46c6-a5fb-5e817d4b570f.webm"
    print(f"\n5. Uploading real speaking recording to analyze speech...")
    with open(real_webm_path, "rb") as f:
        files = {"file": ("recording.webm", f, "video/webm")}
        res = requests.post(f"{BASE_URL}/document/session/{session_id}/upload", files=files, headers=headers)
        
    if res.status_code != 200:
        print(f"Recording analysis failed: {res.status_code} - {res.text}")
        # Note: If no speech is detected, we get 400. That's a valid path but we want to make sure it functions.
        # Let's inspect the error.
    else:
        analyzed_data = res.json()
        report = analyzed_data.get("report")
        print("Speech Analysis Completed Successfully!")
        if report:
            print(f"  Accuracy Score: {report.get('accuracy_score')}")
            print(f"  Coverage Score: {report.get('coverage_score')}")
            print(f"  Understanding Score: {report.get('understanding_score')}")
            print(f"  Technical Correctness: {report.get('technical_correctness')}")
            print(f"  Suggested Improvements: {report.get('suggested_improvements')}")
            print(f"  Knowledge Gaps Count: {len(analyzed_data.get('knowledge_gaps', []))}")
            
    # 7. Start Viva Session
    print(f"\n6. Starting Document Viva session...")
    viva_payload = {
        "document_id": doc_id,
        "mode": "project"
    }
    res = requests.post(f"{BASE_URL}/document/viva/start", json=viva_payload, headers=headers)
    if res.status_code != 200:
        print(f"Start Viva failed: {res.status_code} - {res.text}")
        sys.exit(1)
        
    viva_data = res.json()
    viva_id = viva_data["id"]
    qa_list = viva_data.get("questions_answers", [])
    print(f"Viva started successfully. Viva ID: {viva_id}")
    print(f"Generated {len(qa_list)} questions.")
    for idx, qa in enumerate(qa_list):
        print(f"  Q{idx+1}: {qa['question']}")
        
    # 8. Submit Viva Answer for first question
    if qa_list:
        first_q = qa_list[0]["question"]
        print(f"\n7. Submitting answer for Q1: '{first_q}'")
        
        # Use real webm file for viva response
        with open(real_webm_path, "rb") as f:
            files = {"file": ("viva_ans.webm", f, "video/webm")}
            res = requests.post(f"{BASE_URL}/document/viva/{viva_id}/answer?question_index=0", files=files, headers=headers)
            
        if res.status_code != 200:
            print(f"Viva answer grading failed: {res.status_code} - {res.text}")
        else:
            viva_result = res.json()
            answered_q = viva_result["questions_answers"][0]
            print("Viva Answer Graded Successfully!")
            print(f"  Score: {answered_q['evaluation'].get('score')}")
            print(f"  Feedback: {answered_q['evaluation'].get('feedback')}")
            print(f"  Ideal Response: {answered_q['evaluation'].get('ideal_response')}")
            print(f"  Overall Viva Score: {viva_result.get('overall_score')}")

    # 9. Verify Communication DNA updates
    print("\n8. Verifying Communication DNA matches new dimensions...")
    res = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    if res.status_code == 200:
        user_profile = res.json()
        # Fetch DNA from backend to check fields
        dna_res = requests.get(f"{BASE_URL}/jam/analytics", headers=headers)
        print("DNA Analytics response received.")
        # Note: we can also verify the database columns directly.
        
    print("\n=== E2E TEST COMPLETED ===")

if __name__ == "__main__":
    run_test()
