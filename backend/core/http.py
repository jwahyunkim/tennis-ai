import json
import logging
import time
from uuid import uuid4

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger("tennis.http")


class RequestBodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(413, "Request too large")


class RequestMiddleware:
    """Bound request bodies before multipart parsing; log no credentials or query."""

    def __init__(self, app, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.monotonic()
        request_id = str(uuid4())
        size = 0
        response_started = False
        status_code = 500
        settings = getattr(scope.get("app").state, "settings", None)
        maximum = (
            min(self.max_body_bytes, settings.max_upload_bytes + 1024**2)
            if settings
            else self.max_body_bytes
        )
        if not (scope["method"] == "POST" and scope["path"] == "/api/v1/videos"):
            maximum = min(maximum, 65536)

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > maximum:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                existing = {key.lower() for key, _ in headers}
                for key, value in [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"),
                ]:
                    if key not in existing:
                        headers.append((key, value))
            await send(message)

        scope.setdefault("state", {})["request_id"] = request_id
        headers = dict(scope.get("headers", []))
        try:
            try:
                declared = int(headers.get(b"content-length", b"0"))
            except ValueError:
                declared = -1
            if declared < 0 or declared > maximum:
                raise RequestBodyTooLarge
            await self.app(scope, bounded_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            response = JSONResponse(
                {
                    "error": {
                        "code": "request_too_large",
                        "message": "요청 용량을 초과했습니다.",
                    }
                },
                status_code=413,
            )
            await response(scope, receive, tracked_send)
        except Exception as exc:
            if response_started:
                raise
            # Exception messages from storage/DB drivers may contain private data.
            logger.error(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "error_type": type(exc).__name__,
                    }
                )
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "요청을 처리하지 못했습니다.",
                    }
                },
            )
            await response(scope, receive, tracked_send)
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status_code,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    }
                )
            )
