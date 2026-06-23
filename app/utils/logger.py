"""
日志系统配置模块

提供结构化日志输出，支持控制台彩色输出和日志级别配置。
所有模块通过 get_logger() 获取统一的 logger 实例。
"""

import logging
import sys
from typing import Optional


_logger: Optional[logging.Logger] = None


def setup_logger(level: str = "INFO") -> logging.Logger:
    """
    初始化全局日志器。

    Args:
        level: 日志级别，默认 INFO

    Returns:
        配置好的 logger 实例
    """
    global _logger

    logger = logging.getLogger("suda_qa")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 控制台 handler — Windows 下强制 UTF-8，避免 emoji 等字符导致崩溃
    # 用 errors='replace' 保证无法编码的字符被替换而非抛异常
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)

    # 使用简洁格式：时间 | 级别 | 模块 | 消息
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s.%(module)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    _logger = logger
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取 logger 实例。若未初始化则使用默认配置。

    Args:
        name: 子 logger 名称，为 None 时返回根 logger

    Returns:
        logger 实例
    """
    global _logger
    if _logger is None:
        setup_logger()

    if name:
        return _logger.getChild(name)
    return _logger
