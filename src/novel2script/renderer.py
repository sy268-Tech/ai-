"""把结构化剧本渲染成「美观直白」的可读文本。

需求要求：生成时要**标注出角色、对话和环境**，让格式更直观。

YAML 是机器可读的结构化产物；本模块在其之上额外提供一份人类可读的剧本视图，
用清晰的中文小节标题分别标注【环境】【角色】【对话/动作/旁白/音效】，
方便作者快速通读初稿。
"""

from __future__ import annotations

from typing import Any


# 节拍类型 → 中文标签
_BEAT_LABELS = {
    "dialogue": "对话",
    "action": "动作",
    "narration": "旁白",
    "sound": "音效",
    "visual": "画面",
    "pause": "停顿",
    "insert": "插入",
}

_TIME_LABELS = {
    "morning": "清晨", "day": "白天", "afternoon": "下午", "evening": "傍晚",
    "night": "夜晚", "dawn": "黎明", "dusk": "黄昏",
    "continuous": "承接上场", "unknown": "时间不限",
}

_IE_LABELS = {"INT": "室内", "EXT": "室外", "INT_EXT": "内外景", "UNKNOWN": "未标注"}

_ROLE_LABELS = {
    "protagonist": "主角", "antagonist": "反派", "supporting": "配角",
    "mentor": "导师", "love_interest": "情感线", "comic_relief": "喜剧调剂",
    "minor": "次要", "unknown": "待定",
}

_LOC_TYPE_LABELS = {
    "interior": "室内", "exterior": "室外", "mixed": "内外兼有", "unknown": "未标注",
}


def _hr(char: str = "─", width: int = 60) -> str:
    return char * width


def render_readable_script(screenplay: dict[str, Any]) -> str:
    """把剧本 dict 渲染成带【环境】【角色】【对话】标注的可读文本。"""
    script = screenplay.get("script", {})
    lines: list[str] = []

    title = script.get("title", "未命名剧本")
    fmt = script.get("format", "")
    lines.append(_hr("═"))
    lines.append(f"  《{title}》  剧本初稿（{fmt}）")
    lines.append(_hr("═"))

    logline = script.get("logline", "")
    if logline:
        lines.append(f"一句话故事：{logline}")
    synopsis = script.get("synopsis", "")
    if synopsis:
        lines.append(f"剧情梗概：{synopsis}")
    source = script.get("source", {})
    if source:
        chapters = source.get("adapted_chapters", [])
        author = source.get("author", "")
        meta = f"改编自《{source.get('novel_title', title)}》"
        if author:
            meta += f"（作者：{author}）"
        if chapters:
            meta += f"，覆盖第 {', '.join(str(c) for c in chapters)} 章"
        lines.append(meta)
    lines.append("")

    # ── 角色表 ──────────────────────────────────────────
    characters = script.get("characters", [])
    id_to_name = {c.get("id"): c.get("name", "") for c in characters}
    lines.append(_hr())
    lines.append("【角色表】")
    lines.append(_hr())
    for c in characters:
        role = _ROLE_LABELS.get(c.get("role", ""), c.get("role", ""))
        head = f"  ● {c.get('name', '')}（{role}）"
        extra = []
        if c.get("gender"):
            extra.append(c["gender"])
        if c.get("age"):
            extra.append(str(c["age"]))
        if extra:
            head += f"  [{' / '.join(extra)}]"
        lines.append(head)
        if c.get("description"):
            lines.append(f"      简介：{c['description']}")
        if c.get("goal"):
            lines.append(f"      目标：{c['goal']}")
        if c.get("conflict"):
            lines.append(f"      冲突：{c['conflict']}")
    lines.append("")

    # ── 地点表 ──────────────────────────────────────────
    locations = script.get("locations", [])
    lines.append(_hr())
    lines.append("【地点表】")
    lines.append(_hr())
    for loc in locations:
        ltype = _LOC_TYPE_LABELS.get(loc.get("type", ""), loc.get("type", ""))
        line = f"  ◆ {loc.get('name', '')}（{ltype}）"
        if loc.get("atmosphere"):
            line += f"  氛围：{loc['atmosphere']}"
        lines.append(line)
        if loc.get("description"):
            lines.append(f"      {loc['description']}")
    lines.append("")

    # ── 分场正文 ────────────────────────────────────────
    scenes = script.get("scenes", [])
    lines.append(_hr())
    lines.append(f"【正文】共 {len(scenes)} 场")
    lines.append(_hr())
    lines.append("")

    for scene in scenes:
        heading = scene.get("heading", {})
        loc_name = heading.get("location_name") or id_to_name_loc(locations, heading.get("location_id"))
        ie = _IE_LABELS.get(heading.get("interior_exterior", ""), "")
        tod = _TIME_LABELS.get(heading.get("time_of_day", ""), "")

        no = scene.get("scene_number", "?")
        # 环境标注行：场号 + 内外景 + 地点 + 时间
        env = f"第 {no} 场　{ie}　{loc_name}　{tod}".strip()
        lines.append(f"◇ {env}")
        if heading.get("atmosphere"):
            lines.append(f"  【环境】氛围：{heading['atmosphere']}")
        if scene.get("dramatic_function"):
            lines.append(f"  【环境】戏剧功能：{scene['dramatic_function']}")
        if scene.get("summary"):
            lines.append(f"  【环境】本场概要：{scene['summary']}")

        present = [id_to_name.get(cid, cid) for cid in scene.get("characters", [])]
        if present:
            lines.append(f"  【角色】在场：{'、'.join(present)}")
        lines.append("")

        for beat in scene.get("beats", []):
            btype = beat.get("type", "action")
            text = beat.get("text", "")
            if btype == "dialogue":
                speaker = beat.get("character_name") or id_to_name.get(
                    beat.get("character_id"), "角色"
                )
                lines.append(f"    【对话】{speaker}：{text}")
            else:
                label = _BEAT_LABELS.get(btype, btype)
                lines.append(f"    （{label}）{text}")
        if scene.get("transition") and scene["transition"] != "NONE":
            lines.append(f"    〔转场：{scene['transition']}〕")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def id_to_name_loc(locations: list[dict[str, Any]], loc_id: str | None) -> str:
    for loc in locations:
        if loc.get("id") == loc_id:
            return loc.get("name", "")
    return ""
