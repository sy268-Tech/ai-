"""高层服务：把"原始小说文本 / 结构化输入"一步转成剧本。

GUI 与 CLI 都通过本模块调用，避免重复拼装流程。核心函数：

* :func:`build_novel_from_text` —— 把粘贴的整段小说文本解析成 NovelInput。
* :func:`convert_novel` —— 选择生成器（大模型优先，回退规则版）并产出剧本 dict。
* :func:`convert_text` —— 文本 → 剧本 dict + YAML + 可读视图 的一站式封装。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .adapters import LangGraphScriptGenerator, ScriptGenerator
from .config import LLMConfig
from .models import ConvertOptions, NovelChapter, NovelInput, ScreenplayYaml
from .pipeline import RuleBasedGenerator
from .renderer import render_readable_script
from .utils import split_chapters
from .yaml_io import dump_yaml


@dataclass(slots=True)
class ConversionResult:
    screenplay: ScreenplayYaml
    yaml_text: str
    readable_text: str
    generator_name: str
    used_llm: bool


def build_novel_from_text(
    raw_text: str,
    *,
    title: str = "未命名剧本",
    author: str = "",
    fmt: str = "web_series",
    language: str = "zh-CN",
    genre: Optional[list[str]] = None,
    min_chapters: int = 3,
) -> NovelInput:
    """把整段小说文本解析为 NovelInput，并校验至少 ``min_chapters`` 章。"""
    chapters_raw = split_chapters(raw_text)
    if len(chapters_raw) < min_chapters:
        raise ValueError(
            f"至少需要 {min_chapters} 个章节。请使用"
            "「第一章 / 第二章 / 第三章」这样的章节标题分隔正文。"
        )
    chapters = [
        NovelChapter(
            chapter_number=int(c["chapter_number"]),
            title=str(c["title"]),
            text=str(c["text"]),
        )
        for c in chapters_raw
    ]
    return NovelInput(
        title=title.strip() or "未命名剧本",
        author=author.strip() or None,
        chapters=chapters,
        format=fmt or "web_series",
        language=language or "zh-CN",
        genre=genre or [],
    )


def choose_generator(
    *,
    prefer_llm: bool = True,
    config: Optional[LLMConfig] = None,
) -> tuple[ScriptGenerator, bool]:
    """选择生成器。配置了 API Key 且 prefer_llm 时用大模型，否则用规则版。

    返回 (generator, used_llm)。
    """
    cfg = config or LLMConfig.from_env()
    if prefer_llm and cfg.is_configured:
        return LangGraphScriptGenerator(cfg), True
    return RuleBasedGenerator(), False


def convert_novel(
    novel: NovelInput,
    *,
    options: Optional[ConvertOptions] = None,
    prefer_llm: bool = True,
    config: Optional[LLMConfig] = None,
) -> tuple[ScreenplayYaml, bool]:
    """把 NovelInput 转成剧本 dict。大模型失败时自动回退规则版。"""
    options = options or ConvertOptions(default_format=novel.format)
    generator, used_llm = choose_generator(prefer_llm=prefer_llm, config=config)

    if used_llm:
        try:
            return generator.generate(novel, options), True
        except Exception:
            # 大模型不可用（网络/额度/Key 失效）时优雅回退，保证有产出
            return RuleBasedGenerator().generate(novel, options), False
    return generator.generate(novel, options), False


def convert_text(
    raw_text: str,
    *,
    title: str = "未命名剧本",
    author: str = "",
    fmt: str = "web_series",
    prefer_llm: bool = True,
    options: Optional[ConvertOptions] = None,
    config: Optional[LLMConfig] = None,
) -> ConversionResult:
    """一站式：原始文本 → 剧本 dict + YAML + 可读视图。"""
    novel = build_novel_from_text(raw_text, title=title, author=author, fmt=fmt)
    screenplay, used_llm = convert_novel(
        novel, options=options, prefer_llm=prefer_llm, config=config
    )
    generator_name = screenplay.get("script", {}).get("metadata", {}).get(
        "generator", "RuleBasedGenerator"
    )
    return ConversionResult(
        screenplay=screenplay,
        yaml_text=dump_yaml(screenplay),
        readable_text=render_readable_script(screenplay),
        generator_name=generator_name,
        used_llm=used_llm,
    )
