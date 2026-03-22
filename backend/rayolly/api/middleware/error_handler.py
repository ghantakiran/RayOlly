"""Global error handling middleware."""
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error("unhandled_exception",
                path=request.url.path,
                method=request.method,
                error=str(exc),
                exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request.headers.get("x-request-id", "unknown")}
            )
