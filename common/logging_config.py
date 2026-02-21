"""
FORESIGHT — Structured logging configuration.

Configures Python's logging module to emit JSON-formatted logs in production
and human-readable text in development. Import configure_logging() once at
application entry point (main.py, DAG file, Spark job).
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict

try:
    import structlog  # optional enhanced structured logging
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON for log aggregation systems
    (Datadog, CloudWatch, ELK).
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialise log record to JSON string."""
        import json
        import traceback

        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include extra fields injected via logger.info("msg", extra={...})
        extra_keys = set(record.__dict__.keys()) - {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
        }
        for key in extra_keys:
            log_obj[key] = getattr(record, key)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    service_name: str = "foresight",
) -> logging.Logger:
    """
    Configure root logger and return the named logger for this service.

    Args:
        level:        Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt:          "json" for structured logs, "text" for human-readable.
        service_name: Service identifier included in every log record.

    Returns:
        Configured Logger instance.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any existing handlers (e.g. added by Airflow / Spark)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if fmt.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root.addHandler(handler)

    logger = logging.getLogger(service_name)
    logger.info(
        "Logging configured",
        extra={"service": service_name, "log_level": level, "log_format": fmt},
    )
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger. Call once per module at module level.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)
