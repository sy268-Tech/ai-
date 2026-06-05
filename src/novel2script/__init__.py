"""Novel2Script AI —— 小说转结构化剧本 YAML 工具。

公开 API:
    - LLMConfig: 大模型配置（自动读取 .env）
    - RuleBasedGenerator / LangGraphScriptGenerator: 两种生成器
    - convert_text / convert_novel / build_novel_from_text: 高层服务
    - render_readable_script: 渲染标注角色/对话/环境的可读剧本
"""

from __future__ import annotations

__version__ = "0.2.0"

from .config import LLMConfig
from .models import ConvertOptions, NovelChapter, NovelInput
from .renderer import render_readable_script
from .service import (
    ConversionResult,
    build_novel_from_text,
    choose_generator,
    convert_novel,
    convert_text,
)

__all__ = [
    "__version__",
    "LLMConfig",
    "ConvertOptions",
    "NovelChapter",
    "NovelInput",
    "ConversionResult",
    "build_novel_from_text",
    "choose_generator",
    "convert_novel",
    "convert_text",
    "render_readable_script",
]
