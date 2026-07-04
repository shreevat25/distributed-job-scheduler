"""Domain exceptions with structured error codes for API responses."""

from typing import Any


class AppError(Exception):
    """Base application error with structured error metadata."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str = "") -> None:
        detail_msg = f"{resource} not found"
        if identifier:
            detail_msg = f"{resource} '{identifier}' not found"
        super().__init__(
            code="NOT_FOUND",
            message=detail_msg,
            status_code=404,
            details={"resource": resource},
        )


class ForbiddenError(AppError):
    """Access denied to the requested resource."""

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403,
        )


class ConflictError(AppError):
    """Resource conflict (duplicate, already exists)."""

    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409,
        )


class InvalidTransitionError(AppError):
    """Invalid state transition for a resource."""

    def __init__(self, resource: str, from_status: str, to_status: str) -> None:
        super().__init__(
            code="INVALID_TRANSITION",
            message=f"Cannot transition {resource} from '{from_status}' to '{to_status}'",
            status_code=422,
            details={"from_status": from_status, "to_status": to_status},
        )


class QueuePausedError(AppError):
    """Operation rejected because the queue is paused."""

    def __init__(self, queue_id: str = "") -> None:
        msg = "Queue is paused"
        if queue_id:
            msg = f"Queue '{queue_id}' is paused"
        super().__init__(
            code="QUEUE_PAUSED",
            message=msg,
            status_code=409,
            details={"queue_id": queue_id} if queue_id else {},
        )


class IdempotencyConflictError(AppError):
    """Idempotency key reuse with different request payload."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            code="IDEMPOTENCY_CONFLICT",
            message="Idempotency key already used with different request parameters",
            status_code=409,
            details={"idempotency_key": idempotency_key},
        )


class ValidationError(AppError):
    """Custom validation error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details or {},
        )


class AuthenticationError(AppError):
    """Authentication failure — generic message to avoid leaking info."""

    def __init__(self) -> None:
        super().__init__(
            code="INVALID_CREDENTIALS",
            message="Invalid credentials",
            status_code=401,
        )


class OwnershipLostError(AppError):
    """Worker has lost ownership of the claimed job or lease."""

    def __init__(self, message: str = "Worker lost ownership of job") -> None:
        super().__init__(
            code="OWNERSHIP_LOST",
            message=message,
            status_code=409,
        )


class LeaseExpiredError(AppError):
    """Job lease has expired."""

    def __init__(self, message: str = "Job lease expired") -> None:
        super().__init__(
            code="LEASE_EXPIRED",
            message=message,
            status_code=409,
        )


class ExhaustedAttemptsError(AppError):
    """Job has exhausted all execution attempts."""

    def __init__(self, message: str = "Job attempts exhausted") -> None:
        super().__init__(
            code="EXHAUSTED_ATTEMPTS",
            message=message,
            status_code=422,
        )


class WorkerLostError(AppError):
    """Worker running this execution was marked dead or lost."""

    def __init__(self, message: str = "Worker running execution was lost or marked dead") -> None:
        super().__init__(
            code="WORKER_LOST",
            message=message,
            status_code=500,
        )

