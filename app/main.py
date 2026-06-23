"""
FastAPI 应用入口

启动方式：
    python run.py               # 推荐：项目根目录的启动脚本
    python -m app.main          # 模块方式
    uvicorn app.main:app --host 0.0.0.0 --port 8080
"""

import sys
from pathlib import Path
from contextlib import asynccontextmanager

# 当直接运行 python app/main.py 时，确保项目根目录在 sys.path 中
# 这样 `from app.xxx import ...` 才能正确解析
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import router, RateLimitMiddleware
from app.config import get_config
from app.core.embeddings import load_vectorstore, close_vectorstore
from app.core.llm_client import get_client, close_client
from app.sessions.manager import get_session_manager
from app.utils.logger import setup_logger, get_logger
from app.utils.rate_limiter import init_rate_limiter

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 启动时初始化资源，关闭时释放。"""
    cfg = get_config()
    setup_logger(cfg.log_level)

    # 启动前校验
    errors = cfg.validate()
    if errors:
        logger.error("配置校验失败：%s", errors)
        sys.exit(1)

    logger.info("=== 开始初始化全局资源 ===")

    try:
        # 1. 初始化限流器
        init_rate_limiter(
            max_requests=cfg.rate_limit_max,
            window_seconds=cfg.rate_limit_window,
        )

        # 2. 初始化 LLM 客户端
        client = get_client()
        logger.info("[OK] LLM 客户端就绪：%s", cfg.deepseek_model)

        # 3. 加载向量库
        vectordb = load_vectorstore()
        logger.info("[OK] 向量库就绪")

        # 4. 初始化会话管理器
        session_mgr = get_session_manager()
        logger.info("[OK] 会话管理器就绪")

        logger.info("=== 全局资源初始化完成，服务启动 ===")
        yield

    except Exception as e:
        logger.error("[ERROR] 初始化失败：%s", str(e), exc_info=True)
        raise

    finally:
        logger.info("=== 正在释放资源 ===")
        close_client()
        close_vectorstore()
        logger.info("=== 资源释放完成 ===")


# —————————————————— 创建应用 ——————————————————

cfg = get_config()

app = FastAPI(
    title="苏州大学校园政策智能问答API",
    version="2.0.0",
    description="基于 RAG 架构的校园政策智能问答系统 — 支持流式输出与多轮对话",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定义限流中间件（在 CORS 之后）
app.add_middleware(RateLimitMiddleware)

# 静态文件挂载 — 使用绝对路径，避免 CWD 变化导致找不到目录
_static_dir = str(_PROJECT_ROOT / "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# 注册路由
app.include_router(router)

# —————————————————— 启动入口 ——————————————————

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level=cfg.log_level.lower(),
    )
