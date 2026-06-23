"""
应用配置管理 — 基于环境变量，使用 python-dotenv 加载 .env 文件

所有敏感信息通过环境变量注入，不再硬编码在代码中。
开发时复制 .env.example → .env 并填入真实值。
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

# 加载项目根目录的 .env 文件（优先级高于系统环境变量）
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)


def _env(key: str, default: str = "") -> str:
    """获取环境变量，不存在时返回默认值。"""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    """获取整数型环境变量。"""
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """获取浮点型环境变量。"""
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default


@dataclass
class AppConfig:
    """应用配置数据类"""

    # === DeepSeek API ===
    deepseek_api_key: str = field(
        default_factory=lambda: _env("DEEPSEEK_API_KEY")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(
        default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-v4-flash")
    )

    # === 服务 ===
    host: str = field(
        default_factory=lambda: _env("HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: _env_int("PORT", 8080)
    )
    log_level: str = field(
        default_factory=lambda: _env("LOG_LEVEL", "INFO")
    )

    # === RAG 参数 ===
    top_k: int = field(
        default_factory=lambda: _env_int("TOP_K", 15)
    )
    max_tokens: int = field(
        default_factory=lambda: _env_int("MAX_TOKENS", 32768)
    )
    temperature: float = field(
        default_factory=lambda: _env_float("TEMPERATURE", 0.01)
    )
    top_p: float = field(
        default_factory=lambda: _env_float("TOP_P", 0.9)
    )

    # === 限流 ===
    rate_limit_max: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_MAX", 3)
    )
    rate_limit_window: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_WINDOW", 60)
    )

    # === 会话 ===
    session_ttl_seconds: int = field(
        default_factory=lambda: _env_int("SESSION_TTL_SECONDS", 1800)
    )

    # === 模型路径（相对于项目根目录） ===
    bge_local_path: str = field(
        default_factory=lambda: str(
            _project_root / "bge-small-zh-v1.5"
        )
    )
    vector_db_path: str = field(
        default_factory=lambda: str(_project_root / "vector_db_suda")
    )

    # === Prompt 模板 ===
    prompt_template: str = field(
        default_factory=lambda: _env(
            "PROMPT_TEMPLATE",
            """你是苏州大学校园政策智能问答助手。
请严格根据下面提供的参考文档回答，不能编造信息。
拒绝回答除了询问苏州大学校园政策的问题。如果问无关内容，优先回复"本系统仅回复苏州大学校园政策的问题。"。
如果提问内容是关于苏州大学校园政策的问题且文档中没有答案，请直接回复："未查询到相关校园政策信息，请自行在学校网站寻找或咨询学校工作人员。"
如果询问到绩点相关问题，必须慎重处理，需要使用下面的公式计算，不要按照文档内容，公式是4-3*(100-X)*(100-X)/1600，如果小于60分则绩点为0，无需计算。大于等于60分的情况必须准确计算，可以分步写出过程。分别给出保留一位小数和两位小数的结果，需要分别进行四舍五入。

注意：在**所有情况**的最开始**单独一行**输出"\\n**由AI生成，不保证结果的准确性，仅供参考，请仔细甄别。**"，必须单独一行，无论输入什么都要输出该免责声明，加粗。

【参考文档】
{context}

【对话历史】
{conversation_history}

【用户问题】
{user_query}

请回答：""",
        )
    )

    def validate(self) -> list[str]:
        """校验必要配置项，返回缺失项列表。"""
        errors = []
        if not self.deepseek_api_key:
            errors.append("DEEPSEEK_API_KEY 未设置 — 请在 .env 文件中配置")
        if not self.deepseek_base_url:
            errors.append("DEEPSEEK_BASE_URL 未设置")
        return errors


# 全局单例
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """获取全局配置实例。"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
