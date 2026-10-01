"""ORM models.

Importing this package registers every model on ``Base.metadata``. That is
required before mappers configure (string-based relationships) and for Alembic
autogenerate. Importing any ``app.models.<module>`` runs this first.

The registry lives here rather than in ``app.db.base`` because every model
imports ``Base`` from there; importing models back from ``app.db.base`` made
the import order matter and broke the standalone worker, scheduler and reaper
entry points with a circular import.
"""

from app.models.user import User
from app.models.project import Project
from app.models.retry_policy import RetryPolicy
from app.models.queue import Queue
from app.models.job_batch import JobBatch
from app.models.worker import Worker
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.scheduled_job import ScheduledJob
from app.models.worker_heartbeat import WorkerHeartbeat
from app.models.dlq_entry import DLQEntry

__all__ = [
    "User",
    "Project",
    "RetryPolicy",
    "Queue",
    "JobBatch",
    "Worker",
    "Job",
    "JobExecution",
    "JobLog",
    "ScheduledJob",
    "WorkerHeartbeat",
    "DLQEntry",
]
