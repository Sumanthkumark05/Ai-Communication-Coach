import requests
import json
import time

BASE_URL = "http://localhost:8000/api"

def test_flow():
    # 1. Sign up
    email = f"test_{int(time.time())}@example.com"
    payload = {
        "email": email,
        "password": "testpassword123",
        "name": "Audit Test User"
    }
    print(f"Signing up user: {email}...")
    res = requests.post(f"{BASE_URL}/auth/signup", json=payload)
    print("Signup Status:", res.status_code)
    print("Signup Response:", res.json())
    
    # 2. Login
    print("Logging in...")
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": "testpassword123"
    })
    print("Login Status:", res.status_code)
    data = res.json()
    print("Login Response:", data)
    
    if "access_token" not in data:
        print("Error: No access token returned.")
        return
        
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Call get me
    print("Calling /auth/me...")
    res = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    print("Get Me Status:", res.status_code)
    print("Get Me Response:", res.json())
    
    # 4. Call generate-topic
    print("Calling /generate-topic...")
    res = requests.get(f"{BASE_URL}/generate-topic", headers=headers)
    print("Generate Topic Status:", res.status_code)
    print("Generate Topic Response:", res.json())
    
    # 5. Call jam/session
    print("Calling /jam/session...")
    session_payload = {
        "topic": "Test Topic",
        "category": "Technology",
        "instant_start": True,
        "preparation_mode": False,
        "skip_preparation": False
    }
    res = requests.post(f"{BASE_URL}/jam/session", json=session_payload, headers=headers)
    print("Create Session Status:", res.status_code)
    print("Create Session Response:", res.json())

if __name__ == "__main__":
    test_flow()
