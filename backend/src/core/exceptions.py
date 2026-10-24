from datetime import UTC, datetime
from typing import Any


class DomainError(Exception):
    def __init__(
        self,
        message: str,
        error_code: str = "DOMAIN_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_problem_details(self, server_time: datetime | None = None) -> dict[str, Any]:
        timestamp = (server_time or datetime.now(UTC)).isoformat()
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "server_time": timestamp,
        }


class NotFoundError(DomainError):
    def __init__(
        self,
        message: str = "Resource not found",
        error_code: str = "NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=404, details=details)


class UnauthorizedError(DomainError):
    def __init__(
        self,
        message: str = "Authentication required",
        error_code: str = "UNAUTHORIZED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=401, details=details)


class ForbiddenError(DomainError):
    def __init__(
        self,
        message: str = "Access forbidden",
        error_code: str = "FORBIDDEN",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=403, details=details)


class ConflictError(DomainError):
    def __init__(
        self,
        message: str = "Resource state conflict",
        error_code: str = "CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=409, details=details)
