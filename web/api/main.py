"""Jobhunter FastAPI application."""

import logging
import logging.handlers
import os
import queue
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# Ensure project root (jobhunter-agent/) is on the Python path so that
# `from src.xxx import ...` works when running from web/api/.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from auth import decode_jwt  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from routers import (  # noqa: E402
    applications_router,
    auth_router,
    jobs_router,
    preferences_router,
    profile_router,
)


class _LokiLogHandler(logging.Handler):
    """Non-blocking log handler that ships records to Grafana Cloud Loki.

    Reads LOKI_URL, LOKI_USER, LOKI_TOKEN from env.
    Silently drops records if the endpoint is unreachable — never crashes the API.
    """

    def __init__(self):
        super().__init__()
        loki_url = os.environ.get("LOKI_URL", "").rstrip("/")
        self._url = loki_url + "/loki/api/v1/push"
        self._user = os.environ.get("LOKI_USER", "")
        self._token = os.environ.get("LOKI_TOKEN", "")
        self._session = requests.Session()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            ts_ns = str(int(record.created * 1e9))
            payload = {
                "streams": [
                    {
                        "stream": {
                            "service": "jobhunter-api",
                            "level": record.levelname.lower(),
                            "logger": record.name,
                        },
                        "values": [[ts_ns, msg]],
                    }
                ]
            }
            self._session.post(
                self._url,
                json=payload,
                auth=(self._user, self._token),
                timeout=2,
            )
        except Exception:
            self.handleError(record)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    loki_url = os.environ.get("LOKI_URL")
    if loki_url:
        # Ship logs to Loki; queue keeps it non-blocking
        loki_handler = _LokiLogHandler()
        loki_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        log_queue: queue.Queue = queue.Queue(maxsize=1000)
        queue_handler = logging.handlers.QueueHandler(log_queue)
        listener = logging.handlers.QueueListener(
            log_queue, loki_handler, respect_handler_level=True
        )
        listener.start()
        logging.getLogger().addHandler(queue_handler)
        logging.getLogger("jobhunter").info("Loki log shipping enabled → %s", loki_url)


_setup_logging()
logger = logging.getLogger("jobhunter.api")

app = FastAPI(
    title="Jobhunter API",
    description="REST API for the Jobhunter Agent web frontend",
    version="1.0.0",
)

# CORS — allow the Next.js frontend (localhost:3000 in dev, Vercel in prod)
_raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
if "*" in _origins:
    raise RuntimeError("CORS_ORIGINS must not be '*' — set explicit allowed origins")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers[
        "Strict-Transport-Security"
    ] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()

    # Best-effort user identity from JWT — don't fail if missing/invalid
    user = "anonymous"
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = decode_jwt(auth[7:])
            user = payload.get("email") or payload.get("sub", "unknown")
        except Exception:
            pass

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "unhandled_error method=%s path=%s user=%s duration_ms=%d error=%r",
            request.method,
            request.url.path,
            user,
            duration_ms,
            exc,
            exc_info=True,
        )
        raise

    duration_ms = int((time.monotonic() - start) * 1000)
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(
        level,
        "request method=%s path=%s status=%d duration_ms=%d user=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        user,
    )
    return response


app.include_router(auth_router.router)
app.include_router(jobs_router.router)
app.include_router(profile_router.router)
app.include_router(preferences_router.router)
app.include_router(applications_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
