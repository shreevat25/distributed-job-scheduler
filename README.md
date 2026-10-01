# Distributed Job Scheduler

A production-inspired, highly concurrent distributed job scheduling platform built entirely on PostgreSQL without the need for external queue brokers like Redis, Kafka, or RabbitMQ.

## Features
- **Strict Concurrency Control**: Worker-level and Queue-level concurrency limits enforced via transactional locking.
- **Atomic Claiming**: Uses `SELECT FOR UPDATE SKIP LOCKED` to allow multiple concurrent workers to securely claim jobs. This prevents multiple concurrent claimers from successfully claiming the same available job row during the claim transaction, while avoiding unnecessary blocking on already locked candidate rows.
- **Robust Failure Handling**: Dead-Letter Queue (DLQ), configurable retry policies (linear, fixed, exponential with jitter), and automated crash recovery. Workers emit heartbeats to report process liveness. Separately, active job executions renew their own leases. If a worker crashes, heartbeats stop, job leases eventually expire, and the Reaper recovers eligible interrupted work.
- **Graceful Shutdown**: Draining state for workers that safely completes existing tasks before exiting.
- **Cron and Recurring Jobs**: Transactional materialization of scheduled tasks with idempotency guarantees to prevent double-firing across multiple scheduler replicas.
- **Glassmorphism React Dashboard**: A beautiful, modern frontend for observing system health.

## Technology Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (Async), Pydantic v2
- **Database**: PostgreSQL 16 (via `asyncpg` and `alembic`)
- **Frontend**: React, TypeScript, Vite, Vanilla CSS
- **Infrastructure**: Docker, Docker Compose

## Quickstart

```bash
# Start the full stack
docker-compose up --build
```
This launches:
- PostgreSQL 16
- Dedicated Alembic migration service
- FastAPI Backend (Port 8000)
- React Frontend Dashboard (Port 8080)
- Worker 1 & Worker 2
- Background Scheduler & Crash Recovery Reaper

Access the dashboard at `http://localhost:8080`.

## Development

Common tasks are wrapped in the root `Makefile` (`make help` lists all of them):

```bash
make install        # create backend/.venv and install backend + dev deps
make test-db        # start a disposable PostgreSQL 16 on :54321 for tests
make test           # run the full test suite
make migrate        # apply Alembic migrations (uses DATABASE_URL)
make migrate-check  # fail if models have drifted from migrations
make run-api        # or run-worker / run-scheduler / run-reaper
make up             # docker compose up --build -d
```

## Testing
- Verified by **112 passing automated tests** against a real PostgreSQL 16 instance, including a migration round-trip and model-drift check.

## Documentation
- [Architecture](docs/ARCHITECTURE.md) (includes the backend code layout)
- [Database Design](docs/DATABASE_DESIGN.md)
- [Design Decisions](docs/DESIGN_DECISIONS.md)


