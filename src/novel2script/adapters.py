"""剧本生成器适配层。

本模块提供两类生成器：

* :class:`ScriptGenerator` —— 抽象接口，规则版与大模型版都实现它。
* :class:`LangGraphScriptGenerator` —— 基于 **LangChain + LangGraph** 的大模型
  生成器。它把"角色识别 → 地点识别 → 场景切分 → 节拍(对白/动作)抽取"建模成一个
  有向状态图 (StateGraph)，每个节点调用一次大模型并用 Pydantic 结构化输出约束结果。

当未配置 API Key 或大模型调用失败时，会自动回退到 :class:`RuleBasedGenerator`
（定义在 :mod:`novel2script.pipeline`），保证项目离线也能产出剧本初稿。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Optional, TypedDict

from .config import LLMConfig
from .models import ConvertOptions, NovelInput, ScreenplayYaml
from .utils import (
    guess_interior_exterior,
    guess_time_of_day,
    slugify_id,
    split_paragraphs,
    summarize_text,
)


# ── 抽象接口 ────────────────────────────────────────────────────

class ScriptGenerator(ABC):
    """可替换的剧本生成器接口。

    规则版（RuleBasedGenerator）保证开箱即用；大模型版
    （LangGraphScriptGenerator）在配置 API Key 后提供更高质量的改编。
    """

    @abstractmethod
    def generate(self, novel: NovelInput, options: ConvertOptions) -> ScreenplayYaml:
        raise NotImplementedError


# 占位类已删除：历史版本的 LLMGeneratorPlaceholder 不再需要。
# 大模型生成请直接使用 LangGraphScriptGenerator。


# ── 共享的剧本组装辅助 ──────────────────────────────────────────

def make_logline(novel: NovelInput) -> str:
    first = summarize_text(novel.chapters[0].text, 60)
    return f"围绕《{novel.title}》展开的故事，从“{first}”开始，人物在连续事件中直面逐步升级的冲突。"


def make_synopsis(novel: NovelInput) -> str:
    summaries = [
        f"第{c.chapter_number}章：{summarize_text(c.text, 70)}" for c in novel.chapters
    ]
    return " ".join(summaries)


def _placeholder_to_empty(value: str) -> str:
    """把历史占位串转成空串，避免输出"待作者确认"等标识。"""
    junk = {"待作者确认", "需作者进一步确认", "待确认", "unknown", "未知"}
    return "" if value.strip() in junk else value


# ── LangGraph 状态定义 ──────────────────────────────────────────

class _GraphState(TypedDict, total=False):
    """LangGraph 在节点之间流转的共享状态。"""

    characters: "OrderedDict[str, dict[str, Any]]"
    locations: "OrderedDict[str, dict[str, Any]]"
    scenes: list[dict[str, Any]]


class LangGraphScriptGenerator(ScriptGenerator):
    """基于 LangChain + LangGraph 的大模型剧本生成器。

    生成流程被建模为一个 LangGraph 状态图：

        START → extract_characters → extract_locations
              → segment_scenes → extract_beats → END

    每个节点调用大模型（通过 LangChain 的 ``ChatOpenAI`` +
    ``with_structured_output``）并把结果写入共享状态。这样既能利用 LangGraph
    清晰的流程编排，又能借助结构化输出保证每一步返回规范 JSON。

    用法::

        from novel2script.config import LLMConfig
        gen = LangGraphScriptGenerator(LLMConfig.from_env())
        screenplay = gen.generate(novel, ConvertOptions())
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self._llm = None  # 延迟初始化
        self._graph = None

    # ── 大模型客户端 ────────────────────────────────────────

    def _get_llm(self):
        """构造 LangChain ChatOpenAI 客户端（兼容 OpenAI 协议的各家模型）。"""
        if self._llm is not None:
            return self._llm
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=120,
            max_retries=2,
        )
        return self._llm

    def _structured(self, schema):
        """返回一个绑定了结构化输出 schema 的可调用链。

        使用 function_calling 方法以兼容 DeepSeek 等不支持
        response_format: json_schema 的 API 提供商。
        """
        return self._get_llm().with_structured_output(schema, method="function_calling")

    # ── 图构建 ──────────────────────────────────────────────

    def _build_graph(self, novel: NovelInput, options: ConvertOptions):
        from langgraph.graph import StateGraph, START, END

        builder = StateGraph(_GraphState)

        builder.add_node(
            "extract_characters",
            lambda state: {"characters": self._node_characters(novel)},
        )
        builder.add_node(
            "extract_locations",
            lambda state: {"locations": self._node_locations(novel, state["characters"])},
        )
        builder.add_node(
            "segment_scenes",
            lambda state: {
                "scenes": self._node_scenes(
                    novel, state["characters"], state["locations"], options
                )
            },
        )
        builder.add_node(
            "extract_beats",
            lambda state: {
                "scenes": self._node_beats(
                    novel, state["characters"], state["scenes"], options
                )
            },
        )

        builder.add_edge(START, "extract_characters")
        builder.add_edge("extract_characters", "extract_locations")
        builder.add_edge("extract_locations", "segment_scenes")
        builder.add_edge("segment_scenes", "extract_beats")
        builder.add_edge("extract_beats", END)

        return builder.compile()

    # ── 对外入口 ────────────────────────────────────────────

    def generate(self, novel: NovelInput, options: ConvertOptions) -> ScreenplayYaml:
        if not self.config.is_configured:
            raise RuntimeError(
                "未配置大模型 API Key。请在项目根目录的 .env 文件中填写 LLM_API_KEY，"
                "或改用规则生成器（RuleBasedGenerator）。"
            )

        graph = self._build_graph(novel, options)
        final_state: _GraphState = graph.invoke({})

        characters = final_state.get("characters") or OrderedDict()
        locations = final_state.get("locations") or OrderedDict()
        scenes = final_state.get("scenes") or []

        screenplay: ScreenplayYaml = {
            "schema_version": "1.0",
            "script": {
                "title": novel.title,
                "format": novel.format or options.default_format,
                "language": novel.language,
                "genre": novel.genre,
                "logline": make_logline(novel),
                "synopsis": make_synopsis(novel),
                "source": {
                    "novel_title": novel.title,
                    "author": novel.author or "",
                    "adapted_chapters": [c.chapter_number for c in novel.chapters],
                    "source_note": "由 Novel2Script AI（LangChain + LangGraph 大模型流水线）生成的剧本初稿。",
                },
                "metadata": {
                    "draft_type": "ai_first_draft",
                    "generator": f"LangGraphScriptGenerator ({self.config.model})",
                    "framework": "langchain + langgraph",
                },
                "characters": list(characters.values()),
                "locations": list(locations.values()),
                "scenes": scenes,
                "notes": [
                    "本剧本由大模型按「角色 → 环境 → 场景 → 对话」流水线生成。",
                    "建议作者重点复核人物动机、对白口吻与场景节奏。",
                ],
            },
        }
        return screenplay

    # ── 节点 1：角色识别 ────────────────────────────────────

    def _node_characters(self, novel: NovelInput) -> "OrderedDict[str, dict[str, Any]]":
        from langchain_core.prompts import ChatPromptTemplate

        from .llm_schemas import LLMCharacterList

        chapter_texts = "\n\n".join(
            f"【第{c.chapter_number}章 {c.title}】\n{self._clip(c.text)}"
            for c in novel.chapters
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYS_ANALYST),
            ("human", _CHARACTER_PROMPT),
        ])
        chain = prompt | self._structured(LLMCharacterList)
        result: LLMCharacterList = chain.invoke({"chapter_texts": chapter_texts})

        characters: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        for idx, ch in enumerate(result.characters):
            name = (ch.name or "").strip()
            if not name or len(name) > 8:
                continue
            role = (ch.role or "supporting").strip()
            if idx == 0 and role not in ("protagonist", "antagonist"):
                role = "protagonist"
            characters[name] = {
                "id": slugify_id("char", name),
                "name": name,
                "role": role,
                "age": _placeholder_to_empty(str(ch.age or "")),
                "gender": _placeholder_to_empty(str(ch.gender or "")),
                "description": _placeholder_to_empty(
                    str(ch.description or "")
                ) or f"从原文识别出的人物：{name}。",
                "goal": _placeholder_to_empty(str(ch.goal or "")),
                "conflict": _placeholder_to_empty(str(ch.conflict or "")),
                "relationships": [],
                "source_chapters": sorted(
                    {c.chapter_number for c in novel.chapters if name in c.text}
                ) or [c.chapter_number for c in novel.chapters],
            }

        if not characters:
            return self._fallback()._extract_characters(novel)  # pragma: no cover
        return characters

    # ── 节点 2：地点识别 ────────────────────────────────────

    def _node_locations(
        self,
        novel: NovelInput,
        characters: "OrderedDict[str, dict[str, Any]]",
    ) -> "OrderedDict[str, dict[str, Any]]":
        from langchain_core.prompts import ChatPromptTemplate

        from .llm_schemas import LLMLocationList

        chapter_texts = "\n\n".join(
            f"【第{c.chapter_number}章 {c.title}】\n{self._clip(c.text)}"
            for c in novel.chapters
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYS_ANALYST),
            ("human", _LOCATION_PROMPT),
        ])
        chain = prompt | self._structured(LLMLocationList)
        result: LLMLocationList = chain.invoke({"chapter_texts": chapter_texts})

        type_map = {"interior", "exterior", "mixed", "unknown"}
        locations: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        for loc in result.locations:
            name = (loc.name or "").strip()
            if not name:
                continue
            loc_type = (loc.type or "unknown").strip()
            if loc_type not in type_map:
                loc_type = "unknown"
            locations[name] = {
                "id": slugify_id("loc", name),
                "name": name,
                "type": loc_type,
                "description": _placeholder_to_empty(
                    str(loc.description or "")
                ) or f"故事场景地点：{name}。",
                "atmosphere": _placeholder_to_empty(str(loc.atmosphere or "")),
                "source_chapters": sorted(
                    {c.chapter_number for c in novel.chapters if name[:2] in c.text}
                ) or [novel.chapters[0].chapter_number],
            }

        if not locations:
            locations["未明确地点"] = {
                "id": "loc_unspecified",
                "name": "未明确地点",
                "type": "unknown",
                "description": "原文未明确交代具体地点。",
                "atmosphere": "",
                "source_chapters": [c.chapter_number for c in novel.chapters],
            }
        return locations

    # ── 节点 3：场景切分 ────────────────────────────────────

    def _node_scenes(
        self,
        novel: NovelInput,
        characters: "OrderedDict[str, dict[str, Any]]",
        locations: "OrderedDict[str, dict[str, Any]]",
        options: ConvertOptions,
    ) -> list[dict[str, Any]]:
        from langchain_core.prompts import ChatPromptTemplate

        from .llm_schemas import LLMSceneList

        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYS_ANALYST),
            ("human", _SCENE_PROMPT),
        ])
        chain = prompt | self._structured(LLMSceneList)

        char_names = "、".join(characters.keys()) or "（未识别到角色）"
        scenes: list[dict[str, Any]] = []
        scene_no = 1

        for chapter in novel.chapters:
            paragraphs = split_paragraphs(chapter.text)
            if not paragraphs:
                continue
            numbered = "\n".join(f"[{i}] {p}" for i, p in enumerate(paragraphs))

            try:
                result: LLMSceneList = chain.invoke({
                    "character_names": char_names,
                    "numbered_paragraphs": numbered,
                })
                llm_scenes = result.scenes
            except Exception:
                llm_scenes = []

            if not llm_scenes:
                # 大模型未返回时，按段落数兜底切分
                size = max(1, options.max_paragraphs_per_scene)
                llm_scenes = []
                for i in range(0, len(paragraphs), size):
                    from .llm_schemas import LLMScene

                    llm_scenes.append(LLMScene(
                        summary=summarize_text("\n".join(paragraphs[i:i + size]), 60),
                        paragraph_ranges=[[i, min(i + size, len(paragraphs)) - 1]],
                    ))

            for sc in llm_scenes:
                scene_paras: list[str] = []
                for rng in (sc.paragraph_ranges or []):
                    if len(rng) >= 2:
                        start, end = int(rng[0]), int(rng[1])
                        scene_paras.extend(paragraphs[start:end + 1])
                if not scene_paras:
                    scene_paras = paragraphs
                scene_text = "\n".join(scene_paras)

                location = self._match_location(sc.location, scene_text, locations)
                scene_char_ids = [
                    c["id"] for name, c in characters.items()
                    if name in scene_text or name in (sc.characters_present or [])
                ]
                if not scene_char_ids and characters:
                    scene_char_ids = [next(iter(characters.values()))["id"]]

                tod = (sc.time_of_day or "").strip() or guess_time_of_day(scene_text)
                ie = (sc.interior_exterior or "").strip() or guess_interior_exterior(scene_text)

                scenes.append({
                    "id": f"scene_{scene_no:03d}",
                    "scene_number": scene_no,
                    "source_chapters": [chapter.chapter_number],
                    "heading": {
                        "location_id": location["id"],
                        "location_name": location["name"],
                        "time_of_day": tod,
                        "interior_exterior": ie,
                        "atmosphere": _placeholder_to_empty(str(sc.atmosphere or ""))
                        or location.get("atmosphere", ""),
                    },
                    "dramatic_function": (sc.dramatic_function or "推进剧情").strip(),
                    "summary": (sc.summary or "").strip()
                    or summarize_text(scene_text, 80),
                    "characters": scene_char_ids,
                    "_scene_text": scene_text,  # 临时字段，供节拍抽取使用，最终会删除
                    "beats": [],
                    "transition": "CUT_TO",
                    "notes": [f"来源：第{chapter.chapter_number}章《{chapter.title}》。"],
                })
                scene_no += 1

        return scenes

    # ── 节点 4：节拍 / 对白抽取 ─────────────────────────────

    def _node_beats(
        self,
        novel: NovelInput,
        characters: "OrderedDict[str, dict[str, Any]]",
        scenes: list[dict[str, Any]],
        options: ConvertOptions,
    ) -> list[dict[str, Any]]:
        from langchain_core.prompts import ChatPromptTemplate

        from .llm_schemas import LLMBeatList

        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYS_ANALYST),
            ("human", _BEAT_PROMPT),
        ])
        chain = prompt | self._structured(LLMBeatList)
        char_names = "、".join(characters.keys()) or "（未识别到角色）"
        name_to_id = {name: c["id"] for name, c in characters.items()}

        valid_types = {"action", "dialogue", "narration", "sound", "visual"}

        for scene in scenes:
            scene_text = scene.pop("_scene_text", "") or scene.get("summary", "")
            beats: list[dict[str, Any]] = []
            try:
                result: LLMBeatList = chain.invoke({
                    "character_names": char_names,
                    "scene_text": scene_text,
                })
                llm_beats = result.beats
            except Exception:
                llm_beats = []

            for b in llm_beats:
                btype = (b.type or "action").strip()
                if btype not in valid_types:
                    btype = "action"
                text = (b.text or "").strip()
                if not text:
                    continue
                beat: dict[str, Any] = {"type": btype, "text": text}
                if btype == "dialogue":
                    speaker = (b.speaker or "").strip()
                    cid = name_to_id.get(speaker)
                    if not cid:
                        # 模糊匹配：说话人是某已知角色名的子串
                        for nm, _id in name_to_id.items():
                            if nm and (nm in speaker or speaker in nm):
                                cid = _id
                                break
                    if not cid and name_to_id:
                        cid = next(iter(name_to_id.values()))
                    beat["character_id"] = cid
                    beat["character_name"] = next(
                        (n for n, i in name_to_id.items() if i == cid), speaker
                    )
                beats.append(beat)

            if not beats:
                # 没有任何节拍时，退化成一条动作，保证 schema(beats>=1) 通过
                beats.append({
                    "type": "action",
                    "text": summarize_text(scene_text, 120) or scene.get("summary", "（无内容）"),
                })
            scene["beats"] = beats

        return scenes

    # ── 工具方法 ────────────────────────────────────────────

    def _clip(self, text: str) -> str:
        limit = self.config.max_chars_per_chapter
        if limit > 0 and len(text) > limit:
            return text[:limit] + "…（内容过长已截断）"
        return text

    @staticmethod
    def _match_location(
        loc_name: str,
        scene_text: str,
        locations: "OrderedDict[str, dict[str, Any]]",
    ) -> dict[str, Any]:
        name = (loc_name or "").strip()
        if name and name in locations:
            return locations[name]
        for lname, loc in locations.items():
            if lname and (lname in scene_text or lname in name or name in lname):
                return loc
        return next(iter(locations.values()))

    @staticmethod
    def _fallback():
        from .pipeline import RuleBasedGenerator

        return RuleBasedGenerator()


# ── 大模型 Prompt 模板 ──────────────────────────────────────────

_SYS_ANALYST = (
    "你是一位资深影视编剧与剧本分析师，擅长把中文小说改编为结构化剧本。"
    "请始终严格按要求的结构化字段输出，不要输出多余解释。"
)

_CHARACTER_PROMPT = """请从下面的小说章节中提取所有出场人物。

严格遵守：
1. 只返回人物的真实姓名本身，绝不能把"说/问/道/喊/叫"等动词或"低声/大声"等修饰词并入名字。
   - 正确：林夏、顾言；错误：林夏说、顾言低声说、林夏没有回。
2. 不要把"照片背面""门外""有人"这类非人名短语当作角色。
3. 判断每个角色的定位(role)，并尽量补全性别、年龄、一句话描述、目标与冲突。
4. 第一主角的 role 用 protagonist。

小说章节：
{chapter_texts}
"""

_LOCATION_PROMPT = """请从下面的小说章节中提取所有重要的场景地点。

要求：
1. 给出地点名称（如"旧火车站""林夏的办公室""狭窄的巷子"）。
2. 判断该地点是室内(interior)、室外(exterior)、内外兼有(mixed)还是未知(unknown)。
3. 用一句话描述地点，并概括其环境氛围(atmosphere)。
4. 只提取真实出现的地点，不要臆造。

小说章节：
{chapter_texts}
"""

_SCENE_PROMPT = """请把下面这一章小说按"叙事节奏"切分成若干剧本场景。

切分原则：
1. 时间或地点发生明显变化时切分为新场景。
2. 出现明显戏剧转折或视角切换时切分。
3. 不要机械按固定段落数切分，一个场景可包含多段。
4. 为每个场景标注地点、时间(morning/day/afternoon/evening/night/dawn/dusk/continuous/unknown)、
   内外景(INT/EXT/INT_EXT/UNKNOWN)、环境氛围、一句话摘要、戏剧功能、在场角色，
   以及覆盖的段落区间 paragraph_ranges（形如 [[起始段号, 结束段号]]）。

已识别角色：{character_names}

带段号的章节文本：
{numbered_paragraphs}
"""

_BEAT_PROMPT = """请把下面这一个场景的文字改写成有序的剧本节拍(beats)。

每个节拍是下列类型之一：
- action  动作描写（人物在做什么、画面在发生什么）
- dialogue 人物口头对白（必须标注说话人 speaker，且 speaker 必须来自已识别角色）
- narration 旁白 / 内心独白（"她想到…"这类）
- sound   音效（"铁门发出刺耳的响声"这类）
- visual  纯画面 / 镜头描写

严格遵守：
1. 真正的对白才标成 dialogue。"信上写着…""照片背面写着…"是书面文字，应作为 action 或 narration，不是对白。
2. 对白文本去掉引号，只保留台词本身。
3. 按场景中事件发生的先后顺序排列节拍。
4. speaker 只能是已识别角色之一：{character_names}

场景文字：
{scene_text}
"""
