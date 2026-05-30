"""FastAPI application factory.

Importing this module side-effect-free; the app is built by `create_app()`
so tests can override settings cleanly.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.db import reset_engine
from app.routers import health, instances


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Touch settings early so a misconfigured env aborts startup.
    get_settings()
    yield
    await reset_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="uod-backend",
        version=__version__,
        description=(
            "Universal Ontology Definition — instance store API.\n\n"
            "Class definitions live in the public GitHub repo "
            "`ramphias/universal-ontology-definition`; this service owns the "
            "private, queryable instance store."
        ),
        lifespan=_lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(instances.router)
    return app


app = create_app()
