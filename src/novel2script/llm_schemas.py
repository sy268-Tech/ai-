"""大模型结构化输出的 Pydantic 模型。

这些模型用于 LangChain 的 ``with_structured_output``，约束大模型
必须按既定字段返回 JSON，从而避免解析自由文本的脆弱性。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LLMCharacter(BaseModel):
    """大模型识别出的单个角色。"""

    name: str = Field(description="角色的真实姓名，只要名字本身，不含'说/问/道'等动词")
    role: str = Field(
        default="supporting",
        description="角色定位：protagonist/antagonist/supporting/mentor/love_interest/comic_relief/minor",
    )
    gender: str = Field(default="", description="性别：male/female/unknown，未知留空")
    age: str = Field(default="", description="年龄或年龄段，未知留空")
    description: str = Field(default="", description="一句话刻画角色身份与性格特征")
    goal: str = Field(default="", description="角色在故事中的核心目标或动机")
    conflict: str = Field(default="", description="角色面临的主要矛盾冲突")


class LLMCharacterList(BaseModel):
    characters: List[LLMCharacter] = Field(default_factory=list)


class LLMLocation(BaseModel):
    """大模型识别出的单个场景地点。"""

    name: str = Field(description="地点名称，如'旧火车站''林夏的办公室'")
    type: str = Field(
        default="unknown",
        description="地点类型：interior(室内)/exterior(室外)/mixed(内外兼有)/unknown",
    )
    description: str = Field(default="", description="一句话描述该地点")
    atmosphere: str = Field(default="", description="该地点的氛围基调，如'阴冷、压抑'")


class LLMLocationList(BaseModel):
    locations: List[LLMLocation] = Field(default_factory=list)


class LLMScene(BaseModel):
    """大模型按叙事节奏切分出的单个场景。"""

    location: str = Field(default="", description="本场景发生的地点名（尽量匹配已知地点）")
    time_of_day: str = Field(
        default="unknown",
        description="时间：morning/day/afternoon/evening/night/dawn/dusk/continuous/unknown",
    )
    interior_exterior: str = Field(
        default="UNKNOWN", description="内外景：INT(室内)/EXT(室外)/INT_EXT/UNKNOWN"
    )
    atmosphere: str = Field(default="", description="本场景的环境氛围，一句话")
    summary: str = Field(description="一句话概括本场景内容")
    dramatic_function: str = Field(default="推进剧情", description="本场在剧作结构中的功能")
    characters_present: List[str] = Field(
        default_factory=list, description="本场景中在场的角色名列表"
    )
    paragraph_ranges: List[List[int]] = Field(
        default_factory=list,
        description="本场景覆盖的段落区间，形如 [[起始段号, 结束段号]]",
    )


class LLMSceneList(BaseModel):
    scenes: List[LLMScene] = Field(default_factory=list)


class LLMChapterSegment(BaseModel):
    """大模型识别出的单个章节/段落边界。"""

    title: str = Field(description="章节标题，若原文无标题则自行根据内容概括一个简短标题")
    start_line: int = Field(description="该章节在带行号文本中的起始行号（从1开始）")
    end_line: int = Field(description="该章节在带行号文本中的结束行号（包含）")


class LLMChapterSegmentList(BaseModel):
    """大模型对整段文本的章节切分结果。"""

    chapters: List[LLMChapterSegment] = Field(
        default_factory=list,
        description="按顺序排列的章节列表，每个章节标明起止行号",
    )


class LLMBeat(BaseModel):
    """大模型从一个场景中提炼出的单个剧本节拍 (beat)。"""

    type: str = Field(
        description="节拍类型：action(动作)/dialogue(对白)/narration(旁白)/sound(音效)/visual(画面)"
    )
    speaker: str = Field(
        default="",
        description="当 type=dialogue 时，说话角色的名字（必须来自已知角色列表）",
    )
    text: str = Field(description="节拍的具体内容；对白请去掉引号只保留台词")


class LLMBeatList(BaseModel):
    beats: List[LLMBeat] = Field(default_factory=list)
