"""Structured logging configuration for Job Hunter Agent.

Provides JSON-formatted logs suitable for log aggregation and analysis.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs logs in JSON format."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


def configure_logging(
    level: int = logging.INFO, json_format: bool = True, debug: bool = False
) -> None:
    """Configure logging for the application.

    Args:
        level: Log level (default INFO)
        json_format: If True, use JSON formatter; otherwise use text format
        debug: If True, set level to DEBUG
    """
    if debug:
        level = logging.DEBUG

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    # Set formatter
    if json_format:
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)


def get_logger(name: str) -> logging.LoggerAdapter:
    """Get a logger instance with extra fields support.

    Args:
        name: Logger name (typically __name__)

    Returns:
        LoggerAdapter for adding extra fields to logs
    """
    base_logger = logging.getLogger(name)
    return LoggerWithExtra(base_logger)


class LoggerWithExtra(logging.LoggerAdapter):
    """LoggerAdapter that supports adding extra fields to logs."""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:  # type: ignore
        """Process log message and add extra fields."""
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        # Extract extra_fields if provided
        if "extra_fields" in kwargs:
            kwargs["extra"]["extra_fields"] = kwargs.pop("extra_fields")

        return msg, kwargs


__all__ = ["configure_logging", "get_logger", "JSONFormatter"]
