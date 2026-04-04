import os
from typing import Dict, Any, Optional

import redis


REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
JOB_STATE_TTL_SECONDS = int(os.getenv("JOB_STATE_TTL_SECONDS", "86400"))

_redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# Fallback for environments where Redis is not reachable.
_jobs_fallback: Dict[str, Dict[str, Any]] = {}
_redis_unavailable_logged = False


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _job_logs_key(job_id: str) -> str:
    return f"job:{job_id}:logs"


def _try_redis_ping() -> bool:
    global _redis_unavailable_logged
    try:
        _redis_client.ping()
        return True
    except redis.RedisError:
        if not _redis_unavailable_logged:
            print("[WARN] Redis unavailable, falling back to in-memory state manager.", flush=True)
            _redis_unavailable_logged = True
        return False


def is_redis_available() -> bool:
    return _try_redis_ping()


def create_job(job_id: str):
    if _try_redis_ping():
        fields = {
            "status": "PROCESSING",
            "current_step": "Initializing Agents",
            "code": "",
            "explanation": "",
        }
        pipe = _redis_client.pipeline()
        pipe.hset(_job_key(job_id), mapping=fields)
        pipe.delete(_job_logs_key(job_id))
        pipe.expire(_job_key(job_id), JOB_STATE_TTL_SECONDS)
        pipe.expire(_job_logs_key(job_id), JOB_STATE_TTL_SECONDS)
        pipe.execute()
        return

    _jobs_fallback[job_id] = {
        "status": "PROCESSING",
        "current_step": "Initializing Agents",
        "code": None,
        "explanation": None,
        "logs": [],
    }


def update_job(job_id: str, status: str, step: str = None, code: str = None, explanation: str = None):
    if _try_redis_ping():
        if not _redis_client.exists(_job_key(job_id)):
            return

        updates: Dict[str, str] = {}
        if status:
            updates["status"] = status
        if step:
            updates["current_step"] = step
        if code is not None:
            updates["code"] = code
        if explanation is not None:
            updates["explanation"] = explanation

        pipe = _redis_client.pipeline()
        if updates:
            pipe.hset(_job_key(job_id), mapping=updates)
        pipe.expire(_job_key(job_id), JOB_STATE_TTL_SECONDS)
        pipe.expire(_job_logs_key(job_id), JOB_STATE_TTL_SECONDS)
        pipe.execute()
        return

    if job_id in _jobs_fallback:
        if status:
            _jobs_fallback[job_id]["status"] = status
        if step:
            _jobs_fallback[job_id]["current_step"] = step
        if code is not None:
            _jobs_fallback[job_id]["code"] = code
        if explanation is not None:
            _jobs_fallback[job_id]["explanation"] = explanation


def append_log(job_id: str, log_line: str):
    if _try_redis_ping():
        if not _redis_client.exists(_job_key(job_id)):
            return
        pipe = _redis_client.pipeline()
        pipe.rpush(_job_logs_key(job_id), log_line)
        pipe.expire(_job_key(job_id), JOB_STATE_TTL_SECONDS)
        pipe.expire(_job_logs_key(job_id), JOB_STATE_TTL_SECONDS)
        pipe.execute()
        return

    if job_id in _jobs_fallback:
        _jobs_fallback[job_id].setdefault("logs", []).append(log_line)


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    if _try_redis_ping():
        if not _redis_client.exists(_job_key(job_id)):
            return None

        data = _redis_client.hgetall(_job_key(job_id))
        logs = _redis_client.lrange(_job_logs_key(job_id), 0, -1)

        code = data.get("code", "")
        explanation = data.get("explanation", "")

        return {
            "status": data.get("status", "PROCESSING"),
            "current_step": data.get("current_step", "Initializing Agents"),
            "code": code if code else None,
            "explanation": explanation if explanation else None,
            "logs": logs,
        }

    return _jobs_fallback.get(job_id)