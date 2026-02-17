"""Tests for AWS Lambda handler."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


@pytest.fixture(autouse=True)
def _set_env(tmp_path, monkeypatch):
    """Set Lambda environment variables for all tests."""
    db_path = str(tmp_path / "jobs.db")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_DB_KEY", "jobhunter/jobs.db")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:eu-west-1:123:test-topic")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MIN_MATCH_SCORE_NOTIFY", "70")


@pytest.fixture
def mock_s3_client():
    """Mock S3 client via the lazy getter."""
    mock = MagicMock()
    with patch("src.lambda_handler._get_s3", return_value=mock):
        yield mock


@pytest.fixture
def mock_sns_client():
    """Mock SNS client via the lazy getter."""
    mock = MagicMock()
    with patch("src.lambda_handler._get_sns", return_value=mock):
        yield mock


@pytest.fixture
def mock_s3_no_db(mock_s3_client):
    """S3 client that returns 404 (no existing DB)."""
    mock_s3_client.download_file.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject"
    )
    return mock_s3_client


@pytest.fixture
def mock_scrapers():
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.return_value = []
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP",
        {"greenhouse": mock_scraper_cls, "lever": mock_scraper_cls},
    ):
        with patch(
            "src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse", "lever"]
        ):
            yield mock_scraper_cls, mock_instance


def test_handler_first_run(mock_s3_no_db, mock_sns_client, mock_scrapers):
    """Test handler with no existing DB in S3 (first run)."""
    from src.lambda_handler import lambda_handler

    result = lambda_handler({}, None)

    assert result["jobs_scraped"] == 0
    assert result["matches_computed"] == 0
    # DB should still be uploaded even with no new jobs
    mock_s3_no_db.upload_file.assert_called_once()


def test_handler_existing_db(mock_s3_client, mock_sns_client, mock_scrapers):
    """Test handler downloads existing DB from S3."""
    mock_s3_client.download_file.return_value = None  # Success

    from src.lambda_handler import lambda_handler

    result = lambda_handler({}, None)

    mock_s3_client.download_file.assert_called_once()
    mock_s3_client.upload_file.assert_called_once()
    assert "jobs_scraped" in result


def test_handler_scraper_failure_still_uploads(mock_s3_no_db, mock_sns_client):
    """Test that DB is uploaded even if a scraper fails."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.side_effect = Exception("Scraper broke")
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}
    ):
        with patch("src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse"]):
            from src.lambda_handler import lambda_handler

            result = lambda_handler({}, None)

            mock_s3_no_db.upload_file.assert_called_once()
            assert "greenhouse" in result["scrape_errors"]


def test_notify_sends_sns(mock_sns_client):
    """Test SNS notification is sent."""
    from src.lambda_handler import _notify

    _notify("arn:aws:sns:eu-west-1:123:topic", "Test Subject", "Test message")

    mock_sns_client.publish.assert_called_once_with(
        TopicArn="arn:aws:sns:eu-west-1:123:topic",
        Subject="Test Subject",
        Message="Test message",
    )


def test_notify_skipped_without_topic_arn(mock_sns_client):
    """Test notification is skipped when topic ARN is empty."""
    from src.lambda_handler import _notify

    _notify("", "Subject", "Message")
    mock_sns_client.publish.assert_not_called()


def test_download_db_returns_false_on_404(mock_s3_no_db):
    """Test _download_db returns False when DB doesn't exist in S3."""
    from src.lambda_handler import _download_db

    result = _download_db("test-bucket", "jobhunter/jobs.db")
    assert result is False


def test_download_db_returns_true_on_success(mock_s3_client):
    """Test _download_db returns True when DB exists in S3."""
    mock_s3_client.download_file.return_value = None

    from src.lambda_handler import _download_db

    result = _download_db("test-bucket", "jobhunter/jobs.db")
    assert result is True
