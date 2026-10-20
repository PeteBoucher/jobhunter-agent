"""Tests for the OpenAI embeddings client (src/embeddings.py)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src import embeddings


def _response(status, vectors=None):
    resp = MagicMock(status_code=status)
    if vectors is not None:
        # API may return items out of order; the client sorts by index
        data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
        resp.json.return_value = {"data": list(reversed(data))}
    resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


def test_requires_api_key():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        embeddings.embed_texts(["hello"])


def test_empty_input_needs_no_key():
    assert embeddings.embed_texts([]).shape == (0, embeddings.EMBEDDING_DIMENSIONS)


@patch("src.embeddings.requests.post")
def test_vectors_are_normalised_and_ordered(mock_post):
    mock_post.return_value = _response(200, [[3.0, 4.0], [0.0, 2.0]])

    out = embeddings.embed_texts(["a", "b"], api_key="k")

    np.testing.assert_allclose(out, [[0.6, 0.8], [0.0, 1.0]], rtol=1e-6)
    body = mock_post.call_args.kwargs["json"]
    assert body["model"] == embeddings.EMBEDDING_MODEL
    assert body["dimensions"] == embeddings.EMBEDDING_DIMENSIONS


@patch("src.embeddings.requests.post")
def test_batches_large_inputs(mock_post, monkeypatch):
    monkeypatch.setattr(embeddings, "_BATCH_SIZE", 2)
    mock_post.side_effect = lambda *a, **kw: _response(
        200, [[1.0, 0.0]] * len(kw["json"]["input"])
    )

    out = embeddings.embed_texts(["a", "b", "c"], api_key="k")

    assert out.shape == (3, 2)
    assert [len(c.kwargs["json"]["input"]) for c in mock_post.call_args_list] == [2, 1]


@patch("src.embeddings.time.sleep")
@patch("src.embeddings.requests.post")
def test_retries_rate_limits(mock_post, mock_sleep):
    mock_post.side_effect = [_response(429), _response(200, [[1.0, 0.0]])]

    out = embeddings.embed_texts(["a"], api_key="k")

    assert out.shape == (1, 2)
    assert mock_sleep.call_count == 1


@patch("src.embeddings.requests.post")
def test_client_errors_raise(mock_post):
    mock_post.return_value = _response(400)
    with pytest.raises(Exception, match="HTTP 400"):
        embeddings.embed_texts(["a"], api_key="k")


def test_bytes_round_trip():
    vec = np.array([0.25, -1.5, 3.0], dtype=np.float32)
    np.testing.assert_array_equal(embeddings.from_bytes(embeddings.to_bytes(vec)), vec)
