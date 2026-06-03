"""Structured logging configuration with structlog."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Configure structlog and the standard library logging.

    Args:
        level: minimum log level (DEBUG, INFO, WARNING, ...).
        json_logs: if True emit JSON (production); if False, colored console output.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route standard library logging (uvicorn, sqlalchemy, discord) through structlog.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    for noisy in ("uvicorn.access", "discord", "apscheduler"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.INFO))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structured logger, optionally bound to a name."""
    return structlog.get_logger(name)
