import time
import requests

def test_async_solve_flow():
    base_url = "http://127.0.0.1:8000/api/v1/tutor"
    
    # 1. Start the job
    payload = {"problem_description": "Reverse a Linked List"}
    res = requests.post(f"{base_url}/solve", json=payload).json()
    job_id = res["job_id"]
    assert res["status"] == "ACCEPTED"
    
    # 2. Poll until complete
    completed = False
    for _ in range(15): # Max 15 seconds
        status_res = requests.get(f"{base_url}/status/{job_id}").json()
        print(f"Current Step: {status_res['current_step']}")
        
        if status_res["status"] == "COMPLETED":
            assert "def solution()" in status_res["code"]
            completed = True
            break
        time.sleep(1)
    
    assert completed is True