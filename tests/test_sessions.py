"""
会话管理器单元测试

覆盖：
- 会话创建
- 消息追加与历史获取
- 会话过期清理
"""

import time
import pytest

from app.sessions.manager import SessionManager, Session


class TestSession:
    """Session 数据结构测试"""

    def test_add_message(self):
        s = Session(session_id="test")
        assert s.message_count == 0

        s.add_message("user", "hello")
        assert s.message_count == 1
        assert s.messages[0]["role"] == "user"
        assert s.messages[0]["content"] == "hello"

    def test_last_active_updates_on_message(self):
        s = Session(session_id="test")
        old_time = s.last_active
        time.sleep(0.01)
        s.add_message("user", "hello")
        assert s.last_active > old_time


class TestSessionManager:
    """SessionManager 核心功能测试"""

    def test_create_session_returns_id(self):
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()
        assert isinstance(sid, str)
        assert len(sid) == 12  # uuid4 hex[:12]

    def test_get_existing_session(self):
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()
        session = mgr.get_session(sid)
        assert session is not None
        assert session.session_id == sid

    def test_get_nonexistent_session_returns_none(self):
        mgr = SessionManager(ttl_seconds=1800)
        assert mgr.get_session("nonexistent") is None

    def test_get_or_create_returns_existing(self):
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()
        session = mgr.get_or_create_session(sid)
        assert session.session_id == sid

    def test_get_or_create_creates_new(self):
        mgr = SessionManager(ttl_seconds=1800)
        session = mgr.get_or_create_session("nonexistent")
        assert session is not None
        assert session.session_id != "nonexistent"

    def test_add_message_to_session(self):
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()
        mgr.add_message(sid, "user", "测试问题")
        mgr.add_message(sid, "assistant", "测试回答")

        session = mgr.get_session(sid)
        assert session.message_count == 2
        assert session.messages[0]["content"] == "测试问题"
        assert session.messages[1]["content"] == "测试回答"

    def test_history_text_format(self):
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()
        mgr.add_message(sid, "user", "绩点怎么算")
        mgr.add_message(sid, "assistant", "绩点公式为...")

        text = mgr.get_history_text(sid)
        assert "【用户】绩点怎么算" in text
        assert "【助手】绩点公式为..." in text

    def test_history_text_empty_session(self):
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()
        text = mgr.get_history_text(sid)
        assert text == "（无历史对话）"

    def test_history_text_nonexistent(self):
        mgr = SessionManager(ttl_seconds=1800)
        text = mgr.get_history_text("nonexistent")
        assert text == "（无历史对话）"

    def test_expired_session_returns_none(self):
        mgr = SessionManager(ttl_seconds=0)  # 立即过期
        sid = mgr.create_session()

        # 会话应被视为过期
        session = mgr.get_session(sid)
        assert session is None

    def test_cleanup_removes_expired(self):
        mgr = SessionManager(ttl_seconds=0)
        mgr.create_session()
        mgr.create_session()

        cleaned = mgr.cleanup_expired()
        assert cleaned >= 2
        assert mgr.active_count == 0

    def test_max_history_truncation(self):
        """应只保留最近 MAX_HISTORY_MESSAGES 条消息"""
        mgr = SessionManager(ttl_seconds=1800)
        sid = mgr.create_session()

        # 添加超过上限的消息
        for i in range(mgr.MAX_HISTORY_MESSAGES + 6):
            mgr.add_message(sid, "user", f"msg-{i}")

        text = mgr.get_history_text(sid)
        # 最早的消息不应出现在历史中
        assert "msg-0" not in text
        # 但最近的应在
        last_index = mgr.MAX_HISTORY_MESSAGES + 5
        assert f"msg-{last_index}" in text

    def test_active_count(self):
        mgr = SessionManager(ttl_seconds=3600)
        assert mgr.active_count == 0
        mgr.create_session()
        mgr.create_session()
        assert mgr.active_count == 2
