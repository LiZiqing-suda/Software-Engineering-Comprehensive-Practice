"""
检索引擎纯逻辑函数（无外部 IO 依赖）

提取文档分类、去重截断等纯函数，使其可被独立测试
而无需加载 langchain_community / chromadb 等重型依赖。
"""

from langchain_core.documents import Document


def classify_docs(
    raw_docs: list[Document],
) -> tuple[list[Document], list[Document], list[Document]]:
    """
    按来源类型分类文档：
    - priority（本科生相关）→ other（其他）→ graduate（研究生/硕士/博士）

    Args:
        raw_docs: 向量检索原始结果

    Returns:
        (priority_docs, other_docs, graduate_docs)
    """
    priority_docs: list[Document] = []
    other_docs: list[Document] = []
    graduate_docs: list[Document] = []

    for doc in raw_docs:
        source = doc.metadata.get("source", "").lower()
        content = doc.page_content.lower()
        if "本科" in source or "本科生" in content:
            priority_docs.append(doc)
        elif any(kw in source for kw in ("研究生", "硕士", "博士")):
            graduate_docs.append(doc)
        else:
            other_docs.append(doc)

    return priority_docs, other_docs, graduate_docs


def dedup_and_truncate(
    sorted_docs: list[Document], max_docs: int = 3
) -> list[str]:
    """
    去重并截断上下文文档列表。

    使用文档前 200 字符作为去重 key。

    Args:
        sorted_docs: 已排序的文档列表
        max_docs: 最多保留的文档数

    Returns:
        格式化后的上下文字符串片段列表
    """
    seen: set[str] = set()
    context_list: list[str] = []

    for doc in sorted_docs:
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            source = doc.metadata.get("source", "未知")
            context_list.append(
                f"【来源：{source}】\n{doc.page_content}"
            )
            if len(context_list) >= max_docs:
                break

    return context_list
