"""
FastAPI 中间件

- RateLimitMiddleware: 基于 IP 的请求限流中间件
"""

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.utils.rate_limiter import get_rate_limiter
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    IP 级别限流中间件。

    只对 /api/ 路径生效，静态文件和页面不受限制。
    限流时返回 429 Too Many Requests，并附带 RateLimit 系列响应头。
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # 仅对 API 路径限流
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        limiter = get_rate_limiter()
        client_ip = (
            request.client.host if request.client else "unknown"
        )

        allowed, remaining, reset_sec = limiter.check(client_ip)

        if not allowed:
            logger.debug("限流拒绝：IP=%s, path=%s", client_ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "data": {},
                    "msg": (
                        f"请求过于频繁，请 {reset_sec} 秒后再试"
                        f"（单IP每分钟最多 {limiter.max_requests} 次）"
                    ),
                },
                headers={
                    "X-RateLimit-Limit": str(limiter.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + reset_sec)),
                    "Retry-After": str(reset_sec),
                },
            )

        response = await call_next(request)

        # 注入限流头
        response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time() + limiter.window_seconds)
        )

        return response
