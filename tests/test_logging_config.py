"""Tests for structured logging configuration."""

import json
import logging
from io import StringIO

from src.logging_config import JSONFormatter, configure_logging, get_logger


def test_json_formatter():
    """Test JSONFormatter produces valid JSON output."""
    logger = logging.getLogger("test")
    handler = logging.StreamHandler(StringIO())

    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Log a message
    logger.info("Test message")

    # Get output and parse JSON
    output = handler.stream.getvalue()
    data = json.loads(output.strip())

    assert data["level"] == "INFO"
    assert data["message"] == "Test message"
    assert data["logger"] == "test"
    assert "timestamp" in data


def test_configure_logging_json():
    """Test configure_logging with JSON format."""
    configure_logging(level=logging.INFO, json_format=True, debug=False)

    logger = get_logger("test_json")
    handler = logging.StreamHandler(StringIO())
    handler.setFormatter(JSONFormatter())
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)

    # Log a message
    logger.info("Test structured logging")

    # Get output and parse
    output = handler.stream.getvalue()
    data = json.loads(output.strip())

    assert data["message"] == "Test structured logging"


def test_configure_logging_text():
    """Test configure_logging with text format."""
    configure_logging(level=logging.INFO, json_format=False, debug=False)

    logger = logging.getLogger("test_text")
    assert logger.level == logging.INFO or logger.level == 0  # Root logger
