"""
API 路由定义

端点列表：
- GET  /              首页（HTML）
- GET  /health        健康检查
- POST /api/qa        非流式问答
- POST /api/qa/stream 流式问答（SSE）
"""

import json
import time
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.config import get_config
from app.core.embeddings import get_vectorstore
from app.core.rag_engine import answer_async, answer_stream_generator
from app.models.schemas import QARequest
from app.utils.logger import get_logger
from app.utils.rate_limiter import get_rate_limiter

logger = get_logger(__name__)

router = APIRouter()

# 项目根目录（用于定位静态文件）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# —————————————————— 页面 ——————————————————

@router.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面。"""
    html_path = _PROJECT_ROOT / "static" / "index.html"
    try:
        return html_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="前端页面文件未找到")


# —————————————————— 健康检查 ——————————————————

@router.get("/health")
async def health():
    """服务健康检查端点。"""
    cfg = get_config()
    vectordb = get_vectorstore()
    doc_count = 0
    if vectordb is not None and vectordb._collection is not None:
        doc_count = vectordb._collection.count()

    return {
        "status": "ok",
        "model": cfg.deepseek_model,
        "vectordb_document_count": doc_count,
    }


# —————————————————— 非流式问答 ——————————————————

@router.post("/api/qa")
async def qa(request: Request, body: QARequest):
    """
    非流式问答接口。

    提交问题后等待完整回答，适用于不需要实时反馈的场景。
    """
    vectordb = get_vectorstore()
    if vectordb is None:
        raise HTTPException(
            status_code=503, detail="系统正在初始化，请稍后再试"
        )

    # 记录限流
    client_ip = request.client.host if request.client else "unknown"
    limiter = get_rate_limiter()

    # 再次检查限流（中间件已做第一道检查，此处为双保险）
    allowed, remaining, reset_sec = limiter.check(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "data": {},
                "msg": f"请求过于频繁，请 {reset_sec} 秒后再试",
            },
        )

    try:
        result, session_id = await answer_async(
            query=body.query,
            session_id=body.session_id,
        )
        # 记录限流计数
        limiter.record(client_ip)

        return {
            "code": 200,
            "data": {"answer": result, "session_id": session_id},
            "msg": "success",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("问答异常：%s", str(e), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "data": {}, "msg": f"服务器错误：{str(e)}"},
        )


# —————————————————— 流式问答 ——————————————————

@router.post("/api/qa/stream")
async def qa_stream(request: Request, body: QARequest):
    """
    流式问答接口（Server-Sent Events）。

    提交问题后通过 SSE 推送 token 增量，前端可实时渲染。
    流结束时发送 [DONE] 信号。
    """
    vectordb = get_vectorstore()
    if vectordb is None:
        raise HTTPException(
            status_code=503, detail="系统正在初始化，请稍后再试"
        )

    client_ip = request.client.host if request.client else "unknown"
    limiter = get_rate_limiter()

    allowed, _, reset_sec = limiter.check(client_ip)
    if not allowed:
        # 限流时返回普通 JSON（SSE 连接建立前拒绝）
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "data": {},
                "msg": f"请求过于频繁，请 {reset_sec} 秒后再试",
            },
        )

    # 记录限流
    limiter.record(client_ip)

    async def event_generator():
        """
        SSE 事件生成器 — 将同步生成器包装为异步流。
        每个事件格式：data: <JSON>\n\n
        """
        try:
            # 在线程池中运行同步生成器，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            gen = await loop.run_in_executor(
                None,
                lambda: answer_stream_generator(body.query, body.session_id),
            )

            # 由于生成器本身是同步的，我们用 run_in_executor 逐个产出
            # 通过队列传递结果
            queue: asyncio.Queue = asyncio.Queue()

            def _produce():
                try:
                    for item in gen:
                        loop.call_soon_threadsafe(
                            queue.put_nowait, item
                        )
                except Exception as exc:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "error", "message": str(exc)},
                    )
                finally:
                    loop.call_soon_threadsafe(
                        queue.put_nowait, None  # sentinel
                    )

            executor_future = loop.run_in_executor(None, _produce)

            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

            await executor_future

        except Exception as e:
            logger.error("SSE 流异常：%s", str(e), exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )
