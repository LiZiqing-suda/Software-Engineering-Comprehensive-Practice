"""
核心业务逻辑模块

子模块：
- _retrieval   — 纯逻辑函数（轻量，无外部 IO 依赖，可独立测试）
- rag_engine   — RAG 编排（需要 embeddings + llm_client）
- embeddings   — 向量嵌入管理（需要 langchain_community + chromadb）
- llm_client   — LLM 客户端（需要 openai + tenacity）

使用方式：直接导入所需子模块，避免触发重型依赖的链式加载。
  from app.core._retrieval import classify_docs, dedup_and_truncate
  from app.core.rag_engine import answer_async, answer_stream_generator
  from app.core.embeddings import load_vectorstore, get_vectorstore
"""

__all__ = [
    "_retrieval",
    "rag_engine",
    "embeddings",
    "llm_client",
]
