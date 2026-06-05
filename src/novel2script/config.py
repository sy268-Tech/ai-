"""集中管理大模型与运行配置。

本模块负责：
1. 从项目根目录的 ``.env`` 文件加载环境变量（借助 python-dotenv）。
2. 把零散的环境变量收敛成一个 :class:`LLMConfig` 数据类，供
   GUI / CLI / LangGraph 生成器统一读取。

设计目标：让用户只需在 ``.env`` 里填入 ``LLM_API_KEY`` 即可调用大模型，
其余字段都有合理默认值。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# 项目根目录（src/novel2script/config.py → 上溯三级到仓库根）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

# 占位符值：用户尚未填写真实 key 时的默认内容，用于判断是否已配置。
_PLACEHOLDER_KEYS = {
    "",
    "sk-your-api-key-here",
    "your-api-key",
    "your-key",
    "changeme",
}


def load_env(env_path: str | Path | None = None) -> None:
    """加载 .env 文件到进程环境变量。

    没有安装 python-dotenv 时静默跳过（仍可用系统环境变量），
    保证项目在最小依赖下也能运行。
    """
    path = Path(env_path) if env_path else ENV_PATH
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if path.exists():
        load_dotenv(dotenv_path=path, override=False)


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(slots=True)
class LLMConfig:
    """大模型调用配置。"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 4096
    max_chars_per_chapter: int = 6000

    @property
    def is_configured(self) -> bool:
        """是否填写了有效的 API Key。"""
        return self.api_key.strip() not in _PLACEHOLDER_KEYS

    @classmethod
    def from_env(cls, *, auto_load: bool = True) -> "LLMConfig":
        """从环境变量构造配置；auto_load=True 时先加载 .env。"""
        if auto_load:
            load_env()
        # 兼容历史变量名 OPENAI_API_KEY / OPENAI_BASE_URL
        api_key = (
            os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        base_url = (
            os.environ.get("LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).strip()
        model = (os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=_get_float("LLM_TEMPERATURE", 0.3),
            max_tokens=_get_int("LLM_MAX_TOKENS", 4096),
            max_chars_per_chapter=_get_int("LLM_MAX_CHARS_PER_CHAPTER", 6000),
        )
