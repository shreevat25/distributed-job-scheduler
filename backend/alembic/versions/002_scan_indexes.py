"""Reconcile workers schema with models and add background-scan indexes.

- workers: add the table comment declared on the model (was missing from 001).
- workers: replace the single-column status / last_seen_at indexes with one
  composite (status, last_seen_at) index matching the reaper's stale-worker
  scan (status = 'online' AND last_seen_at < NOW() - threshold).
- jobs: add a partial index on available_at for the promotion scan
  (status IN ('scheduled', 'retry_wait') AND available_at <= NOW()), which the
  queue-leading claim index cannot serve.

Revision ID: 002_scan_indexes
Revises: 001_initial
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_scan_indexes"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WORKERS_COMMENT = "Registered worker processes for job execution"
PROMOTABLE_PREDICATE = "status IN ('scheduled', 'retry_wait')"


def upgrade() -> None:
    op.create_table_comment("workers", WORKERS_COMMENT)

    op.create_index("ix_workers_status_last_seen_at", "workers", ["status", "last_seen_at"])
    op.drop_index("ix_workers_status", table_name="workers")
    op.drop_index("ix_workers_last_seen_at", table_name="workers")

    op.create_index(
        "ix_jobs_due_for_promotion",
        "jobs",
        ["available_at"],
        postgresql_where=sa.text(PROMOTABLE_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_due_for_promotion", table_name="jobs")

    op.create_index("ix_workers_last_seen_at", "workers", ["last_seen_at"])
    op.create_index("ix_workers_status", "workers", ["status"])
    op.drop_index("ix_workers_status_last_seen_at", table_name="workers")

    op.drop_table_comment("workers", existing_comment=WORKERS_COMMENT)
