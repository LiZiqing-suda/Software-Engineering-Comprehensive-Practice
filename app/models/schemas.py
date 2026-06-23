"""
Pydantic 请求/响应数据模型

用于 FastAPI 的自动参数校验、序列化与 OpenAPI 文档生成。
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class QARequest(BaseModel):
    """问答请求"""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="用户提问内容",
        examples=["本科生绩点怎么计算？"],
    )
    session_id: str = Field(
        default="",
        max_length=64,
        description="会话 ID，为空时服务端自动创建新会话",
    )


class QAData(BaseModel):
    """问答数据载荷"""

    answer: str = Field(..., description="模型生成的回答")
    session_id: str = Field(..., description="当前会话 ID")


class QAResponse(BaseModel):
    """标准问答响应"""

    code: int = Field(default=200, description="状态码")
    data: QAData | dict = Field(default_factory=dict, description="数据载荷")
    msg: str = Field(default="success", description="提示信息")


class ErrorResponse(BaseModel):
    """错误响应"""

    code: int = Field(..., description="错误状态码")
    data: dict = Field(default_factory=dict, description="（空）")
    msg: str = Field(..., description="错误描述")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(..., description="服务状态")
    model: str = Field(..., description="当前使用的 LLM 模型")
    vectordb_document_count: int = Field(..., description="向量库文档数")


class SessionInfo(BaseModel):
    """会话信息"""

    session_id: str
    message_count: int
    created_at: float
    last_active: float
