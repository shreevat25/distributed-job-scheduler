"""Application enumerations for type-safe status and strategy fields."""

import enum


class JobStatus(str, enum.Enum):
    """Job lifecycle states."""

    QUEUED = "queued"
    SCHEDULED = "scheduled"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


class RetryStrategy(str, enum.Enum):
    """Retry backoff strategies."""

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class ScheduleType(str, enum.Enum):
    """Scheduled job trigger types."""

    ONE_TIME = "one_time"
    CRON = "cron"


class WorkerStatus(str, enum.Enum):
    """Worker lifecycle states."""

    STARTING = "starting"
    ONLINE = "online"
    DRAINING = "draining"
    OFFLINE = "offline"
    DEAD = "dead"


class LogLevel(str, enum.Enum):
    """Structured log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
