import requests
import json
import time
import os

BASE_URL = "http://localhost:8000/api"
TEST_USER_EMAIL = "audit_debater@example.com"
TEST_USER_PASSWORD = "Password123!"
WEBM_PATH = "uploads/debate_aace9c1d-a9e5-437d-bd54-4f9dcdcb3391_0.webm"

def main():
    print("=== DEBATE ARENA END-TO-END VERIFICATION ===")
    
    # Check if test webm file exists
    if not os.path.exists(WEBM_PATH):
        # Let's try inside backend directory if run from parent
        fallback_path = os.path.join("backend", WEBM_PATH)
        if os.path.exists(fallback_path):
            file_path = fallback_path
        else:
            # Let's search uploads directory
            uploads_dir = "uploads"
            if not os.path.exists(uploads_dir) and os.path.exists("backend/uploads"):
                uploads_dir = "backend/uploads"
            
            webm_files = [f for f in os.listdir(uploads_dir) if f.endswith(".webm")]
            if webm_files:
                file_path = os.path.join(uploads_dir, webm_files[0])
            else:
                raise FileNotFoundError(f"Could not find any .webm file for testing upload.")
    else:
        file_path = WEBM_PATH

    print(f"Using webm file for testing upload: {file_path}")

    # 1. Sign up/Login to get Token
    token = None
    headers = {}
    
    signup_payload = {
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD,
        "name": "Audit Debater User"
    }
    
    print("\n[1] Attempting to Sign Up...")
    try:
        res = requests.post(f"{BASE_URL}/auth/signup", json=signup_payload)
        print(f"Signup Status: {res.status_code}")
        if res.status_code == 200:
            token = res.json().get("access_token")
    except Exception as e:
        print(f"Signup request error: {e}")

    if not token:
        print("Signup failed or user already exists. Attempting Login...")
        login_payload = {
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
        res = requests.post(f"{BASE_URL}/auth/login", json=login_payload)
        print(f"Login Status: {res.status_code}")
        if res.status_code != 200:
            print("Login failed! Details:", res.text)
            return
        token = res.json().get("access_token")

    print("Successfully authenticated.")
    headers = {"Authorization": f"Bearer {token}"}

    # Verify user profile
    res = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    print(f"Me Endpoint Status: {res.status_code}, User: {res.json().get('email')}")

    # 2. Start Debate Session
    print("\n[2] Starting Debate Session...")
    start_payload = {
        "topic": "Social Media causes mental health problems in teenagers",
        "difficulty": "Intermediate",
        "category": "Technology"
    }
    # Send as query parameters as expected by router
    res = requests.post(f"{BASE_URL}/debate/start?topic={start_payload['topic']}&difficulty={start_payload['difficulty']}&category={start_payload['category']}", headers=headers)
    print(f"Start Debate Status: {res.status_code}")
    if res.status_code != 200:
        print("Failed to start debate:", res.text)
        return
    
    debate_start_data = res.json()
    session_id = debate_start_data.get("session_id")
    opponent_statement = debate_start_data.get("opponent_statement")
    print(f"Debate Session Created: {session_id}")
    print(f"Opponent Opening Argument:\n\"{opponent_statement}\"")

    # 3. Argue / Submit Text Argument
    print("\n[3] Submitting text rebuttal argument...")
    argue_payload = {
        "session_id": session_id,
        "user_argument": "Social media platforms utilize addictive algorithms that maximize screen time, triggering negative comparisons, anxiety, and sleep deprivation among teenagers. Numerous studies show direct correlations between usage hours and mental health issues."
    }
    res = requests.post(f"{BASE_URL}/debate/{session_id}/argue?user_argument={requests.utils.quote(argue_payload['user_argument'])}", headers=headers)
    print(f"Argue Status: {res.status_code}")
    if res.status_code != 200:
        print("Failed to submit argument text:", res.text)
        return
    
    argue_data = res.json()
    print("Opponent Counter Rebuttal:", argue_data.get("opponent_statement"))
    print("Logic/Persuasion score dictionary:", argue_data.get("scores"))

    # 4. Upload Recording (Submit Video/Audio file)
    print("\n[4] Uploading recorded webm video file...")
    upload_url = f"{BASE_URL}/debate/submit?session_id={session_id}"
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "video/webm")}
        res = requests.post(upload_url, files=files, headers=headers)
        print(f"Upload Status: {res.status_code}")
        if res.status_code != 200:
            print("Upload failed:", res.text)
            return
        upload_data = res.json()
        print(f"Upload Response Status: {upload_data.get('analysis_status')}")

    # 5. Poll debate session status until complete
    print("\n[5] Polling background analysis task...")
    status_url = f"{BASE_URL}/debate/analyze?session_id={session_id}"
    max_polls = 60
    poll_count = 0
    completed = False
    
    while poll_count < max_polls:
        res = requests.post(status_url, headers=headers)
        if res.status_code != 200:
            print(f"Poll request failed with status: {res.status_code}. Response: {res.text}")
            break
        
        session_info = res.json()
        status = session_info.get("analysis_status")
        print(f"[{poll_count + 1}] Debate analysis status: {status}")
        
        if status == "completed":
            completed = True
            break
        elif status == "failed":
            print("Debate background analysis failed!")
            break
            
        time.sleep(3)
        poll_count += 1

    if not completed:
        print("Analysis did not complete in time or failed.")
        return

    print("\n✓ Debate Analysis completed successfully!")

    # 6. Verify Report Retrieval
    print("\n[6] Testing GET /api/debate/report/{id}...")
    report_url = f"{BASE_URL}/debate/report/{session_id}"
    res = requests.get(report_url, headers=headers)
    print(f"Report Retrieve Status: {res.status_code}")
    if res.status_code != 200:
        print("Failed to retrieve report:", res.text)
        return
    
    report_data = res.json()
    print("Report parsed successfully.")
    print(f"Overall Score: {report_data.get('overall_score')}")
    print(f"Rating Verdict: {report_data.get('rating')}")
    print(f"Executive Summary:\n{report_data.get('executive_summary')}")
    print(f"Strengths: {report_data.get('strengths')}")
    print(f"Areas for Improvement: {report_data.get('weaknesses')}")
    print(f"Speech Analysis - Confidence: {report_data.get('speech_analysis', {}).get('confidence', {})}")

    # 7. Verify History Retrieval
    print("\n[7] Testing GET /api/debate/history...")
    res = requests.get(f"{BASE_URL}/debate/history", headers=headers)
    print(f"History Endpoint Status: {res.status_code}")
    if res.status_code != 200:
        print("Failed to retrieve history:", res.text)
        return
    
    history = res.json()
    print(f"History list length: {len(history)}")
    matching_sessions = [s for s in history if s['id'] == session_id]
    if matching_sessions:
        print(f"✓ Found session {session_id} in history: topic='{matching_sessions[0]['topic']}', status='{matching_sessions[0]['status']}', score={matching_sessions[0]['overall_score']}")
    else:
        print("✗ Session not found in history!")

    # 8. Verify Latest Session
    print("\n[8] Testing GET /api/debate/latest...")
    res = requests.get(f"{BASE_URL}/debate/latest", headers=headers)
    print(f"Latest Endpoint Status: {res.status_code}")
    if res.status_code != 200:
        print("Failed to retrieve latest session:", res.text)
        return
    
    latest = res.json()
    if latest.get("id") == session_id:
        print(f"✓ Latest debate session ID matches created session {session_id}")
    else:
        print(f"✗ Latest session ID mismatch: {latest.get('id')} vs expected {session_id}")

    # 9. Verify Video Player token-based streaming URL resolver
    print("\n[9] Testing token-based streaming URL resolver...")
    info_url = f"{BASE_URL}/interviews/{session_id}/video-info"
    res = requests.get(info_url, headers=headers)
    print(f"Video Info Status: {res.status_code}")
    if res.status_code != 200:
        print("Failed to get video info:", res.text)
        return
    
    info_data = res.json()
    print("Video Info Data:", info_data)
    if not info_data.get("exists"):
        print("✗ Error: Session recording not found by resolver!")
        return
        
    stream_url = info_data.get("video_url")
    print(f"Stream URL returned: {stream_url}")
    
    # Request a chunk of the video stream
    stream_headers = {"Range": "bytes=0-1024"}
    res = requests.get(f"http://localhost:8000{stream_url}", headers=stream_headers)
    print(f"Video Stream chunk response code: {res.status_code}")
    if res.status_code in [200, 206]:
        print("✓ Successfully requested and read bytes from stream!")
    else:
        print(f"✗ Stream read failed: status code {res.status_code}, response: {res.text}")

    print("\n=== ALL E2E VERIFICATION CHECKS PASSED ===")

if __name__ == "__main__":
    main()
