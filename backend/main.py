from fastapi import FastAPI
from contextlib import asynccontextmanager
from backend.api.routes import router as tutor_router
from backend.core import state_manager
from backend.core.celery_app import is_celery_broker_available


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not state_manager.is_redis_available():
        print("[WARN] Redis state store unavailable at startup. API will use in-memory fallback.", flush=True)
    if not is_celery_broker_available():
        print("[WARN] Celery broker unavailable at startup. /solve enqueue requests may fail.", flush=True)
    yield


app = FastAPI(
    title="AlgoTutor CaaS",
    description="Coding-as-a-Service for Algorithmic Tutoring",
    version="1.0.0",
    lifespan=lifespan,
)

# DEFINE THE BASE ROUTE HERE
app.include_router(tutor_router, prefix="/api/v1/tutor", tags=["Tutor Engine"])

@app.get("/")
async def root():
    return {
        "message": "AlgoTutor CaaS API is Online",
        "docs": "/docs",
        "version": "v1"
    }