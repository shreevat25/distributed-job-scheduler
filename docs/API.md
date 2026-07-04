# API Documentation

The REST API exposes operations for managing the Distributed Job Scheduler. All endpoints return JSON.

## Authentication
JWT-based authentication is required for most endpoints.
- `POST /api/v1/auth/register`: Create a new user.
- `POST /api/v1/auth/login`: Exchange credentials for a JWT access token.

## Jobs
- `POST /api/v1/jobs`: Enqueue a single job.
- `GET /api/v1/jobs`: List jobs (paginated, supports status/queue filters).
- `GET /api/v1/jobs/{job_id}`: Retrieve job details.
- `GET /api/v1/jobs/{job_id}/executions`: Retrieve job execution history.

## Schedules
- `POST /api/v1/schedules`: Create a recurring (cron) or one-time schedule.
- `GET /api/v1/schedules`: List scheduled jobs.
- `POST /api/v1/schedules/{id}/pause`: Pause materialization.
- `POST /api/v1/schedules/{id}/resume`: Resume materialization.

## DLQ (Dead-Letter Queue)
- `GET /api/v1/dlq`: List jobs that have exceeded maximum retry attempts.
- `POST /api/v1/dlq/{id}/retry`: Transactionally move a DLQ entry back to `QUEUED`.

## Queues and Workers
- `GET /api/v1/queues`: List queues and concurrency settings.
- `GET /api/v1/workers`: List active, draining, or offline workers.
