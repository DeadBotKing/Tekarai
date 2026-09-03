"""Exception → standard envelope mapping (Phase 06 §15).

One DRF exception handler maps:
- the Tekarai error hierarchy (each carries its ErrorCodeCatalog code),
- DRF validation failures → ``VALIDATION_ERROR`` entries with fields,
- everything unexpected → ``SYS_INTERNAL_ERROR`` (logged, never leaked).

The mapping is the only place exceptions become HTTP.
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drfExceptionHandler
from rest_framework.views import set_rollback

from apps.sharedKernel.domain.errors import TekaraiError, ValidationFailedError
from apps.sharedKernel.presentation.api.response import errorEntry, errorEnvelope

logger = logging.getLogger("tekarai.api.errors")


def tekraiExceptionHandler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drfExceptionHandler(exc, context)
    if response is not None:
        # DRF-handled errors (permission/auth/validation/parse/not found).
        errors = drfErrorsToEntries(exc, response.status_code)
        response.data = errorEnvelope(errors)
        return response

    if isinstance(exc, TekaraiError):
        set_rollback()
        entry = errorEntry(exc.code, exc.message, details=exc.details or None)
        if isinstance(exc, ValidationFailedError) and exc.fieldErrors:
            entry["field"] = next(iter(exc.fieldErrors))
            entry["details"] = {"fields": exc.fieldErrors}
        headers: dict[str, str] = {}
        retryAfterSeconds = getattr(exc, "retryAfterSeconds", None)
        if retryAfterSeconds:
            headers["Retry-After"] = str(retryAfterSeconds)
        return Response(
            errorEnvelope([entry]),
            status=exc.httpStatus,
            headers=headers or None,
        )

    logger.exception("Unhandled exception", extra={"exceptionType": type(exc).__name__})
    set_rollback()
    return Response(
        errorEnvelope([errorEntry("SYS_INTERNAL_ERROR", "Unexpected server error.")]),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def drfErrorsToEntries(exc: Exception, statusCode: int) -> list[dict[str, Any]]:
    from rest_framework.exceptions import (
        APIException,
        AuthenticationFailed,
        NotAuthenticated,
        PermissionDenied,
        ValidationError,
    )

    if isinstance(exc, ValidationError):
        fields = exc.detail if isinstance(exc.detail, dict) else {"nonField": str(exc.detail)}
        entries = [
            errorEntry("VALIDATION_ERROR", "Validation failed.", field=str(field))
            for field in fields
        ]
        return entries or [errorEntry("VALIDATION_ERROR", "Validation failed.")]
    if isinstance(exc, NotAuthenticated):
        return [errorEntry("AUTH_AUTHENTICATION_REQUIRED", "Authentication required.")]
    if isinstance(exc, AuthenticationFailed):
        return [errorEntry("AUTH_CREDENTIALS_INVALID", "Invalid credentials.")]
    if isinstance(exc, PermissionDenied):
        return [errorEntry("PERM_PERMISSION_DENIED", "Permission denied.")]
    if isinstance(exc, APIException):
        code = getattr(exc, "code", "SYS_INTERNAL_ERROR")
        return [errorEntry(str(code).upper(), str(exc.detail))]
    fallbackByStatus = {
        400: "VALIDATION_ERROR",
        403: "PERM_PERMISSION_DENIED",
        404: "SYS_RECORD_NOT_FOUND",
        405: "SYS_METHOD_NOT_ALLOWED",
        429: "SYS_RATE_LIMITED",
    }
    return [errorEntry(fallbackByStatus.get(statusCode, "SYS_INTERNAL_ERROR"), str(exc))]
