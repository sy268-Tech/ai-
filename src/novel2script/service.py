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
from .utils import split_chapters, split_chapters_with_llm
from .yaml_io import dump_yaml


@dataclass(slots=True)
class ConversionResult:
    screenplay: ScreenplayYaml
    yaml_text: str
    readable_text: str
    generator_name: str
    used_llm: bool


def _try_parse_structured_text(raw_text: str) -> tuple[list[dict[str, object]], dict[str, Any]]:
    """尝试将文本作为结构化 YAML 解析（支持多种变体格式）。

    支持的格式：
    - 标准格式：顶层 novel.chapters，字段 chapter_number / title / text
    - 简化格式：顶层 chapters，字段 chapter / title / text
    - 无包裹格式：直接 title + chapters 平铺
    - 缩进不一致格式：第一行无缩进，后续行有多余缩进（自动修正）

    返回 (chapters_list, metadata_dict)。解析失败时返回 ([], {})。
    """
    import yaml

    data = None

    # 第一次尝试：直接解析
    try:
        data = yaml.safe_load(raw_text)
    except Exception:
        pass

    # 第二次尝试：去除所有行的公共缩进（处理从 novel: 块内复制出来的情况）
    if not isinstance(data, dict):
        lines = raw_text.split("\n")
        # 找出非空行的最小缩进
        min_indent = float("inf")
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                min_indent = min(min_indent, indent)
        if min_indent > 0 and min_indent != float("inf"):
            dedented = "\n".join(line[min_indent:] if len(line) >= min_indent else line for line in lines)
            try:
                data = yaml.safe_load(dedented)
            except Exception:
                pass

    # 第三次尝试：第一行顶格但后续行有额外缩进，统一去掉后续行的多余缩进
    if not isinstance(data, dict):
        lines = raw_text.split("\n")
        if lines and not lines[0].startswith(" "):
            # 找后续非空行的公共缩进量
            subsequent_indents = []
            for line in lines[1:]:
                stripped = line.lstrip()
                if stripped:
                    subsequent_indents.append(len(line) - len(stripped))
            if subsequent_indents:
                common_indent = min(subsequent_indents)
                if common_indent > 0:
                    fixed_lines = [lines[0]]
                    for line in lines[1:]:
                        if len(line) >= common_indent:
                            fixed_lines.append(line[common_indent:])
                        else:
                            fixed_lines.append(line)
                    try:
                        data = yaml.safe_load("\n".join(fixed_lines))
                    except Exception:
                        pass

    if not isinstance(data, dict):
        return [], {}

    # 尝试定位 chapters 列表和元数据来源
    meta_source = data
    chapters_raw = None
    if "novel" in data and isinstance(data["novel"], dict):
        meta_source = data["novel"]
        chapters_raw = meta_source.get("chapters")
    elif "chapters" in data:
        chapters_raw = data.get("chapters")

    if not isinstance(chapters_raw, list) or not chapters_raw:
        return [], {}

    # 提取元数据
    metadata: dict[str, Any] = {}
    if "title" in meta_source:
        metadata["title"] = str(meta_source["title"]).strip()
    if "author" in meta_source:
        metadata["author"] = str(meta_source["author"]).strip()
    if "genre" in meta_source:
        genre_val = meta_source["genre"]
        if isinstance(genre_val, list):
            metadata["genre"] = genre_val
        elif isinstance(genre_val, str):
            # "奇幻 / 治愈" → ["奇幻", "治愈"]
            metadata["genre"] = [g.strip() for g in genre_val.replace("/", ",").split(",") if g.strip()]
    if "format" in meta_source:
        metadata["format"] = str(meta_source["format"]).strip()
    if "language" in meta_source:
        metadata["language"] = str(meta_source["language"]).strip()

    chapters: list[dict[str, object]] = []
    for idx, item in enumerate(chapters_raw, start=1):
        if not isinstance(item, dict):
            continue
        # 兼容 chapter_number / chapter / 自动编号
        number = item.get("chapter_number") or item.get("chapter") or idx
        title = str(item.get("title", f"第{number}章")).strip()
        text = str(item.get("text", "")).strip()
        if text:
            chapters.append({
                "chapter_number": int(number),
                "title": title,
                "text": text,
            })

    return chapters, metadata


def build_novel_from_text(
    raw_text: str,
    *,
    title: str = "未命名剧本",
    author: str = "",
    fmt: str = "web_series",
    language: str = "zh-CN",
    genre: Optional[list[str]] = None,
    min_chapters: int = 1,
    config: Optional[LLMConfig] = None,
) -> NovelInput:
    """把整段小说文本解析为 NovelInput，并校验至少 ``min_chapters`` 章。

    分割流程：
    0. 先检测输入是否为结构化 YAML（含 chapters 字段），若是则直接解析；
    1. 用正则匹配多种常见章节标题格式；
    2. 若正则无法切出足够章节，调用大模型进行智能切分；
    3. 若大模型也无法切分（未配置或调用失败），给出详细格式提示。
    """
    # 步骤 0：尝试作为结构化 YAML 解析
    chapters_raw, yaml_meta = _try_parse_structured_text(raw_text)

    # 从 YAML 元数据补充调用者未提供的字段
    if yaml_meta:
        if title == "未命名剧本" and "title" in yaml_meta:
            title = yaml_meta["title"]
        if not author and "author" in yaml_meta:
            author = yaml_meta["author"]
        if genre is None and "genre" in yaml_meta:
            genre = yaml_meta["genre"]
        if fmt == "web_series" and "format" in yaml_meta:
            fmt = yaml_meta["format"]
        if language == "zh-CN" and "language" in yaml_meta:
            language = yaml_meta["language"]

    # 步骤 1：正则切分
    if len(chapters_raw) < min_chapters:
        regex_chapters = split_chapters(raw_text)
        if len(regex_chapters) >= len(chapters_raw):
            chapters_raw = regex_chapters

    # 正则切分不足时，尝试调用大模型智能切分
    if len(chapters_raw) < min_chapters:
        llm_chapters = split_chapters_with_llm(raw_text, config=config)
        if len(llm_chapters) >= min_chapters:
            chapters_raw = llm_chapters

    if len(chapters_raw) < min_chapters:
        raise ValueError(
            f"至少需要 {min_chapters} 个章节。请使用章节标题分隔正文，支持的格式包括：\n"
            "• 第一章 / 第二章 / 第三章…\n"
            "• 场景1 / 场景2 / 场景3…\n"
            "• Chat1 / Chat2 / Chat3…\n"
            "• Scene 1 / Part 1 / Episode 1…\n"
            "• 1. 标题 / 2. 标题 / 3. 标题…\n"
            "• 用 --- 或 === 分隔线分隔各段\n"
            "（如已配置大模型 API Key，系统会自动尝试智能切分）"
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
    novel = build_novel_from_text(raw_text, title=title, author=author, fmt=fmt, config=config)
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
