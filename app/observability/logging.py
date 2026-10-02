"""Structured JSON logging configuration using structlog and python-json-logger."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from pythonjsonlogger import json as jsonlogger

from app.observability.pii_redaction import redact_pii_dict


class PIIScrubbingProcessor:
    """Structlog processor that redacts sensitive PII from log event dictionaries."""

    def __call__(self, logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return redact_pii_dict(event_dict)


def configure_structured_logging(log_level: str = "INFO") -> structlog.BoundLogger:
    """Configures structured JSON logging outputting machine-parseable JSON lines to stdout."""
    # Standard library root logger setup
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Structlog pipeline
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            PIIScrubbingProcessor(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger("video_editor_assistant")


# Initialize default logger
app_logger = configure_structured_logging()
