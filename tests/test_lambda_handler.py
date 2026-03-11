"""Tests for AWS Lambda handler."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _set_env(tmp_path, monkeypatch):
    """Set Lambda environment variables for all tests."""
    db_path = str(tmp_path / "jobs.db")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:eu-west-1:123:test-topic")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MIN_MATCH_SCORE_NOTIFY", "70")


@pytest.fixture
def mock_sns_client():
    """Mock SNS client via the lazy getter."""
    mock = MagicMock()
    with patch("src.lambda_handler._get_sns", return_value=mock):
        yield mock


@pytest.fixture
def mock_scrapers():
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.return_value = []
    mock_instance.last_raw_count = 0
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP",
        {"greenhouse": mock_scraper_cls, "lever": mock_scraper_cls},
    ):
        with patch(
            "src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse", "lever"]
        ):
            yield mock_scraper_cls, mock_instance


def test_handler_returns_summary(mock_sns_client, mock_scrapers):
    """Test handler returns a well-formed summary dict."""
    from src.lambda_handler import lambda_handler

    result = lambda_handler({}, None)

    assert result["jobs_scraped"] == 0
    assert result["matches_computed"] == 0
    assert "scrape_errors" in result
    assert "high_score_matches" in result


def test_handler_scraper_failure_recorded(mock_sns_client):
    """Test that a failing scraper is listed in scrape_errors."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.side_effect = Exception("Scraper broke")
    mock_instance.last_raw_count = 0
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}
    ):
        with patch("src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse"]):
            from src.lambda_handler import lambda_handler

            result = lambda_handler({}, None)

            assert "greenhouse" in result["scrape_errors"]


def test_handler_zero_results_scrapers_reported(mock_sns_client):
    """Test that scrapers returning 0 raw results are flagged."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.return_value = []
    mock_instance.last_raw_count = 0
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}
    ):
        with patch("src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse"]):
            from src.lambda_handler import lambda_handler

            result = lambda_handler({}, None)

            assert "greenhouse" in result["zero_result_scrapers"]


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
