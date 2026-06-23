"""
线程安全的 IP 限流器

修复了原版的 bug（defaultdict del 后访问导致复位逻辑错误），
并通过 threading.RLock 保证多 worker 并发安全。

使用滑动窗口算法：在时间窗口内，每个 IP 最多允许 N 次请求。
"""

import time
import threading
from collections import defaultdict
from typing import Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    基于滑动窗口的 IP 限流器，线程安全。

    使用示例:
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        allowed, remaining, reset_sec = limiter.check("192.168.1.1")
    """

    def __init__(self, max_requests: int = 3, window_seconds: int = 60) -> None:
        """
        Args:
            max_requests: 窗口内最大请求数
            window_seconds: 时间窗口长度（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.RLock()
        logger.info(
            "RateLimiter 初始化：每IP %d次/%d秒", max_requests, window_seconds
        )

    def check(self, ip: str) -> Tuple[bool, int, int]:
        """
        检查 IP 是否超过限流阈值。

        Args:
            ip: 客户端 IP 地址

        Returns:
            (是否允许, 剩余次数, 重置剩余秒数)
        """
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds

            records = self._records[ip]

            # 清理过期记录 — mutates in-place
            while records and records[0] < cutoff:
                records.pop(0)

            count = len(records)

            if count >= self.max_requests:
                # 计算何时重置：最早记录 + 窗口长度 - 当前时间
                reset_sec = int(records[0] + self.window_seconds - now) + 1
                logger.debug("IP %s 触发限流，需等待 %d 秒", ip, reset_sec)
                return False, 0, reset_sec

            # 未触发限流 — 剩余次数
            remaining = self.max_requests - count - 1
            return True, remaining, 0

    def record(self, ip: str) -> None:
        """记录一次成功请求。"""
        with self._lock:
            self._records[ip].append(time.time())

    def cleanup(self) -> int:
        """
        清理所有过期的 IP 记录，避免内存泄漏。
        建议通过定时任务或后台协程定期调用。

        Returns:
            清理的 IP 数量
        """
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            stale_ips = []

            for ip, records in self._records.items():
                while records and records[0] < cutoff:
                    records.pop(0)
                if not records:
                    stale_ips.append(ip)

            for ip in stale_ips:
                del self._records[ip]

            if stale_ips:
                logger.debug("清理了 %d 个过期 IP 记录", len(stale_ips))
            return len(stale_ips)


# 全局单例 — 由 config 初始化
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """获取全局限流器实例。"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def init_rate_limiter(max_requests: int, window_seconds: int) -> RateLimiter:
    """用自定义参数初始化全局限流器。"""
    global _rate_limiter
    _rate_limiter = RateLimiter(
        max_requests=max_requests, window_seconds=window_seconds
    )
    return _rate_limiter
