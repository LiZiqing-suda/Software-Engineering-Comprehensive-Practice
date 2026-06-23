"""
RAG 检索引擎

核心流程：
1. 用户提问 → 向量检索 → 文档分类排序去重
2. 拼接上下文 + 对话历史 → LLM 生成回答
3. 支持同步（answer）和异步（answer_async）两种调用方式
4. 支持流式（answer_stream）逐 token 输出
"""

import asyncio
from typing import Generator

from app.config import get_config
from app.core._retrieval import classify_docs, dedup_and_truncate
from app.core.embeddings import get_vectorstore
from app.core.llm_client import answer_sync, answer_stream
from app.sessions.manager import get_session_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)




# ——————————————— 检索逻辑 ———————————————

def retrieve_context(query: str) -> str:
    """
    检索并构建上下文文本。

    Args:
        query: 用户提问

    Returns:
        拼接好的上下文字符串
    """
    cfg = get_config()
    vectordb = get_vectorstore()

    if vectordb is None:
        logger.warning("向量库未加载，返回空上下文")
        return "（向量库未就绪）"

    raw_docs = vectordb.similarity_search(query, k=cfg.top_k)
    logger.debug(
        "向量检索完成：raw=%d, query='%s...'", len(raw_docs), query[:50]
    )

    priority_docs, other_docs, graduate_docs = classify_docs(raw_docs)
    sorted_docs = priority_docs + other_docs + graduate_docs
    context_list = dedup_and_truncate(sorted_docs)
    context = "\n\n".join(context_list)

    logger.debug("最终上下文：%d 段，总长度=%d", len(context_list), len(context))
    return context


# ——————————————— 异步包装 ———————————————

async def retrieve_context_async(query: str) -> str:
    """异步版本的上下文检索（不阻塞事件循环）。"""
    return await asyncio.to_thread(retrieve_context, query)


# ——————————————— 生成逻辑 ———————————————

def _build_system_prompt(
    context: str,
    conversation_history: str,
    user_query: str,
) -> str:
    """填充 Prompt 模板。"""
    cfg = get_config()
    return cfg.prompt_template.format(
        context=context,
        conversation_history=conversation_history,
        user_query=user_query,
    )


def answer(
    query: str,
    session_id: str = "",
) -> tuple[str, str]:
    """
    完整 RAG 问答（同步）。

    Args:
        query: 用户提问
        session_id: 会话 ID，为空时自动创建

    Returns:
        (回答文本, 会话ID)
    """
    # 会话管理
    session_mgr = get_session_manager()
    if not session_id:
        session_id = session_mgr.create_session()

    # 上下文检索
    context = retrieve_context(query)

    # 对话历史
    history_text = session_mgr.get_history_text(session_id)

    # 构建 prompt & 生成
    system_content = _build_system_prompt(context, history_text, query)
    result = answer_sync(system_content, query)

    # 记录对话
    session_mgr.add_message(session_id, "user", query)
    session_mgr.add_message(session_id, "assistant", result)

    return result, session_id


async def answer_async(
    query: str,
    session_id: str = "",
) -> tuple[str, str]:
    """
    完整 RAG 问答（异步 — 检索不阻塞事件循环，但 LLM 调用仍是同步的）。

    Args:
        query: 用户提问
        session_id: 会话 ID

    Returns:
        (回答文本, 会话ID)
    """
    # 会话管理
    session_mgr = get_session_manager()
    if not session_id:
        session_id = session_mgr.create_session()

    # 异步上下文检索
    context = await retrieve_context_async(query)

    # 对话历史
    history_text = session_mgr.get_history_text(session_id)

    # 构建 prompt & 生成（LLM 调用在线程池中执行）
    system_content = _build_system_prompt(context, history_text, query)
    result = await asyncio.to_thread(answer_sync, system_content, query)

    # 记录对话
    session_mgr.add_message(session_id, "user", query)
    session_mgr.add_message(session_id, "assistant", result)

    return result, session_id


def answer_stream_generator(
    query: str,
    session_id: str = "",
) -> Generator[dict, None, None]:
    """
    RAG 流式问答生成器。

    先执行检索获取上下文，再流式输出 LLM 生成结果。
    LLM 完整输出会被记录到会话历史中。

    Args:
        query: 用户提问
        session_id: 会话 ID

    Yields:
        事件字典：
        - {"type": "meta", "session_id": "..."}  — 元信息
        - {"type": "token", "content": "..."}     — 增量 token
        - {"type": "done"}                         — 结束信号
    """
    session_mgr = get_session_manager()
    if not session_id:
        session_id = session_mgr.create_session()

    yield {"type": "meta", "session_id": session_id}

    # 检索上下文
    context = retrieve_context(query)
    history_text = session_mgr.get_history_text(session_id)
    system_content = _build_system_prompt(context, history_text, query)

    # 流式生成
    full_answer_parts: list[str] = []
    try:
        for token in answer_stream(system_content, query):
            full_answer_parts.append(token)
            yield {"type": "token", "content": token}
    except Exception as e:
        logger.error("流式生成异常：%s", str(e))
        yield {"type": "error", "message": str(e)}
        return

    # 记录对话
    full_answer = "".join(full_answer_parts).strip()
    session_mgr.add_message(session_id, "user", query)
    session_mgr.add_message(session_id, "assistant", full_answer)

    yield {"type": "done"}
