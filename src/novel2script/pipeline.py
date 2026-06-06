from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from .adapters import ScriptGenerator
from .models import ConvertOptions, NovelChapter, NovelInput, ScreenplayYaml
from .utils import (
    chunk_list,
    extract_dialogue_text,
    guess_interior_exterior,
    guess_time_of_day,
    looks_like_dialogue,
    slugify_id,
    split_paragraphs,
    summarize_text,
)


COMMON_LOCATION_HINTS = [
    "火车站", "车站", "站台", "办公室", "学校", "教室", "医院", "病房", "家", "客厅", "卧室",
    "街道", "巷子", "咖啡馆", "酒吧", "餐厅", "森林", "山路", "码头", "仓库", "警局", "公司",
]


# ── 角色识别：对白动词 / 冒号模式 ──────────────────────────────
# 将"说话动词"按长度降序排列，保证 regex 优先匹配多字动词（如"低声说"），
# 避免将副词"低声"误判为人名的一部分。
_SPEECH_VERBS = "|".join([
    # 修饰 + 说 / 道
    "低声说", "大声说", "轻声说", "小声说", "笑着说", "冷冷说", "淡淡说",
    "温柔地说", "生气地说", "惊讶地说", "平静地说", "严肃地说",
    "好奇地问", "认真地问道", "郑重地说", "激动地说", "喃喃道",
    "吼道", "叫道", "问道", "答道", "说道", "喊道", "回答道",
    "追问道", "反问道", "开口道", "解释道", "补充道", "继续说",
    "接着说", "又道", "反问", "追问", "回答", "开口", "补充", "解释",
    # 单字动词（放在最后，优先匹配上面的多字组合）
    "说", "问", "道", "喊", "叫",
])

# Pattern 1: 名字 + 说话动词 + 冒号  例："林夏说：" → 林夏 / "顾言低声说：" → 顾言
# Pattern 2: 名字 + 说话动词（无冒号）  例："林夏说" / "林夏低声说"
# Pattern 3: 名字 + 裸冒号（无说话动词，低置信度）  例："林夏："
#
# 每个 pattern 都带有 (?<![一-龥]) 前瞻，确保名字前面不是另一个汉字，
# 避免将 "钥匙，说："误识别为角色"匙"，或将 "他只是低声说："误识别为角色"是"。
# 仅用于无冒号模式（Pattern 1）的说话动词——不含单字"道""喊""叫"，
# 因为这些单字在没有冒号时几乎都是非对白用法（如"知道""名叫""叫来"）。
_SPEECH_VERBS_NO_COLON = "|".join([
    "低声说", "大声说", "轻声说", "小声说", "笑着说", "冷冷说", "淡淡说",
    "温柔地说", "生气地说", "惊讶地说", "平静地说", "严肃地说",
    "好奇地问", "认真地问道", "郑重地说", "激动地说", "喃喃道",
    "吼道", "叫道", "问道", "答道", "说道", "喊道", "回答道",
    "追问道", "反问道", "开口道", "解释道", "补充道", "继续说",
    "接着说", "又道", "反问", "追问", "回答", "开口", "补充", "解释",
    "说", "问",  # 仅保留最不易误判的两个单字
])

SPEAKER_PATTERNS = [
    # 高置信度：名 + 动 + 冒号
    re.compile(r"(?<![一-龥])([一-龥A-Za-z0-9_]{1,6}?)(" + _SPEECH_VERBS + r")[:：]"),
    # 高置信度：名 + 动（无冒号）—— 使用受限动词表，避免"知道""名叫"等误判
    re.compile(r"(?<![一-龥])([一-龥A-Za-z0-9_]{1,6}?)(" + _SPEECH_VERBS_NO_COLON + r")"),
    # 低置信度：名 + 裸冒号
    re.compile(r"(?<![一-龥])([一-龥A-Za-z0-9_]{1,6})[:：]"),
]


def parse_novel_input(data: dict[str, Any]) -> NovelInput:
    if "novel" not in data or not isinstance(data["novel"], dict):
        raise ValueError("Input must contain a top-level 'novel' object.")

    raw = data["novel"]
    chapters_raw = raw.get("chapters", [])
    if not isinstance(chapters_raw, list):
        raise ValueError("'novel.chapters' must be a list.")
    if len(chapters_raw) < 1:
        raise ValueError("At least 1 chapter is required.")

    chapters: list[NovelChapter] = []
    for item in chapters_raw:
        chapter_number = int(item.get("chapter_number"))
        title = str(item.get("title", f"第{chapter_number}章"))
        text = str(item.get("text", "")).strip()
        if not text:
            raise ValueError(f"Chapter {chapter_number} text cannot be empty.")
        chapters.append(NovelChapter(chapter_number=chapter_number, title=title, text=text))

    return NovelInput(
        title=str(raw.get("title", "")).strip() or "未命名剧本",
        author=raw.get("author"),
        format=raw.get("format", "web_series"),
        language=raw.get("language", "zh-CN"),
        genre=list(raw.get("genre", [])),
        chapters=chapters,
    )


class RuleBasedGenerator(ScriptGenerator):
    """轻量规则版小说转剧本生成器。

    它不是为了替代专业改编，而是为了提供一个可运行、可扩展的项目骨架。
    """

    def generate(self, novel: NovelInput, options: ConvertOptions) -> ScreenplayYaml:
        character_map = self._extract_characters(novel)
        location_map = self._extract_locations(novel)

        if not character_map:
            character_map["叙事主角"] = {
                "id": "char_main",
                "name": "叙事主角",
                "role": "protagonist",
                "description": "从小说叙述中推断出的主要人物，可由作者补充姓名。",
                "source_chapters": [c.chapter_number for c in novel.chapters],
            }

        if not location_map:
            location_map["未明确地点"] = {
                "id": "loc_unspecified",
                "name": "未明确地点",
                "type": "unknown",
                "description": "原文未明确交代具体地点，可由作者补充。",
                "atmosphere": "",
                "source_chapters": [c.chapter_number for c in novel.chapters],
            }

        scenes = self._build_scenes(novel, character_map, location_map, options)

        screenplay: ScreenplayYaml = {
            "schema_version": "1.0",
            "script": {
                "title": novel.title,
                "format": novel.format or options.default_format,
                "language": novel.language,
                "genre": novel.genre,
                "logline": self._make_logline(novel),
                "synopsis": self._make_synopsis(novel),
                "source": {
                    "novel_title": novel.title,
                    "author": novel.author or "",
                    "adapted_chapters": [c.chapter_number for c in novel.chapters],
                    "source_note": "由 Novel2Script AI 根据小说章节自动生成的剧本初稿。",
                },
                "metadata": {
                    "draft_type": "ai_first_draft",
                    "generator": "RuleBasedGenerator",
                    "warning": "规则生成结果仅作为可编辑初稿，建议作者继续打磨。",
                },
                "characters": list(character_map.values()),
                "locations": list(location_map.values()),
                "scenes": scenes,
                "notes": [
                    "请检查人物目标、动机、对白口吻和场景节奏。",
                    "如果接入大模型，可在 adapters.py 中替换生成器以提升改编质量。",
                ],
            },
        }
        return screenplay

    def _extract_characters(self, novel: NovelInput) -> OrderedDict[str, dict[str, Any]]:
        names: OrderedDict[str, set[int]] = OrderedDict()

        for chapter in novel.chapters:
            text = chapter.text
            # 高置信度：有说话动词（Pattern 0, 1）
            for pattern in SPEAKER_PATTERNS[:2]:
                for match in pattern.finditer(text):
                    name = match.group(1).strip()
                    if self._is_probable_name(name, high_confidence=True):
                        names.setdefault(name, set()).add(chapter.chapter_number)

            # 低置信度：裸冒号（Pattern 2）
            for match in SPEAKER_PATTERNS[2].finditer(text):
                name = match.group(1).strip()
                if self._is_probable_name(name, high_confidence=False):
                    names.setdefault(name, set()).add(chapter.chapter_number)

        # 合并名称：把"林夏说"、 "顾言低声"等合并到真正的名字"林夏"、 "顾言"
        names = self._merge_names(names)

        # 回退：若对白模式提取不到足够角色（< 2），扫描全文中的高频疑似人名
        if len(names) < 2:
            names = self._extract_names_from_narrative(novel, names)

        result: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for idx, (name, chapters) in enumerate(names.items()):
            role = "protagonist" if idx == 0 else "supporting"
            result[name] = {
                "id": slugify_id("char", name),
                "name": name,
                "role": role,
                "age": "",
                "gender": "",
                "description": f"从原文对白或动作中识别出的人物：{name}。",
                "goal": "",
                "conflict": "",
                "relationships": [],
                "source_chapters": sorted(chapters),
            }
        return result

    def _extract_locations(self, novel: NovelInput) -> OrderedDict[str, dict[str, Any]]:
        found: OrderedDict[str, set[int]] = OrderedDict()
        for chapter in novel.chapters:
            for hint in COMMON_LOCATION_HINTS:
                if hint in chapter.text:
                    found.setdefault(hint, set()).add(chapter.chapter_number)

        result: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for name, chapters in found.items():
            combined = " ".join(
                c.text for c in novel.chapters if c.chapter_number in chapters
            )
            ie = guess_interior_exterior(combined)
            loc_type = {
                "INT": "interior",
                "EXT": "exterior",
                "UNKNOWN": "unknown",
                "INT_EXT": "mixed",
            }.get(ie, "unknown")
            result[name] = {
                "id": slugify_id("loc", name),
                "name": name,
                "type": loc_type,
                "description": f"从小说章节中识别出的地点：{name}。",
                "atmosphere": self._guess_atmosphere(combined),
                "source_chapters": sorted(chapters),
            }
        return result

    def _build_scenes(
        self,
        novel: NovelInput,
        character_map: OrderedDict[str, dict[str, Any]],
        location_map: OrderedDict[str, dict[str, Any]],
        options: ConvertOptions,
    ) -> list[dict[str, Any]]:
        scenes: list[dict[str, Any]] = []
        scene_no = 1

        for chapter in novel.chapters:
            paragraphs = split_paragraphs(chapter.text)
            if not paragraphs:
                continue

            chunks = chunk_list(paragraphs, options.max_paragraphs_per_scene)
            for chunk in chunks:
                scene_text = "\n".join(chunk)
                location = self._choose_location(scene_text, location_map)
                scene_characters = self._choose_characters(scene_text, character_map)
                beats = self._paragraphs_to_beats(chunk, character_map, options)

                scene = {
                    "id": f"scene_{scene_no:03d}",
                    "scene_number": scene_no,
                    "source_chapters": [chapter.chapter_number],
                    "heading": {
                        "location_id": location["id"],
                        "location_name": location["name"],
                        "time_of_day": guess_time_of_day(scene_text),
                        "interior_exterior": guess_interior_exterior(scene_text),
                        "atmosphere": location.get("atmosphere", ""),
                    },
                    "dramatic_function": self._guess_dramatic_function(scene_no, len(scenes), chapter),
                    "summary": summarize_text(scene_text, 100),
                    "characters": [c["id"] for c in scene_characters],
                    "beats": beats,
                    "transition": "CUT_TO",
                    "notes": [
                        f"来源：第{chapter.chapter_number}章《{chapter.title}》。",
                    ],
                }
                scenes.append(scene)
                scene_no += 1

        return scenes

    def _paragraphs_to_beats(
        self,
        paragraphs: list[str],
        character_map: OrderedDict[str, dict[str, Any]],
        options: ConvertOptions,
    ) -> list[dict[str, Any]]:
        beats: list[dict[str, Any]] = []
        for para in paragraphs:
            beat_base: dict[str, Any] = {}
            if options.keep_source_refs:
                beat_base["source_text_ref"] = summarize_text(para, 120)

            # 先检查对白（避免"低声说"中的"声"被误判为音效）
            if looks_like_dialogue(para):
                dialogues = extract_dialogue_text(para)
                speaker = self._guess_speaker(para, character_map)
                if dialogues:
                    for line in dialogues:
                        beat = {
                            "type": "dialogue",
                            "character_id": speaker["id"],
                            "character_name": speaker["name"],
                            "text": line,
                            **beat_base,
                        }
                        beats.append(beat)
                else:
                    beats.append({
                        "type": "dialogue",
                        "character_id": speaker["id"],
                        "character_name": speaker["name"],
                        "text": summarize_text(para, 120),
                        **beat_base,
                    })
                continue

            if any(key in para for key in ["想到", "觉得", "意识到", "明白", "回忆"]):
                beats.append({"type": "narration", "text": summarize_text(para, 120), **beat_base})
                continue

            # 音效检测：包含明显音效关键词，但排除"低声说/大声说"等对白修饰
            if self._is_sound_effect(para):
                beats.append({"type": "sound", "text": summarize_text(para, 120), **beat_base})
                continue

            beats.append({"type": "action", "text": summarize_text(para, 120), **beat_base})

        return beats

    def _choose_location(
        self,
        scene_text: str,
        location_map: OrderedDict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        for name, loc in location_map.items():
            if name in scene_text:
                return loc
        return next(iter(location_map.values()))

    def _choose_characters(
        self,
        scene_text: str,
        character_map: OrderedDict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = [c for name, c in character_map.items() if name in scene_text]
        if result:
            return result
        return [next(iter(character_map.values()))]

    def _guess_speaker(
        self,
        text: str,
        character_map: OrderedDict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """推断一段对白的说话人。

        优先使用说话动词模式匹配（例如"顾言说" → 顾言），
        其次查找文本中出现的角色名（短名优先，因为短名更精确），
        最后回退到第一个角色。
        """
        # 高置信度：用说话动词模式定位说话人
        for pattern in SPEAKER_PATTERNS[:2]:
            match = pattern.search(text)
            if match:
                speaker_name = match.group(1).strip()
                # 在角色表中查找匹配（优先精确匹配）
                for name, char in character_map.items():
                    if name == speaker_name:
                        return char
                # 如果捕获的名字是已知角色名的子串，也算匹配
                for name, char in character_map.items():
                    if speaker_name in name or name in speaker_name:
                        return char

        # 中置信度：按角色名长度升序（短名优先）查找文本中出现的人物
        sorted_chars = sorted(character_map.items(), key=lambda kv: len(kv[0]))
        for name, char in sorted_chars:
            if name in text:
                return char

        return next(iter(character_map.values()))

    def _is_probable_name(self, name: str, high_confidence: bool = True) -> bool:
        """判断捕获到的字符串是否像一个人名。

        高置信度（有说话动词）时较宽松，低置信度（裸冒号）时更严格。
        """
        # ── 通用黑名单：常见非人名词 ──
        bad_words = {
            "他说", "她说", "有人说", "有人", "什么", "为什么", "如果",
            "但是", "可是", "于是", "然后", "电话", "门外", "声音",
            "时候", "这里", "那里", "自己", "这个", "那个",
            "没有", "不是", "已经", "还是", "只是", "因为", "所以",
            "虽然", "不过", "可以", "知道", "觉得", "看到", "听到",
            "想到", "出来", "起来", "下来", "过来", "过去",
            "忽然", "突然", "这时候", "那时候", "怎么", "这么", "那么",
            "他", "她", "我", "你", "它", "他问", "她说", "我只是",
            "他只是", "她只是", "他只是", "它只是",
            "他低声", "她低声", "他大声", "她大声",
            "他不会", "她不会", "他不", "她不",
            "说", "问", "道", "喊", "叫", "答",
            "只是", "还是", "就是", "不是", "也是", "都是",
            "没有回答", "没有说话", "没有说", "没有回",
            "全都", "全部", "全是",
            "没有人", "没人", "谁",
            "第一", "第二", "第三", "最后",
        }
        if name in bad_words:
            return False

        # ── 长度限制 ──
        if len(name) > 6:
            return False

        # 必须包含至少一个 CJK 或拉丁字母
        if not re.search(r"[一-龥A-Za-z]", name):
            return False

        # ── 不以非人名成分开头 ──
        bad_starts = (
            "照片", "那张", "这张", "那里", "这里", "那边", "这边",
            "桌上", "门外", "门内", "屏幕", "短信", "电话", "那边",
            "候车", "一阵", "一条", "一张", "一把", "一只", "一封",
            "那封", "这封", "那扇", "这扇", "那个", "这个",
            "里面", "外面", "前面", "后面", "上面", "下面",
            "他的", "她的", "你的", "我的", "他们的",
            "所有", "整个", "什么", "每个", "那些", "这些",
            "每次", "每天", "那年", "那天",
            "全都", "全是", "都是", "没人", "谁",
            "抽屉", "箱子", "盒子", "桌子", "椅子",
            # 常见天气/时间
            "夜色", "阳光", "月光", "灯光", "天空", "雪花",
            "雨点", "雨滴", "风声", "雷声",
            # 常见动作/状态（非人名）
            "发现", "看见", "听见", "闻到", "感到", "觉得",
            "她打", "他打", "他看", "她看",
            # 单字代词——任何以代词开头的字符串都不可能是人名
            "他", "她", "它", "我", "你",
        )
        for prefix in bad_starts:
            if name.startswith(prefix) and name != prefix:
                return False

        # ── 不以非人名成分结尾 ──
        bad_endings = (
            "写着", "没有回", "没有回答", "忽然", "突然",
            "来不及", "找不到", "的照片", "的短信",
            "没有说话", "没有说", "没有回", "没有回答",
            "不会", "不敢", "不能", "不想", "不用", "不知",
            "只是", "还是", "就是", "不是", "也是", "都是",
            "已经", "曾经", "还没", "还没",
            "什么", "怎么", "这么", "那么",
            "这里", "那里", "哪里", "那边",
            "一阵", "一下", "一点", "一些",
        )
        for suffix in bad_endings:
            if name.endswith(suffix) and name != suffix:
                return False

        # ── 低置信度（裸冒号）额外校验 ──
        if not high_confidence:
            # 裸冒号容易误抓，只接受像人名长度的字符串
            if len(name) > 4:
                return False
            if re.search(r"\d", name):
                return False
            # 不以说话动词结尾（避免"林夏说"被裸冒号误抓）
            verb_endings = ("说", "问", "道", "喊", "叫", "答")
            for ending in verb_endings:
                if name.endswith(ending) and len(name) > len(ending):
                    return False

        return True

    def _merge_names(self, names: OrderedDict[str, set[int]]) -> OrderedDict[str, set[int]]:
        """把较长名称合并到其所包含的较短名称中。

        例如 "林夏说"、"林夏没有回" 都包含 "林夏" → 合并为一个 "林夏"；
        "顾言低声说"、"顾言问" 都包含 "顾言" → 合并为一个 "顾言"。
        按名称长度从短到长处理，短名称优先保留。
        """
        if len(names) <= 1:
            return names

        # 按长度升序（短名优先）
        sorted_names = sorted(names.keys(), key=lambda n: (len(n), n))
        merged: OrderedDict[str, set[int]] = OrderedDict()

        for name in sorted_names:
            subsumed = False
            for accepted in merged:
                # 短名称是长名称的子串 且 短名至少2字符（避免单字误合并）
                if name != accepted and len(accepted) >= 2 and accepted in name:
                    merged[accepted].update(names[name])
                    subsumed = True
                    break
            if not subsumed:
                merged[name] = names[name].copy()

        return merged

    # 常见中文姓氏（百家姓前 120+），用于从叙述文本中识别角色名
    _COMMON_SURNAMES: set[str] = {
        "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
        "徐", "孙", "马", "胡", "朱", "郭", "何", "罗", "高", "林",
        "郑", "梁", "谢", "唐", "许", "冯", "宋", "韩", "邓", "彭",
        "曹", "曾", "田", "萧", "潘", "袁", "蔡", "蒋", "余", "于",
        "杜", "叶", "程", "魏", "苏", "吕", "丁", "任", "卢", "姚",
        "钟", "姜", "崔", "谭", "陆", "范", "汪", "廖", "石", "金",
        "韦", "贾", "夏", "付", "方", "邹", "熊", "孟", "秦", "阎",
        "薛", "侯", "雷", "白", "龙", "段", "郝", "孔", "邵", "史",
        "毛", "常", "万", "顾", "赖", "武", "康", "贺", "严", "尹",
        "钱", "施", "牛", "洪", "龚", "沈", "乔", "安", "温", "戴",
        "齐", "邱", "莫", "邢", "柳", "蓝", "岳", "樊", "殷", "阮",
    }

    def _extract_names_from_narrative(
        self,
        novel: NovelInput,
        existing: OrderedDict[str, set[int]],
    ) -> OrderedDict[str, set[int]]:
        """从叙述文本中补充识别高频出现的疑似人名（2-3 字、含常见姓氏）。"""
        # 拼接全文
        full_text = "\n".join(c.text for c in novel.chapters)
        # 按章节记录出现位置
        chapter_texts = {c.chapter_number: c.text for c in novel.chapters}

        # 候选：2-3 字序列，首字为常见姓氏，且后一字或多字为 CJK 汉字
        candidates: dict[str, set[int]] = OrderedDict()

        for ch_num, text in chapter_texts.items():
            seen_in_chapter: set[str] = set()
            # 只扫描 2-字窗口——中文小说角色名绝大多数是 2 个字（单姓+单名）
            # 3 字组合误判率太高（容易匹配到常见三字词组）
            for m in re.finditer(r"(?=([一-龥]{2}))", text):
                token = m.group(1)
                if token in seen_in_chapter:
                    continue
                # 首字必须是常见姓氏
                if token[0] not in self._COMMON_SURNAMES:
                    continue
                # 末字不能是常见非人名用字（颜色、方位、虚词等）
                if token[-1] in {
                    "色", "的", "了", "着", "过", "得", "地", "上", "下",
                    "在", "到", "是", "有", "会", "要", "能", "可", "只",
                    "都", "也", "还", "就", "才", "又", "再",
                }:
                    continue
                # 不能匹配已知的非人名词
                if token in {
                    "什么", "怎么", "那里", "这里", "这个", "那个",
                    "不是", "知道", "觉得", "看到", "听到", "发现",
                    "每天", "忽然", "突然", "于是", "然后", "因为", "所以",
                    "已经", "还是", "只是", "但是", "可是", "不过",
                    "没有", "可以", "出来", "起来", "下来", "过来",
                    "有人", "没人", "谁", "所有", "每个", "全部",
                    "但是", "如果", "虽然", "自己", "什么",
                }:
                    continue
                seen_in_chapter.add(token)
                candidates.setdefault(token, set()).add(ch_num)

        # 至少出现在 2 章中，或在同一章中出现 2 次以上
        result: OrderedDict[str, set[int]] = OrderedDict(existing)
        for name, chs in candidates.items():
            if name in result:
                continue
            # 统计总出现次数
            total_occurrences = sum(
                chapter_texts[c].count(name) for c in chs
            )
            if total_occurrences >= 2:
                result[name] = chs

        return result

    def _is_sound_effect(self, text: str) -> bool:
        """检测段落是否为音效描述（而非对白修饰语）。

        避免把"低声说"中的"声"误判为音效。
        """
        # 明确的音效关键词（多字组合，避免单字"声"的误判）
        sound_patterns = [
            "响起", "响声", "铃声", "喇叭声", "汽笛声", "爆炸声", "枪声",
            "敲门", "按门铃", "脚步声", "咳嗽声", "哭声", "笑声刺耳",
            "发出刺耳", "铁门发出", "传来.*声", "声.*传来",
            "砰", "啪", "轰", "咚", "哐",
        ]
        if any(p in text for p in sound_patterns):
            return True

        # "声" 在文本中但不是"低声/大声/轻声/小声/声音"
        if "声" in text:
            # 排除对白修饰词中的"声"
            dialog_adverbs = {"低声", "大声", "轻声", "小声", "出声", "做声", "吱声"}
            for adv in dialog_adverbs:
                text = text.replace(adv, "")
            # 排除常见含"声"的非音效词
            noise_words = {"声音", "声说", "声道"}
            for nw in noise_words:
                text = text.replace(nw, "")
            # 清理后仍含"声" → 可能是音效
            if "声" in text:
                return True

        return False

    def _make_logline(self, novel: NovelInput) -> str:
        first = summarize_text(novel.chapters[0].text, 60)
        return f"围绕《{novel.title}》展开的故事从“{first}”开始，人物被迫面对逐渐升级的冲突。"

    def _make_synopsis(self, novel: NovelInput) -> str:
        chapter_summaries = [
            f"第{c.chapter_number}章：{summarize_text(c.text, 70)}" for c in novel.chapters
        ]
        return " ".join(chapter_summaries)

    def _guess_atmosphere(self, text: str) -> str:
        if any(w in text for w in ["雾", "黑", "冷", "阴", "雨", "血", "失踪"]):
            return "紧张、悬疑"
        if any(w in text for w in ["笑", "阳光", "温暖"]):
            return "明亮、轻松"
        return ""

    def _guess_dramatic_function(
        self,
        scene_no: int,
        existing_count: int,
        chapter: NovelChapter,
    ) -> str:
        if scene_no == 1:
            return "开场，建立人物与悬念"
        if chapter.chapter_number == 1:
            return "铺垫人物关系与故事背景"
        if chapter.chapter_number == 2:
            return "推动事件升级"
        if chapter.chapter_number == 3:
            return "制造转折或揭示新线索"
        return "推进剧情"
