import requests
import time

URL = "http://localhost:5000/api/v1/intent"

def submit():
    payload = {
        "intent_type": "resilience",
        "target": {"target_type": "node", "identifier": "node-C"},
        "parameters": {"protection_mode": "space-diversity"},
        "always_apply": True
    }
    r = requests.post(URL, json=payload)
    return r.json()

print("--- First Submission (Fallback) ---")
res1 = submit()
print(f"Status: {res1.get('status')}")
print(f"Explanation: {res1.get('explanation')}")

time.sleep(2)

print("\n--- Second Submission (No-Op) ---")
res2 = submit()
print(f"Status: {res2.get('status')}")
print(f"Explanation: {res2.get('explanation')}")
