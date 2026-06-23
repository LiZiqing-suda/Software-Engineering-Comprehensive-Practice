"""
启动入口 — 项目根目录直接运行

用法：
    python run.py
"""

import uvicorn
from app.config import get_config

if __name__ == "__main__":
    cfg = get_config()
    print(f"启动服务: http://{cfg.host}:{cfg.port}")
    print(f"模型: {cfg.deepseek_model}")
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level=cfg.log_level.lower(),
    )
