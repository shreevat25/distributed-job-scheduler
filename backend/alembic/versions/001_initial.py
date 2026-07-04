"""Initial migration — create all Phase 1 tables.

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables, indexes, constraints for Phase 1."""

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_projects_owner_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("owner_id", "name", name="uq_projects_owner_id_name"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    # --- retry_policies ---
    # Create the enum type first
    retry_strategy_enum = postgresql.ENUM("fixed", "linear", "exponential", name="retry_strategy_enum", create_type=False)
    retry_strategy_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "retry_policies",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("strategy", retry_strategy_enum, nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("base_delay_seconds", sa.Integer(), nullable=False),
        sa.Column("max_delay_seconds", sa.Integer(), nullable=True),
        sa.Column("jitter", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("jitter_factor", sa.Float(), server_default=sa.text("0.1"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_retry_policies_project_id_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_retry_policies"),
        sa.UniqueConstraint("project_id", "name", name="uq_retry_policies_project_id_name"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_retry_policies_max_attempts_gte_1"),
        sa.CheckConstraint("base_delay_seconds >= 0", name="ck_retry_policies_base_delay_seconds_gte_0"),
        sa.CheckConstraint("jitter_factor >= 0", name="ck_retry_policies_jitter_factor_gte_0"),
        sa.CheckConstraint("jitter_factor <= 1", name="ck_retry_policies_jitter_factor_lte_1"),
    )

    # --- queues ---
    op.create_table(
        "queues",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retry_policy_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False),
        sa.Column("is_paused", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_queues_project_id_projects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retry_policy_id"], ["retry_policies.id"], name="fk_queues_retry_policy_id_retry_policies", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_queues"),
        sa.UniqueConstraint("project_id", "name", name="uq_queues_project_id_name"),
        sa.CheckConstraint("concurrency_limit > 0", name="ck_queues_concurrency_limit_gt_0"),
    )
    op.create_index("ix_queues_project_id", "queues", ["project_id"])
    op.create_index("ix_queues_project_id_is_paused", "queues", ["project_id", "is_paused"])

    # --- workers ---
    worker_status_enum = postgresql.ENUM("starting", "online", "draining", "offline", "dead", name="worker_status_enum", create_type=False)
    worker_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "workers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("process_id", sa.Integer(), nullable=True),
        sa.Column("status", worker_status_enum, server_default=sa.text("'starting'"), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("stopped_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_workers"),
    )
    op.create_index("ix_workers_status", "workers", ["status"])
    op.create_index("ix_workers_last_seen_at", "workers", ["last_seen_at"])

    # --- job_batches ---
    op.create_table(
        "job_batches",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("queue_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("total_jobs", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["queue_id"], ["queues.id"], name="fk_job_batches_queue_id_queues", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_job_batches_created_by_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_job_batches"),
    )
    op.create_index("ix_job_batches_queue_id_created_at", "job_batches", ["queue_id", "created_at"])

    # --- jobs ---
    job_status_enum = postgresql.ENUM(
        "queued", "scheduled", "claimed", "running", "completed",
        "retry_wait", "failed", "dead_lettered", "cancelled",
        name="job_status_enum", create_type=False,
    )
    job_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("queue_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_schedule_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("status", job_status_enum, server_default=sa.text("'queued'"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_token", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("claimed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("result", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("last_error", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["queue_id"], ["queues.id"], name="fk_jobs_queue_id_queues", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["job_batches.id"], name="fk_jobs_batch_id_job_batches", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name="fk_jobs_worker_id_workers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    # Composite indexes
    op.create_index(
        "ix_jobs_claim_query",
        "jobs",
        ["queue_id", "status", "available_at", sa.text("priority DESC"), "created_at"],
    )
    op.create_index("ix_jobs_worker_id_status", "jobs", ["worker_id", "status"])
    op.create_index("ix_jobs_status_lease_expires_at", "jobs", ["status", "lease_expires_at"])
    op.create_index("ix_jobs_queue_id_created_at", "jobs", ["queue_id", "created_at"])
    op.create_index("ix_jobs_batch_id", "jobs", ["batch_id"])

    # CRITICAL: Partial unique index for idempotency
    op.create_index(
        "ix_jobs_queue_id_idempotency_key",
        "jobs",
        ["queue_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # --- job_executions ---
    op.create_table(
        "job_executions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_token", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_type", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("result", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_job_executions_job_id_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name="fk_job_executions_worker_id_workers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_job_executions"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_executions_job_id_attempt_number"),
    )
    op.create_index("ix_job_executions_job_id_attempt_number", "job_executions", ["job_id", "attempt_number"])
    op.create_index("ix_job_executions_worker_id_started_at", "job_executions", ["worker_id", "started_at"])

    # --- job_logs ---
    log_level_enum = postgresql.ENUM("debug", "info", "warning", "error", name="log_level_enum", create_type=False)
    log_level_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "job_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", log_level_enum, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_job_logs_job_id_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["job_executions.id"], name="fk_job_logs_execution_id_job_executions", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_job_logs"),
    )
    op.create_index("ix_job_logs_job_id_created_at", "job_logs", ["job_id", "created_at"])
    op.create_index("ix_job_logs_execution_id_created_at", "job_logs", ["execution_id", "created_at"])

    # --- scheduled_jobs ---
    schedule_type_enum = postgresql.ENUM("one_time", "cron", name="schedule_type_enum", create_type=False)
    schedule_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("queue_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("job_type", sa.String(255), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("schedule_type", schedule_type_enum, nullable=False),
        sa.Column("run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cron_expression", sa.String(100), nullable=True),
        sa.Column("timezone", sa.String(50), server_default=sa.text("'UTC'"), nullable=False),
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["queue_id"], ["queues.id"], name="fk_scheduled_jobs_queue_id_queues", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_scheduled_jobs_created_by_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_jobs"),
        sa.CheckConstraint(
            "(schedule_type = 'one_time' AND run_at IS NOT NULL) OR "
            "(schedule_type = 'cron' AND cron_expression IS NOT NULL)",
            name="ck_scheduled_jobs_schedule_type_fields_valid",
        ),
    )
    op.create_index("ix_scheduled_jobs_is_active_next_run_at", "scheduled_jobs", ["is_active", "next_run_at"])
    op.create_index("ix_scheduled_jobs_queue_id", "scheduled_jobs", ["queue_id"])

    # --- worker_heartbeats ---
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("worker_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_job_count", sa.Integer(), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name="fk_worker_heartbeats_worker_id_workers", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_worker_heartbeats"),
    )
    op.create_index("ix_worker_heartbeats_worker_id_created_at", "worker_heartbeats", ["worker_id", "created_at"])

    # --- dlq_entries ---
    op.create_table(
        "dlq_entries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("queue_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("final_execution_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("error_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("dead_lettered_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("retried_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retried_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_dlq_entries_job_id_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["queue_id"], ["queues.id"], name="fk_dlq_entries_queue_id_queues", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["final_execution_id"], ["job_executions.id"], name="fk_dlq_entries_final_execution_id_job_executions", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["retried_by"], ["users.id"], name="fk_dlq_entries_retried_by_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_dlq_entries"),
        sa.UniqueConstraint("job_id", name="uq_dlq_entries_job_id"),
    )
    op.create_index("ix_dlq_entries_queue_id_dead_lettered_at", "dlq_entries", ["queue_id", "dead_lettered_at"])
    op.create_index("ix_dlq_entries_dead_lettered_at", "dlq_entries", ["dead_lettered_at"])


def downgrade() -> None:
    """Drop all Phase 1 tables in reverse dependency order."""
    op.drop_table("dlq_entries")
    op.drop_table("worker_heartbeats")
    op.drop_table("scheduled_jobs")
    op.drop_table("job_logs")
    op.drop_table("job_executions")
    op.drop_table("jobs")
    op.drop_table("job_batches")
    op.drop_table("workers")
    op.drop_table("queues")
    op.drop_table("retry_policies")
    op.drop_table("projects")
    op.drop_table("users")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS schedule_type_enum")
    op.execute("DROP TYPE IF EXISTS log_level_enum")
    op.execute("DROP TYPE IF EXISTS job_status_enum")
    op.execute("DROP TYPE IF EXISTS worker_status_enum")
    op.execute("DROP TYPE IF EXISTS retry_strategy_enum")
