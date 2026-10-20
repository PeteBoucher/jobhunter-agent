"""Text embeddings via the OpenAI embeddings API.

Used to compare a user's "not interested" reasons against job titles and
locations (see ``job_matcher``). Calls the HTTP API with ``requests`` rather
than the ``openai`` SDK so the Lambda image needs no extra dependency.

Vectors are L2-normalised float32, so cosine similarity is a dot product.
They are stored as raw bytes (``to_bytes``/``from_bytes``) rather than with
pgvector — similarity is computed in numpy per user, and bytes keep the
SQLite test database working.
"""

import logging
import os
import time
from typing import List, Optional

import numpy as np
import requests

logger = logging.getLogger("jobhunter.embeddings")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512

_API_URL = "https://api.openai.com/v1/embeddings"
_BATCH_SIZE = 1000
_MAX_RETRIES = 5


def embed_texts(texts: List[str], api_key: Optional[str] = None) -> np.ndarray:
    """Embed ``texts``; returns an (n, EMBEDDING_DIMENSIONS) normalised array."""
    if not texts:
        return np.zeros((0, EMBEDDING_DIMENSIONS), dtype=np.float32)
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    chunks = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = [t.strip() or " " for t in texts[start : start + _BATCH_SIZE]]
        chunks.append(_embed_batch(batch, key))
    vectors = np.vstack(chunks).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1.0, norms)


def _embed_batch(batch: List[str], key: str) -> np.ndarray:
    for attempt in range(_MAX_RETRIES):
        resp = requests.post(
            _API_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": EMBEDDING_MODEL,
                "input": batch,
                "dimensions": EMBEDDING_DIMENSIONS,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return np.array([d["embedding"] for d in data], dtype=np.float32)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2**attempt
            logger.warning(
                "Embeddings API HTTP %s, retrying in %ss", resp.status_code, wait
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Embeddings API failed after {_MAX_RETRIES} attempts")


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "embed_texts",
    "from_bytes",
    "to_bytes",
]
