"""
会话管理器

为多轮对话提供会话状态维护：
- 每个会话维护消息历史列表
- 支持 TTL 过期自动清理
- 线程安全（RLock 保护）
"""

import time
import uuid
import threading
from dataclasses import dataclass, field

from app.config import get_config
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Session:
    """单个会话的数据结构"""

    session_id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str) -> None:
        """追加一条消息并更新活跃时间。"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })
        self.last_active = time.time()

    @property
    def message_count(self) -> int:
        return len(self.messages)


class SessionManager:
    """
    内存会话管理器，线程安全。

    特性：
    - 会话自动创建与过期清理
    - 最多保留最近 N 轮对话作为上下文（默认 5 轮 = 10 条消息）
    """

    MAX_HISTORY_MESSAGES = 10  # 最近 10 条消息作为上下文

    def __init__(self, ttl_seconds: int = 1800) -> None:
        """
        Args:
            ttl_seconds: 会话存活时间（秒），超时未活跃则视为过期
        """
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self.ttl_seconds = ttl_seconds
        logger.info("SessionManager 初始化：TTL=%d秒", ttl_seconds)

    def create_session(self) -> str:
        """创建新会话，返回 session_id。"""
        session_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._sessions[session_id] = Session(session_id=session_id)
        logger.info("会话创建：%s", session_id)
        return session_id

    def get_session(self, session_id: str) -> Session | None:
        """
        获取会话。若不存在返回 None；若已过期则删除并返回 None。
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if self._is_expired(session):
                del self._sessions[session_id]
                logger.debug("会话过期自动清理：%s", session_id)
                return None
            return session

    def get_or_create_session(self, session_id: str) -> Session:
        """获取会话，不存在或已过期则自动创建。"""
        session = self.get_session(session_id)
        if session is None:
            new_id = self.create_session()
            return self._sessions[new_id]
        return session

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """向会话追加一条消息。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session and not self._is_expired(session):
                session.add_message(role, content)
            else:
                # 会话不存在或已过期，静默忽略
                pass

    def get_history_text(self, session_id: str) -> str:
        """
        获取会话的最近对话历史文本，用于注入 Prompt。

        Args:
            session_id: 会话 ID

        Returns:
            格式化的历史文本，若会话不存在则返回 "（无历史）"
        """
        session = self.get_session(session_id)
        if session is None or not session.messages:
            return "（无历史对话）"

        recent = session.messages[-self.MAX_HISTORY_MESSAGES:]
        lines = []
        for msg in recent:
            role_label = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"【{role_label}】{msg['content']}")
        return "\n".join(lines)

    def cleanup_expired(self) -> int:
        """
        清理所有过期会话。

        Returns:
            清理的会话数量
        """
        with self._lock:
            expired_ids = [
                sid for sid, s in self._sessions.items()
                if self._is_expired(s)
            ]
            for sid in expired_ids:
                del self._sessions[sid]
            if expired_ids:
                logger.info("清理了 %d 个过期会话", len(expired_ids))
            return len(expired_ids)

    def _is_expired(self, session: Session) -> bool:
        """判断会话是否过期。"""
        return (time.time() - session.last_active) > self.ttl_seconds

    @property
    def active_count(self) -> int:
        """当前活跃会话数。"""
        with self._lock:
            self.cleanup_expired()
            return len(self._sessions)


# 全局单例
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """获取全聚会话管理器实例。"""
    global _session_manager
    if _session_manager is None:
        cfg = get_config()
        _session_manager = SessionManager(ttl_seconds=cfg.session_ttl_seconds)
    return _session_manager
