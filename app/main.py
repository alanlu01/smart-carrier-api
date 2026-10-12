from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_pool, ping_database
from app.routes import admin, public, robot
from app.schemas import HealthResponse, ReadinessResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="Smart Carrier API",
    version="0.2.0",
    description="Cloud task API for the Smart Carrier web client and ROS2 robot.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.include_router(public.router)
app.include_router(robot.router)
app.include_router(admin.router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return HealthResponse(
        environment=settings.app_env,
        database_configured=settings.database_configured,
    )


@app.get("/ready", response_model=ReadinessResponse, tags=["system"])
def readiness():
    try:
        ping_database()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Oracle Database is unavailable",
        ) from error
    return ReadinessResponse()
