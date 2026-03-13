"""Unit tests for s3_sync module."""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import src.s3_sync as s3_sync
from src.s3_sync import _local_db_path, is_configured, pull, push


@pytest.fixture(autouse=True)
def reset_s3_client():
    """Reset the module-level _s3_client singleton between tests."""
    s3_sync._s3_client = None
    yield
    s3_sync._s3_client = None


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


def test_is_configured_true(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    assert is_configured() is True


def test_is_configured_false(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    assert is_configured() is False


# ---------------------------------------------------------------------------
# _local_db_path
# ---------------------------------------------------------------------------


def test_local_db_path_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/jobs.db")
    assert _local_db_path() == "./data/jobs.db"


def test_local_db_path_absolute(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/test.db")
    assert _local_db_path() == "/tmp/test.db"


def test_local_db_path_non_sqlite_returns_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert _local_db_path() == "./data/jobs.db"


def test_local_db_path_missing_env_uses_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _local_db_path() == "./data/jobs.db"


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


def test_pull_not_configured_returns_false(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    assert pull() is False


def test_pull_success(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("S3_DB_KEY", "jobhunter/jobs.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/jobs.db")

    mock_s3 = MagicMock()
    s3_sync._s3_client = mock_s3

    result = pull()

    assert result is True
    mock_s3.download_file.assert_called_once_with(
        "my-bucket", "jobhunter/jobs.db", str(tmp_path) + "/jobs.db"
    )


def test_pull_default_key(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.delenv("S3_DB_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/jobs.db")

    mock_s3 = MagicMock()
    s3_sync._s3_client = mock_s3

    pull()

    mock_s3.download_file.assert_called_once()
    call_positional = mock_s3.download_file.call_args[0]
    assert call_positional[1] == "jobhunter/jobs.db"


def test_pull_404_returns_false(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/jobs.db")

    mock_s3 = MagicMock()
    error = ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject")
    mock_s3.download_file.side_effect = error
    s3_sync._s3_client = mock_s3

    result = pull()
    assert result is False


def test_pull_nosuchkey_returns_false(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/jobs.db")

    mock_s3 = MagicMock()
    error = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
    )
    mock_s3.download_file.side_effect = error
    s3_sync._s3_client = mock_s3

    result = pull()
    assert result is False


def test_pull_403_returns_false(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/jobs.db")

    mock_s3 = MagicMock()
    error = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "GetObject")
    mock_s3.download_file.side_effect = error
    s3_sync._s3_client = mock_s3

    result = pull()
    assert result is False


def test_pull_unexpected_error_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/jobs.db")

    mock_s3 = MagicMock()
    error = ClientError(
        {"Error": {"Code": "InternalError", "Message": "boom"}}, "GetObject"
    )
    mock_s3.download_file.side_effect = error
    s3_sync._s3_client = mock_s3

    with pytest.raises(ClientError):
        pull()


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------


def test_push_not_configured_returns_false(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    assert push() is False


def test_push_missing_local_file_returns_false(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/nonexistent.db")

    mock_s3 = MagicMock()
    s3_sync._s3_client = mock_s3

    result = push()
    assert result is False
    mock_s3.upload_file.assert_not_called()


def test_push_success(monkeypatch, tmp_path):
    db_file = tmp_path / "jobs.db"
    db_file.write_bytes(b"fake sqlite data")

    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("S3_DB_KEY", "jobhunter/jobs.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    mock_s3 = MagicMock()
    s3_sync._s3_client = mock_s3

    result = push()

    assert result is True
    mock_s3.upload_file.assert_called_once_with(
        str(db_file), "my-bucket", "jobhunter/jobs.db"
    )


def test_push_default_key(monkeypatch, tmp_path):
    db_file = tmp_path / "jobs.db"
    db_file.write_bytes(b"data")

    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.delenv("S3_DB_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    mock_s3 = MagicMock()
    s3_sync._s3_client = mock_s3

    push()

    mock_s3.upload_file.assert_called_once()
    # upload_file(local_path, bucket, key) — key is positional arg index 2
    call_positional = mock_s3.upload_file.call_args[0]
    assert call_positional[2] == "jobhunter/jobs.db"
