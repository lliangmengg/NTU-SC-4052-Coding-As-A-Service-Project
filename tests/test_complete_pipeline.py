import requests
import time
import os
import pytest
from dotenv import load_dotenv


def _assert_api_reachable(base_url: str):
    health_url = base_url.replace("/api/v1/tutor", "/")
    try:
        response = requests.get(health_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        pytest.fail(f"API is not reachable at {health_url}: {exc}", pytrace=False)

def test_full_agentic_flow():
    load_dotenv()

    BASE_URL = os.environ.get("BASE_URL")
    assert BASE_URL, "BASE_URL is not configured in environment."
    _assert_api_reachable(BASE_URL)
    PROBLEM = "Write a function to find the middle node of a linked list. Handle empty lists."
    
    print(f"\n[START] Sending Problem: {PROBLEM}")
    
    payload = {"problem_description": PROBLEM}
    response = requests.post(f"{BASE_URL}/solve", json=payload, timeout=20)
    assert response.status_code == 200, f"API Request Failed: {response.text}"
        
    job_id = response.json()["job_id"]
    print(f"[INFO] Job ID: {job_id}")

    start_time = time.time()
    max_wait = 180
    last_step = ""
    last_log_index = 0

    while time.time() - start_time < max_wait:
        status_res = requests.get(f"{BASE_URL}/status/{job_id}", timeout=20).json()
        current_status = status_res.get("status")
        current_step = status_res.get("current_step")
        logs = status_res.get("logs", [])

        # Stream any new backend log entries since the previous poll.
        if isinstance(logs, list) and len(logs) > last_log_index:
            for log_line in logs[last_log_index:]:
                print(log_line)
            last_log_index = len(logs)

        if current_step != last_step:
            print(f"[STATUS] {current_step}")
            last_step = current_step

        if current_status == "COMPLETED":
            print("\n[SUCCESS] Pipeline Finished")
            print("-" * 30)
            print("CODE:")
            print(status_res.get("code"))
            print("-" * 30)
            print("ANALYSIS:")
            print(status_res.get("explanation"))
            assert status_res.get("code")
            assert status_res.get("explanation")
            return
            
        if current_status == "FAILED":
            print(f"\n[FAILURE] {status_res.get('current_step')}")
            pytest.fail(f"Pipeline failed: {status_res.get('current_step')}")

        time.sleep(5)

    pytest.fail("Pipeline timeout: test exceeded maximum wait time.")

if __name__ == "__main__":
    test_full_agentic_flow()