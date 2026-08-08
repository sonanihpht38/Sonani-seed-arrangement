"""
Request-ID propagation + logging integration.

Every request gets an id (from an inbound `X-Request-ID` if the load balancer set
one, otherwise freshly generated). The id is:
  * stored in a contextvar so any code on the request's thread can read it,
  * added to every log record via `RequestIDLogFilter`,
  * echoed back on the response `X-Request-ID` header.

That single id is what lets you grep one user's request across the proxy, the
app logs, and (if you pass it along) Celery tasks.
"""

import logging
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"


def get_request_id() -> str:
    return _request_id.get()


class RequestIDMiddleware:
    """Attach a request id to the request, the response header, and the log context."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.META.get(HEADER) or uuid.uuid4().hex
        token = _request_id.set(rid)
        request.request_id = rid
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[RESPONSE_HEADER] = rid
        return response


class RequestIDLogFilter(logging.Filter):
    """Inject `request_id` into every log record so formatters can render it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
