"""Health endpoints — public, no auth required."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db import get_session
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
        db_status = "up"
        overall = "ok"
    except Exception:
        db_status = "down"
        overall = "degraded"
    return HealthResponse(
        status=overall,
        version=__version__,
        database=db_status,
        timestamp=datetime.now(UTC),
    )


@router.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": "uod-backend",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
    }
