"""Test fixtures.

Strategy:
- A real Postgres container (via testcontainers) is required because the
  ORM uses JSONB and asyncpg.
- The container is started once per session (slow) and migrations run
  against it.
- Each test runs inside a SAVEPOINT that rolls back, so state is isolated
  without re-running Alembic per test.
- If Docker is unavailable the whole suite is skipped — we don't pretend
  SQLite is a substitute for Postgres-specific features.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set env BEFORE importing the app — config.get_settings caches on first
# access and any later mutation would be ignored.
os.environ.setdefault("NEXTAUTH_SECRET", "test-secret-do-not-use-in-prod")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/placeholder")


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Provide a Postgres URL.

    Two modes:
    - `UOD_BACKEND_USE_EXTERNAL_DB=1` → trust DATABASE_URL as-is (used by CI
      where a `postgres` service container is already running).
    - otherwise → spin up a testcontainers Postgres for local dev. Skips
      the suite if Docker is unavailable.
    """
    if os.environ.get("UOD_BACKEND_USE_EXTERNAL_DB"):
        url = os.environ.get("DATABASE_URL")
        if not url or "placeholder" in url:
            pytest.skip("UOD_BACKEND_USE_EXTERNAL_DB set but DATABASE_URL is missing/placeholder")
        yield url
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as exc:  # docker unreachable, etc.
        pytest.skip(f"Postgres container unavailable: {exc}")

    raw = container.get_connection_url()
    # testcontainers gives psycopg2 form; rewrite to asyncpg.
    async_url = raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    os.environ["DATABASE_URL"] = async_url

    # wait for readiness
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            import socket

            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(5432))
            with socket.create_connection((host, port), timeout=2):
                break
        except Exception:
            time.sleep(0.5)

    yield async_url

    container.stop()


@pytest.fixture(scope="session")
async def _migrated_db(postgres_url: str) -> AsyncIterator[None]:
    """Apply all Alembic migrations once per test session."""
    from alembic.config import Config

    from alembic import command
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    await reset_engine()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    # Alembic env reads via get_settings, which reads env var.
    await asyncio.get_event_loop().run_in_executor(None, lambda: command.upgrade(cfg, "head"))
    yield


@pytest.fixture(scope="session")
async def _engine(_migrated_db: None, postgres_url: str):
    """One async engine for the whole test session — matches the session-
    scoped event loop set in pyproject.toml.
    """
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


async def _truncate_all(engine) -> None:
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE instance_relations, audit_log, instances, harvest_jobs "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
async def session(_engine) -> AsyncIterator[AsyncSession]:
    """Clean session per test, with a TRUNCATE between tests."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await _truncate_all(_engine)


@pytest.fixture
async def client(_engine) -> AsyncIterator[AsyncClient]:
    """ASGI test client. The app uses its own get_engine(), which is the
    same DATABASE_URL we migrated, so it sees the migrated schema.
    """
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await _truncate_all(_engine)


# ── auth helpers ────────────────────────────────────────────────────────


def _token(role: str, login: str = "octocat", ttl_seconds: int = 3600) -> str:
    now = datetime.now(UTC)
    payload = {
        "login": login,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    secret = os.environ["NEXTAUTH_SECRET"]
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def viewer_token() -> str:
    return _token("viewer")


@pytest.fixture
def editor_token() -> str:
    return _token("editor", login="alice")


@pytest.fixture
def admin_token() -> str:
    return _token("admin", login="root-admin")


@pytest.fixture
def auth_headers():
    """Factory: pass token, get headers dict."""

    def _make(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _make
