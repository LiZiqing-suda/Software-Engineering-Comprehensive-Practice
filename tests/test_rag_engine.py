"""
RAG 检索引擎单元测试

测试文档分类、去重截断等纯逻辑函数（不依赖外部模型和向量库）。
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

# 从纯逻辑模块导入，不触发 langchain_community 依赖
from app.core._retrieval import classify_docs, dedup_and_truncate


def make_doc(source: str, content: str) -> Document:
    """快速创建测试用 Document。"""
    return Document(page_content=content, metadata={"source": source})


class TestClassifyDocs:
    """文档分类逻辑测试"""

    def test_undergraduate_goes_to_priority(self):
        docs = [
            make_doc("本科生手册", "本科生绩点计算规则"),
            make_doc("研究生手册", "研究生培养方案"),
        ]
        priority, other, graduate = classify_docs(docs)
        assert len(priority) == 1
        assert "本科生" in priority[0].metadata["source"]
        assert len(graduate) == 1
        assert "研究生" in graduate[0].metadata["source"]
        assert len(other) == 0

    def test_content_keyword_classification(self):
        """内容中含"本科生"关键词也应归入 priority"""
        docs = [
            make_doc("教务处通知", "关于本科生选课的通知"),
        ]
        priority, other, graduate = classify_docs(docs)
        assert len(priority) == 1
        assert len(other) == 0

    def test_master_phd_in_graduate(self):
        """含"硕士"或"博士"的应归入 graduate"""
        docs = [
            make_doc("硕士培养方案", "硕士生培养"),
            make_doc("博士培养方案", "博士生培养"),
        ]
        priority, other, graduate = classify_docs(docs)
        assert len(graduate) == 2
        assert len(priority) == 0
        assert len(other) == 0

    def test_no_keyword_goes_to_other(self):
        docs = [
            make_doc("校园地图", "校园各建筑位置"),
        ]
        priority, other, graduate = classify_docs(docs)
        assert len(other) == 1
        assert len(priority) == 0
        assert len(graduate) == 0

    def test_empty_list(self):
        priority, other, graduate = classify_docs([])
        assert priority == []
        assert other == []
        assert graduate == []

    def test_mixed_sources(self):
        docs = [
            make_doc("本科生手册", "绩点规则"),
            make_doc("通用指南", "校园交通"),
            make_doc("研究生手册", "学位要求"),
            make_doc("本科生选课", "选课指南"),
            make_doc("博士论文", "答辩流程"),
        ]
        priority, other, graduate = classify_docs(docs)
        assert len(priority) == 2
        assert len(other) == 1
        assert len(graduate) == 2


class TestDedupAndTruncate:
    """去重与截断逻辑测试"""

    def test_removes_duplicates_by_prefix(self):
        docs = [
            make_doc("source_a.txt", "A" * 300 + "unique1"),
            make_doc("source_a.txt", "A" * 300 + "unique2"),  # 前200字符相同
        ]
        result = dedup_and_truncate(docs, max_docs=5)
        assert len(result) == 1  # 第二个应被去重

    def test_keeps_different_docs(self):
        docs = [
            make_doc("src1", "B" * 300),
            make_doc("src2", "C" * 300),
        ]
        result = dedup_and_truncate(docs, max_docs=5)
        assert len(result) == 2

    def test_truncates_to_max_docs(self):
        docs = [
            make_doc(f"src{i}", f"content_{i}" * 100)
            for i in range(10)
        ]
        result = dedup_and_truncate(docs, max_docs=3)
        assert len(result) == 3

    def test_includes_source_in_output(self):
        docs = [
            make_doc("本科生手册.pdf", "绩点计算规则"),
        ]
        result = dedup_and_truncate(docs)
        assert "本科生手册.pdf" in result[0]

    def test_empty_list(self):
        result = dedup_and_truncate([], max_docs=3)
        assert result == []

    def test_unknown_source_fallback(self):
        doc = Document(page_content="test content", metadata={})
        result = dedup_and_truncate([doc])
        assert "未知" in result[0]
