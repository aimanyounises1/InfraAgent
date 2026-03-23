"""Request correlation middleware — assigns X-Request-ID to every request.

The correlation ID is stored in a ``contextvars.ContextVar`` so that
structured loggers can include it automatically.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.logging_config import request_id_ctx

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Propagate or generate X-Request-ID for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Use the client-supplied ID or mint a new one.
        req_id: str = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
        token = request_id_ctx.set(req_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)
