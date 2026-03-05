"""Jobhunter FastAPI application."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Ensure project root (jobhunter-agent/) is on the Python path so that
# `from src.xxx import ...` works when running from web/api/.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .routers import (  # noqa: E402
    applications_router,
    auth_router,
    jobs_router,
    preferences_router,
    profile_router,
)

app = FastAPI(
    title="Jobhunter API",
    description="REST API for the Jobhunter Agent web frontend",
    version="1.0.0",
)

# CORS — allow the Next.js frontend (localhost:3000 in dev, Vercel in prod)
_raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(jobs_router.router)
app.include_router(profile_router.router)
app.include_router(preferences_router.router)
app.include_router(applications_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
