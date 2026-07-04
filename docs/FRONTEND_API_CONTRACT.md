# Frontend API Contract

This table documents every API call the frontend makes and confirms it against the actual FastAPI backend route.

> Prefix: All routes are under `/api/v1` (the Vite proxy forwards `/api` → `http://backend:8000`).

## Authentication

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| Login | POST | `/auth/login` | `POST /api/v1/auth/login` | `{access_token, token_type}` | ✅ Fixed |
| Register | POST | `/auth/register` | `POST /api/v1/auth/register` | `{id, email, ...}` | ✅ |

## Projects

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| List projects | GET | `/projects` | `GET /api/v1/projects` | `[{id, name, ...}]` | ✅ |

## Queues

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| List queues | GET | `/projects/{id}/queues` | `GET /api/v1/projects/{project_id}/queues` | `[{id, name, is_paused, ...}]` | ✅ Fixed |
| Create queue | POST | `/projects/{id}/queues` | `POST /api/v1/projects/{project_id}/queues` | `{id, name, ...}` | ✅ Fixed |
| Pause queue | POST | `/queues/{id}/pause` | `POST /api/v1/queues/{queue_id}/pause` | `{id, is_paused: true, ...}` | ✅ |
| Resume queue | POST | `/queues/{id}/resume` | `POST /api/v1/queues/{queue_id}/resume` | `{id, is_paused: false, ...}` | ✅ |

## Jobs

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| List jobs | GET | `/jobs?limit=50&status=...` | `GET /api/v1/jobs` | `{items: [...], page, limit, total}` | ✅ Fixed (`.items`) |

## Workers

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| List workers | GET | `/workers` | `GET /api/v1/workers` | `[{id, name, status, last_seen_at, ...}]` | ✅ |

## DLQ

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| List DLQ | GET | `/dlq` | `GET /api/v1/dlq` | `[{id, job_id, reason, dead_lettered_at, attempts, ...}]` | ✅ Fixed |
| Retry DLQ entry | POST | `/dlq/{id}/retry` | `POST /api/v1/dlq/{id}/retry` | `{id, retried_at, ...}` | ✅ |

## Schedules

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| List schedules | GET | `/schedules` | `GET /api/v1/schedules` | `[{id, name, is_active, next_run_at, ...}]` | ✅ |
| Create schedule | POST | `/schedules` | `POST /api/v1/schedules` | `{id, name, ...}` | ✅ |
| Pause schedule | POST | `/schedules/{id}/pause` | `POST /api/v1/schedules/{schedule_id}/pause` | `{id, is_active: false, ...}` | ✅ |
| Resume schedule | POST | `/schedules/{id}/resume` | `POST /api/v1/schedules/{schedule_id}/resume` | `{id, is_active: true, ...}` | ✅ |
| Delete schedule | DELETE | `/schedules/{id}` | `DELETE /api/v1/schedules/{schedule_id}` | `204 No Content` | ✅ |

## Health

| Frontend Call | Method | Path | Backend Route | Response Shape | Status |
|---|---|---|---|---|---|
| Health check | GET | `/health` | `GET /health` (root, not versioned) | `{status: "ok", version}` | ✅ Fixed (uses axios directly) |

## Known Remaining Limitations

- **Project selector**: Queues and Schedules only show queues/schedules from the first project returned by `/projects`. A project switcher UI is needed for multi-project users.
- **Job total count**: The dashboard shows "running count from last 50 jobs polled" — not a true system-wide running count. A `GET /stats` endpoint would be needed for accurate totals.
- **Workers pagination**: Workers list is unbounded; if there are hundreds of workers, the list is not paginated.
