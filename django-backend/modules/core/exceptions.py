# ===================== SHARED / CROSS-CUTTING: exceptions =====================
# The one canonical DomainError. Every module used to define its own copy and
# catch it per-view; the DRF exception handler below makes raising it from any
# service enough — no per-view try/except needed.

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler


class DomainError(Exception):
    """Business-rule violation. Rendered as HTTP 400 (or ``http_status``).

    Raise from services/models; the exception handler turns it into
    ``{"detail": str(exc)}`` so views never need their own try/except.
    """

    http_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, message, http_status=None):
        super().__init__(message)
        if http_status is not None:
            self.http_status = http_status


class ConflictError(DomainError):
    """A state conflict (duplicate, already-processed, stale). HTTP 409."""

    http_status = status.HTTP_409_CONFLICT


def domain_exception_handler(exc, context):
    """DRF EXCEPTION_HANDLER: DomainError -> JSON error; everything else default."""
    if isinstance(exc, DomainError):
        return Response({"detail": str(exc)}, status=exc.http_status)
    return drf_default_handler(exc, context)
