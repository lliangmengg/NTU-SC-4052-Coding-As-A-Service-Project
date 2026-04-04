import uuid
from fastapi import APIRouter, HTTPException
from kombu.exceptions import OperationalError
from pydantic import BaseModel
from backend.core.celery_app import CELERY_QUEUE
from backend.core import state_manager
from backend.worker.tasks import run_pipeline_task

router = APIRouter()

class ProblemRequest(BaseModel):
    problem_description: str

@router.post("/solve")
async def solve(request: ProblemRequest):
    job_id = str(uuid.uuid4())
    state_manager.create_job(job_id)

    try:
        run_pipeline_task.apply_async(
            args=[request.problem_description, job_id],
            task_id=job_id,
            queue=CELERY_QUEUE,
        )
    except OperationalError as exc:
        state_manager.update_job(job_id, "FAILED", step="Queue unavailable. Could not submit task.")
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {str(exc)}") from exc
    
    return {"job_id": job_id, "status": "ACCEPTED"}

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job = state_manager.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return job