import time
import requests
import os
import pytest


def _assert_api_reachable(base_url: str):
    health_url = base_url.replace("/api/v1/tutor", "/")
    try:
        response = requests.get(health_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        pytest.fail(f"API is not reachable at {health_url}: {exc}", pytrace=False)

def test_async_solve_flow():
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000/api/v1/tutor")
    _assert_api_reachable(base_url)
    
    # 1. Start the job
    payload = {"problem_description": "Reverse a Linked List"}
    try:
        res = requests.post(f"{base_url}/solve", json=payload, timeout=20).json()
    except requests.RequestException as exc:
        pytest.fail(f"Failed to submit solve request: {exc}", pytrace=False)
    job_id = res["job_id"]
    assert res["status"] == "ACCEPTED"
    
    # 2. Poll until complete
    status_res = {}
    for _ in range(60):  # Max 180 seconds
        status_res = requests.get(f"{base_url}/status/{job_id}", timeout=15).json()
        print(f"Current Step: {status_res['current_step']}")
        
        if status_res["status"] in {"COMPLETED", "FAILED"}:
            break
        time.sleep(3)
    
    assert status_res.get("status") == "COMPLETED", f"Pipeline did not complete successfully: {status_res}"
    assert status_res.get("code")
    assert status_res.get("explanation")