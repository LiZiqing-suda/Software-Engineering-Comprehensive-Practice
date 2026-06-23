"""
向量嵌入管理模块

封装 HuggingFace 本地嵌入模型的加载，以及 ChromaDB 向量库的初始化。
所有操作均为同步（底层 C 库），在执行时通过 asyncio.to_thread 异步化。
"""

import os
from typing import Optional

# Chroma 向量库 — 优先新版，回退旧版
try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

# HuggingFace 嵌入 — 优先新版，回退旧版
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

from app.config import get_config
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 离线模式 — 不从 HuggingFace Hub 下载
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_vectorstore: Optional[Chroma] = None
_embeddings: Optional[HuggingFaceEmbeddings] = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    获取（或延迟初始化）嵌入模型实例。
    首次调用时加载模型，后续复用单例。
    """
    global _embeddings
    if _embeddings is None:
        cfg = get_config()
        logger.info("正在加载本地嵌入模型：%s", cfg.bge_local_path)
        _embeddings = HuggingFaceEmbeddings(
            model_name=cfg.bge_local_path,
            model_kwargs={"local_files_only": True},
        )
        logger.info("[OK] 嵌入模型加载完成")
    return _embeddings


def load_vectorstore() -> Chroma:
    """
    加载 ChromaDB 向量库。
    使用单例模式，首次调用时初始化。

    Returns:
        Chroma 向量库实例

    Raises:
        FileNotFoundError: 向量库路径不存在
    """
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    cfg = get_config()
    if not os.path.isdir(cfg.vector_db_path):
        raise FileNotFoundError(
            f"向量库路径不存在：{cfg.vector_db_path}，请先运行构建脚本"
        )

    logger.info("正在加载本地向量库：%s", cfg.vector_db_path)
    embeddings = get_embeddings()
    _vectorstore = Chroma(
        persist_directory=cfg.vector_db_path,
        embedding_function=embeddings,
    )
    doc_count = _vectorstore._collection.count() if _vectorstore._collection else 0
    logger.info("[OK] 向量库加载完成，共 %d 条文档", doc_count)
    return _vectorstore


def get_vectorstore() -> Optional[Chroma]:
    """获取已加载的向量库实例，未加载时返回 None。"""
    return _vectorstore


def close_vectorstore() -> None:
    """释放向量库资源。"""
    global _vectorstore, _embeddings
    _vectorstore = None
    _embeddings = None
    logger.info("向量库和嵌入模型已释放")
