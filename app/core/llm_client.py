"""
LLM 客户端封装

封装 DeepSeek API（OpenAI 兼容接口）的调用，支持：
- 同步非流式调用（answer_sync）
- 同步流式调用（answer_stream），返回逐 token 迭代器
- 基于 tenacity 的自动重试
"""

from typing import Generator

from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.config import get_config
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """获取（或延迟初始化）OpenAI 客户端单例。"""
    global _client
    if _client is None:
        cfg = get_config()
        logger.info(
            "初始化 DeepSeek 客户端：model=%s, base_url=%s",
            cfg.deepseek_model,
            cfg.deepseek_base_url,
        )
        _client = OpenAI(
            api_key=cfg.deepseek_api_key,
            base_url=cfg.deepseek_base_url,
        )
    return _client


def close_client() -> None:
    """释放 LLM 客户端资源。"""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("LLM 客户端已关闭")


def _build_messages(
    system_content: str, user_query: str
) -> list[dict[str, str]]:
    """构建标准消息列表。"""
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_query},
    ]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def answer_sync(
    system_content: str,
    user_query: str,
) -> str:
    """
    同步非流式调用 LLM，带自动重试。

    Args:
        system_content: system prompt（含上下文的完整模板）
        user_query: 原始用户提问

    Returns:
        模型生成的完整回答文本
    """
    cfg = get_config()
    client = get_client()
    messages = _build_messages(system_content, user_query)

    logger.info("LLM 非流式调用：query='%s...'", user_query[:50])

    response = client.chat.completions.create(
        model=cfg.deepseek_model,
        messages=messages,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
        stream=False,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )

    content = response.choices[0].message.content.strip()
    logger.info("LLM 非流式响应完成，长度=%d 字符", len(content))
    return content


def answer_stream(
    system_content: str,
    user_query: str,
) -> Generator[str, None, None]:
    """
    同步流式调用 LLM，逐 token 产出。

    Args:
        system_content: system prompt
        user_query: 原始用户提问

    Yields:
        每个 token 的增量文本
    """
    cfg = get_config()
    client = get_client()
    messages = _build_messages(system_content, user_query)

    logger.info("LLM 流式调用：query='%s...'", user_query[:50])

    response = client.chat.completions.create(
        model=cfg.deepseek_model,
        messages=messages,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
        stream=True,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )

    token_count = 0
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            token_count += 1
            yield token

    logger.info("LLM 流式响应完成，共 %d 个 token", token_count)
