"""
Problem details for the ITP API.

The ITP API specification requires errors in the ``application/problem+json``
media type (RFC 9457), with a ``type`` URI, a ``title``, the HTTP ``status``, a
``detail`` sentence, the ``instance`` path, an optional ``errors`` array for
schema violations, and a ``requestId``.

Every error raised inside the API is a ``ProblemDetail``. The exception handler
registered by ``APISpecification`` renders it, so the shape of an error response
is defined in exactly one place.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"
DEFAULT_PROBLEM_BASE_URI = "https://api.example.org/problems"

# Problem type slug -> (HTTP status, title).
PROBLEM_TYPES: dict[str, tuple[int, str]] = {
    "malformed-request": (400, "Malformed request"),
    "missing-token": (401, "Missing or invalid interaction token"),
    "invalid-token": (401, "Missing or invalid interaction token"),
    "forbidden-agent": (403, "Operation not permitted for this agent"),
    "model-not-found": (404, "Model not found"),
    "interaction-not-found": (404, "Interaction not found"),
    "agent-not-found": (404, "Agent not found"),
    "invalid-invitation": (404, "Invalid invitation code"),
    "results-not-found": (404, "Results not found"),
    "registration-conflict": (409, "Registration conflict"),
    "invitation-already-used": (409, "Invitation code already used"),
    "action-conflict": (409, "Action conflict"),
    "interaction-ended": (409, "Interaction has ended"),
    "invitation-expired": (410, "Invitation code expired"),
    "interaction-expired": (410, "Interaction expired"),
    "results-gone": (410, "Results no longer available"),
    "invalid-state-vector": (422, "Invalid state vector"),
    "invalid-configuration": (422, "Invalid interaction configuration"),
    "invitation-rate-limit": (429, "Too many invitation attempts"),
    "rate-limit": (429, "Too many requests"),
    "model-failure": (500, "Model failure"),
    "internal-error": (500, "Internal server error"),
}


def make_request_id() -> str:
    """
    Create an identifier for one request.

    Args:

    Returns:
        Request identifier.
    """

    return f"req-{uuid4().hex[:8]}"


class ProblemDetail(Exception):
    """
    API error rendered as an RFC 9457 problem document.

    Args:

    Returns:
    """

    def __init__(
        self,
        problem_type: str,
        detail: str,
        errors: list[dict[str, str]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize a problem detail.

        Args:
            problem_type: Problem type slug registered in PROBLEM_TYPES.
            detail: Sentence describing what went wrong.
            errors: Optional per-field validation errors.
            extra: Optional additional members of the problem document.

        Returns:
        """

        if problem_type not in PROBLEM_TYPES:
            raise ValueError(f"Unknown problem type: {problem_type}")

        status, title = PROBLEM_TYPES[problem_type]

        self.problem_type = problem_type
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors
        self.extra = extra or {}

        super().__init__(detail)

    def to_document(
        self,
        instance: str | None = None,
        request_id: str | None = None,
        base_uri: str = DEFAULT_PROBLEM_BASE_URI,
    ) -> dict[str, Any]:
        """
        Render the problem as a JSON document.

        Args:
            instance: Path of the request that produced the problem.
            request_id: Identifier of the request.
            base_uri: Base URI the problem type is resolved against.

        Returns:
            Problem document.
        """

        document: dict[str, Any] = {
            "type": f"{base_uri}/{self.problem_type}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }

        if instance is not None:
            document["instance"] = instance

        if self.errors:
            document["errors"] = self.errors

        document.update(self.extra)

        if request_id is not None:
            document["requestId"] = request_id

        return document


def make_problem_response(
    problem: ProblemDetail,
    request: Request | None = None,
    base_uri: str = DEFAULT_PROBLEM_BASE_URI,
) -> JSONResponse:
    """
    Render a problem detail as an HTTP response.

    Args:
        problem: Problem to render.
        request: Request that produced the problem.
        base_uri: Base URI the problem type is resolved against.

    Returns:
        Response carrying the problem document.
    """

    request_id = getattr(request.state, "request_id", None) if request else None
    instance = request.url.path if request else None

    document = problem.to_document(
        instance=instance,
        request_id=request_id or make_request_id(),
        base_uri=base_uri,
    )

    headers: dict[str, str] = {}

    if "retryAfterSeconds" in document:
        headers["Retry-After"] = str(document["retryAfterSeconds"])

    return JSONResponse(
        status_code=problem.status,
        content=document,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers or None,
    )
