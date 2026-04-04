from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger

from backend.core import state_manager
from backend.core.celery_app import (
    CELERY_QUEUE,
    CELERY_TASK_RETRY_DELAY_SECONDS,
    CELERY_TASK_RETRY_MAX_RETRIES,
    celery_app,
)
from backend.engine.orchestrator import run_agentic_pipeline

logger = get_task_logger(__name__)


@celery_app.task(name="backend.worker.tasks.run_pipeline_task", bind=True, queue=CELERY_QUEUE)
def run_pipeline_task(self, problem_description: str, job_id: str) -> dict:
    """
    Celery wrapper task for the existing agentic pipeline.

    This task intentionally keeps business logic unchanged by delegating all
    orchestration to run_agentic_pipeline.
    """
    logger.info("Starting pipeline task job_id=%s", job_id)
    try:
        run_agentic_pipeline(problem_description, job_id)
        logger.info("Finished pipeline task job_id=%s", job_id)
        return {"job_id": job_id, "status": "DISPATCHED"}
    except Exception as exc:
        logger.exception("Worker task failed job_id=%s", job_id)
        try:
            raise self.retry(
                exc=exc,
                countdown=CELERY_TASK_RETRY_DELAY_SECONDS,
                max_retries=CELERY_TASK_RETRY_MAX_RETRIES,
            )
        except MaxRetriesExceededError:
            state_manager.update_job(
                job_id,
                "FAILED",
                step=f"Worker failed after retries: {str(exc)}",
            )
            return {"job_id": job_id, "status": "FAILED"}
