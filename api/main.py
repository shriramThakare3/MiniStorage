"""
api/main.py
-----------
FastAPI application entry point.

Started by Gunicorn in the Docker container:
    gunicorn api.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
"""
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from core.config import settings
from db.models import Base
from db.session import engine

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Mini Cloud Storage API",
        description=(
            "Upload, download, delete and organise files — "
            "backed by PostgreSQL metadata and on-disk file storage."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — open for development; tighten allow_origins in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    def on_startup():
        # Ensure storage root exists
        os.makedirs(settings.STORAGE_ROOT, exist_ok=True)
        logger.info("Storage root: %s", settings.STORAGE_ROOT)

        # Auto-create DB tables (idempotent)
        logger.info("Bootstrapping DB schema …")
        Base.metadata.create_all(bind=engine)
        logger.info("API ready — env=%s", settings.APP_ENV)

    return app


app = create_app()
