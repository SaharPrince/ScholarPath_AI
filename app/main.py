from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import database_is_ready, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Official-source scholarship discovery and eligibility matching.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Basic service and database readiness check."""
    if not database_is_ready():
        return {"status": "degraded", "database": "unavailable"}
    return {"status": "ok", "database": "ready"}
