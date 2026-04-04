import os

from celery import Celery
import redis


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


REDIS_URL = _get_env("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_QUEUE = _get_env("CELERY_QUEUE", "pipeline")
CELERY_RESULT_EXPIRES_SECONDS = int(_get_env("CELERY_RESULT_EXPIRES_SECONDS", "86400"))
CELERY_TASK_TIME_LIMIT_SECONDS = int(_get_env("CELERY_TASK_TIME_LIMIT_SECONDS", "900"))
CELERY_TASK_SOFT_TIME_LIMIT_SECONDS = int(
    _get_env("CELERY_TASK_SOFT_TIME_LIMIT_SECONDS", "840")
)
CELERY_TASK_RETRY_MAX_RETRIES = int(_get_env("CELERY_TASK_RETRY_MAX_RETRIES", "1"))
CELERY_TASK_RETRY_DELAY_SECONDS = int(_get_env("CELERY_TASK_RETRY_DELAY_SECONDS", "5"))


celery_app = Celery(
    "coding_as_a_service",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_default_queue=CELERY_QUEUE,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=CELERY_RESULT_EXPIRES_SECONDS,
    task_track_started=True,
    task_time_limit=CELERY_TASK_TIME_LIMIT_SECONDS,
    task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
)


def is_celery_broker_available() -> bool:
    try:
        redis.Redis.from_url(REDIS_URL).ping()
        return True
    except redis.RedisError:
        return False
