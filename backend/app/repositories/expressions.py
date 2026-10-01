"""Database-clock SQL expressions shared by repositories and services.

All lease, schedule and audit timestamps are evaluated against PostgreSQL's
NOW() so that every worker, scheduler and reaper agrees on a single clock.
"""

from sqlalchemy import TextClause, text


def db_now() -> TextClause:
    """The authoritative database timestamp."""
    return text("NOW()")


def db_now_plus_seconds(seconds: float) -> TextClause:
    """NOW() offset by a bound number of seconds."""
    return text("NOW() + (:seconds * INTERVAL '1 second')").bindparams(seconds=seconds)


def db_now_minus_seconds(seconds: float) -> TextClause:
    """NOW() minus a bound number of seconds."""
    return text("NOW() - (:seconds * INTERVAL '1 second')").bindparams(seconds=seconds)


def execution_elapsed_ms() -> TextClause:
    """Milliseconds elapsed since the owning job_executions row started."""
    return text("CAST(EXTRACT(EPOCH FROM (NOW() - job_executions.started_at)) * 1000 AS BIGINT)")
