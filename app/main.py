from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import public, robot
from app.schemas import HealthResponse

settings = get_settings()
app = FastAPI(
    title="Smart Carrier API",
    version="0.1.0",
    description="Cloud task API for the Smart Carrier web client and ROS2 robot.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.include_router(public.router)
app.include_router(robot.router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return HealthResponse(
        environment=settings.app_env,
        database_configured=settings.database_configured,
    )
