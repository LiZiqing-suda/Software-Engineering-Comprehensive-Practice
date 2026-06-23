"""
限流器单元测试

覆盖：
- 正常请求不受限
- 超出上限后拒绝
- 窗口过期后恢复
- 并发安全
"""

import time
import threading
import pytest

from app.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    """限流器核心功能测试"""

    def test_single_request_allowed(self):
        """单次请求应被允许"""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        allowed, remaining, reset_sec = limiter.check("127.0.0.1")
        assert allowed is True
        assert remaining == 2  # 3 - 0 - 1
        assert reset_sec == 0

    def test_multiple_requests_allowed_within_limit(self):
        """在限制范围内，多次请求都应被允许"""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for i in range(5):
            allowed, remaining, _ = limiter.check("127.0.0.1")
            assert allowed is True, f"第 {i+1} 次请求应被允许"
            assert remaining == 5 - i - 1
            limiter.record("127.0.0.1")

    def test_exceeds_limit_blocks_request(self):
        """超出上限后，请求应被拒绝"""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        ip = "192.168.1.1"

        # 达到上限
        for _ in range(3):
            limiter.record(ip)

        # 下一次检查应拒绝
        allowed, remaining, reset_sec = limiter.check(ip)
        assert allowed is False
        assert remaining == 0
        assert reset_sec > 0

    def test_window_expires_allows_new_request(self):
        """窗口时间过后，新请求应被允许"""
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        ip = "10.0.0.1"

        # 达到上限
        limiter.record(ip)
        limiter.record(ip)

        # 等待窗口过期
        time.sleep(1.1)

        # 过期后应被允许
        allowed, remaining, _ = limiter.check(ip)
        assert allowed is True
        assert remaining == 1  # 2 - 0 - 1（旧记录已被清理）

    def test_different_ips_independent(self):
        """不同 IP 应有独立的限流计数"""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # IP A 达到上限
        limiter.record("10.0.0.1")
        limiter.record("10.0.0.1")

        # IP B 应不受影响
        allowed, remaining, _ = limiter.check("10.0.0.2")
        assert allowed is True
        assert remaining == 1

    def test_record_appends_timestamp(self):
        """record() 应正确追加时间戳"""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        ip = "172.16.0.1"

        limiter.record(ip)
        limiter.record(ip)

        with limiter._lock:
            assert len(limiter._records[ip]) == 2

    def test_cleanup_removes_stale_ips(self):
        """cleanup() 应清理过期的 IP 记录"""
        limiter = RateLimiter(max_requests=3, window_seconds=0)  # 窗口为0，立即过期
        ip = "172.16.0.1"

        limiter.record(ip)
        # 记录马上过期

        cleaned = limiter.cleanup()
        assert cleaned >= 1

        with limiter._lock:
            assert ip not in limiter._records

    def test_cleanup_empty_when_no_stale(self):
        """无过期记录时 cleanup 应返回 0"""
        limiter = RateLimiter(max_requests=3, window_seconds=3600)
        limiter.record("10.0.0.1")

        cleaned = limiter.cleanup()
        assert cleaned == 0  # 所有记录都还在窗口内


class TestRateLimiterConcurrency:
    """限流器并发安全测试"""

    def test_concurrent_access_no_race(self):
        """多线程并发访问不应导致数据竞争"""
        limiter = RateLimiter(max_requests=100, window_seconds=60)
        errors = []

        def worker(ip_suffix):
            try:
                for _ in range(50):
                    ip = f"192.168.{ip_suffix}.1"
                    allowed, _, _ = limiter.check(ip)
                    if allowed:
                        limiter.record(ip)
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发错误：{errors}"

        # 验证记录的完整性 — 每个 IP 不超过 max_requests
        with limiter._lock:
            for ip, records in limiter._records.items():
                assert len(records) <= 100, f"IP {ip} 记录数超出限制"
