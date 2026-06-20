import requests
import json
import os

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY environment variable is missing")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Test Llama-3.3-70b-versatile
payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "user", "content": "Hello! What is your name?"}
    ]
}

print("Testing llama-3.3-70b-versatile...")
try:
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=10
    )
    print("Status Code:", res.status_code)
    if res.status_code == 200:
        print("Response:", res.json()["choices"][0]["message"]["content"])
    else:
        print("Response Text:", res.text)
except Exception as e:
    print("Error:", e)

# Test llama-3.1-8b-instant
payload = {
    "model": "llama-3.1-8b-instant",
    "messages": [
        {"role": "user", "content": "Hello! What is your name?"}
    ]
}
print("\nTesting llama-3.1-8b-instant...")
try:
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=10
    )
    print("Status Code:", res.status_code)
    if res.status_code == 200:
        print("Response:", res.json()["choices"][0]["message"]["content"])
    else:
        print("Response Text:", res.text)
except Exception as e:
    print("Error:", e)
