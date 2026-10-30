"""Errors raised by the SDK, carrying the server's error envelope."""

from __future__ import annotations

from typing import Any


class RAGKitError(Exception):
    """A request failed. `code` and `request_id` come from the server's error envelope."""

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        code: str = "error",
        request_id: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.request_id = request_id
        self.details = details

    def __str__(self) -> str:
        suffix = f" (request {self.request_id})" if self.request_id else ""
        return f"{self.status} {self.code}: {self.message}{suffix}"


class AuthenticationError(RAGKitError):
    """401: the API key is missing, wrong, revoked or expired."""


class PermissionDeniedError(RAGKitError):
    """403: the key's role does not allow this request."""


class NotFoundError(RAGKitError):
    """404: the project, collection, dataset or run does not exist for this key."""


class ValidationError(RAGKitError):
    """422: the request was understood but is not valid; `details` says where."""


class RateLimitError(RAGKitError):
    """429: retried automatically up to `max_retries`, then raised."""


class TimeoutError(RAGKitError):
    """A wait helper gave up before the server finished."""


def from_response(status: int, body: Any) -> RAGKitError:
    error = body.get("error") if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {}
    kind = {
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        422: ValidationError,
        429: RateLimitError,
    }.get(status, RAGKitError)
    return kind(
        str(error.get("message") or f"The request failed with HTTP {status}."),
        status=status,
        code=str(error.get("code") or "error"),
        request_id=error.get("request_id"),
        details=error.get("details"),
    )
