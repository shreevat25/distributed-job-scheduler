"""Structured logging configuration with request context support."""

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

# Context variable for per-request ID propagation
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
current_user_id_ctx: ContextVar[str] = ContextVar("current_user_id", default="")

# Fields that must never appear in logs
_SENSITIVE_FIELDS = frozenset({
    "password",
    "password_hash",
    "token",
    "jwt",
    "secret",
    "authorization",
})


def _filter_sensitive(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict,
) -> dict:
    """Remove sensitive fields from log events."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def _add_request_context(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict,
) -> dict:
    """Inject request_id and user_id into every log event."""
    rid = request_id_ctx.get("")
    if rid:
        event_dict["request_id"] = rid
    uid = current_user_id_ctx.get("")
    if uid:
        event_dict["user_id"] = uid
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured JSON logging for the application."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            _add_request_context,
            _filter_sensitive,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def generate_request_id() -> str:
    """Generate a new UUID request ID."""
    return str(uuid.uuid4())


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger."""
    return structlog.get_logger(name)
