"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_embeddings_api(monkeypatch):
    """Never let a test reach the OpenAI embeddings API (and bill for it).

    Without a key, `embed_texts` raises, which every caller treats as "vectors
    unavailable". Tests that need vectors pass a fake embedder explicitly.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
