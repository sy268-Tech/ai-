from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ScriptFormat = Literal[
    "film",
    "web_series",
    "short_drama",
    "animation",
    "audio_drama",
    "stage_play",
    "unknown",
]


@dataclass(slots=True)
class NovelChapter:
    chapter_number: int
    title: str
    text: str


@dataclass(slots=True)
class NovelInput:
    title: str
    author: str | None
    chapters: list[NovelChapter]
    format: ScriptFormat = "web_series"
    language: str = "zh-CN"
    genre: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConvertOptions:
    max_paragraphs_per_scene: int = 6
    keep_source_refs: bool = True
    default_format: ScriptFormat = "web_series"


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


ScreenplayYaml = dict[str, Any]
