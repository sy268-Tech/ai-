from __future__ import annotations

import re
from hashlib import md5


def slugify_id(prefix: str, value: str) -> str:
    raw = re.sub(r"\W+", "_", value.strip(), flags=re.UNICODE).strip("_")
    if not raw:
        raw = md5(value.encode("utf-8")).hexdigest()[:8]
    # Chinese characters are allowed in YAML but less convenient for references.
    # Use a short hash suffix to keep ids stable and ASCII-friendly.
    suffix = md5(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{suffix}"


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n|(?<=[。！？!?])\s+", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def split_chapters(raw_text: str) -> list[dict[str, object]]:
    """把整段小说文本拆分成章节列表。

    支持多种章节标题格式：
    - 中文：第X章/节/回/幕、场景X、片段X
    - 英文：Chapter N、Part N、Scene N、Act N
    - 编号式：Chat1、chat 2、ep1、EP01
    - 纯数字序号行：独占一行的 "1." "2." "3."（后可跟标题）
    - 分隔线：--- 或 === 独占一行（至少三个连续符号）

    若没有任何章节标题，则按连续空行粗略切分。
    返回形如 ``[{"chapter_number": 1, "title": "第一章 ...", "text": "..."}]``。
    """
    text = raw_text.strip()
    if not text:
        return []

    # 按优先级尝试多种分割模式
    patterns = [
        # 中文章节：第X章/节/回/幕
        re.compile(
            r"(?m)^\s*(第\s*[0-9一二三四五六七八九十百千两]+\s*[章节回幕])\s*(.*)$"
        ),
        # 中文场景/片段/段落
        re.compile(
            r"(?m)^\s*((?:场景|片段|段落|篇章)\s*[0-9一二三四五六七八九十百千两]+)\s*(.*)$"
        ),
        # 英文 Chapter/Part/Scene/Act/Episode
        re.compile(
            r"(?mi)^\s*((?:Chapter|Part|Scene|Act|Episode)\s+\d+)\s*(.*)$"
        ),
        # Chat/chat/EP/ep 加数字（紧凑或空格分隔）
        re.compile(
            r"(?mi)^\s*((?:Chat|chat|EP|ep|Ep)\s*\d+)\s*(.*)$"
        ),
        # 纯数字序号行：1. / 2. / 3.（独占行首，后可跟标题文字）
        re.compile(
            r"(?m)^\s*(\d+)\.\s+(.+)$"
        ),
        # 分隔线模式：---、===、***（至少三个连续符号独占一行）
        re.compile(
            r"(?m)^(\s*[-=*]{3,})\s*()$"
        ),
    ]

    chapters: list[dict[str, object]] = []

    for pat in patterns:
        matches = list(pat.finditer(text))
        if len(matches) >= 2:  # 至少匹配到两个才算有效分割
            # 分隔线模式特殊处理：分隔线本身不作为标题
            is_separator = pat.pattern.startswith(r"(?m)^(\s*[-=*]")
            for idx, match in enumerate(matches):
                start = match.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
                body = text[start:end].strip()
                number = idx + 1

                if is_separator:
                    title = f"第{number}章"
                else:
                    title_prefix = match.group(1).strip()
                    title_rest = match.group(2).strip()
                    title = f"{title_prefix} {title_rest}".strip() if title_rest else title_prefix

                if body:
                    chapters.append(
                        {"chapter_number": number, "title": title or f"第{number}章", "text": body}
                    )

            # 处理分隔线模式时，第一个分隔线之前的内容也应作为一章
            if is_separator and matches:
                first_body = text[: matches[0].start()].strip()
                if first_body:
                    # 插入到列表最前面，重新编号
                    chapters.insert(0, {"chapter_number": 0, "title": "第0章", "text": first_body})
                    for i, ch in enumerate(chapters):
                        ch["chapter_number"] = i + 1
                        if ch["title"].startswith("第") and ch["title"][-1] == "章":
                            ch["title"] = f"第{i + 1}章"

            if chapters:
                return chapters

    # 兜底：按连续空行切分
    parts = [p.strip() for p in re.split(r"\n\s*\n\s*\n+", text) if p.strip()]
    for idx, part in enumerate(parts, start=1):
        chapters.append(
            {"chapter_number": idx, "title": f"第{idx}章", "text": part}
        )

    return chapters


def chunk_list(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i:i + size] for i in range(0, len(items), size)]


def looks_like_dialogue(text: str) -> bool:
    return bool(re.search(r"[“\"].+?[”\"]", text)) or "：" in text or ":" in text


def extract_dialogue_text(text: str) -> list[str]:
    """从文本中提取对白内容，自动去重。

    对于"林夏说：\\"你好\\""这类同时包含引号和冒号的句子，
    只保留一份对白内容，避免生成重复 beat。
    """
    # 提取引号内的对白
    quoted = []
    for m in re.finditer(r"[「『“\"](.+?)[」』”\"]", text):
        quoted.append(m.group(1).strip())

    # 提取冒号后的对白，并去除两端可能残留的引号
    colon = []
    # 匹配冒号后到句末或字符串末尾的内容（包含问号、感叹号）
    for m in re.finditer(r"[:：]\s*(.+?)(?:\s*$|\s*[。！!\n]|$)", text):
        raw = m.group(1).strip()
        # 去掉两端引号
        clean = raw.strip("「」『』\"\"''“”‘’")
        if clean:
            colon.append(clean)

    # 去重：按清理后的文本比较（同时去掉引号和句末标点后比较）
    def _normalize(s: str) -> str:
        s = s.strip("「」『』\"\"''“”‘’").strip()
        return s.rstrip("。！？!?")

    # 选择最佳版本：优先保留带标点的（更完整）
    seen: set[str] = set()
    candidate: dict[str, str] = {}  # normalized -> best original
    for x in quoted + colon:
        key = _normalize(x)
        if key and key not in seen:
            seen.add(key)
            candidate[key] = x
        elif key and len(x) > len(candidate.get(key, "")):
            # 保留更长的版本（通常包含标点，更完整）
            candidate[key] = x
    return list(candidate.values())


def guess_time_of_day(text: str) -> str:
    mapping = {
        "凌晨": "dawn",
        "清晨": "morning",
        "早晨": "morning",
        "上午": "morning",
        "中午": "day",
        "下午": "afternoon",
        "傍晚": "dusk",
        "黄昏": "dusk",
        "晚上": "night",
        "夜": "night",
        "深夜": "night",
    }
    for key, value in mapping.items():
        if key in text:
            return value
    return "unknown"


def guess_interior_exterior(text: str) -> str:
    exterior_words = ["街", "路", "桥", "广场", "站台", "森林", "山", "海", "门外", "院子", "操场"]
    interior_words = ["房间", "屋", "室", "大厅", "办公室", "教室", "车厢", "店里", "门内", "走廊"]
    if any(w in text for w in exterior_words):
        return "EXT"
    if any(w in text for w in interior_words):
        return "INT"
    return "UNKNOWN"


def summarize_text(text: str, max_len: int = 80) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1] + "…"


def split_chapters_with_llm(raw_text: str, config=None) -> list[dict[str, object]]:
    """当正则无法识别章节时，调用大模型智能切分文本。

    大模型会根据叙事节奏、时间跳跃、场景转换等语义信息来判断章节边界，
    从而支持任意用户自定义的分割方式。

    参数:
        raw_text: 原始小说文本
        config: LLMConfig 实例，为 None 时从环境变量读取

    返回:
        与 split_chapters 相同格式的章节列表，失败时返回空列表。
    """
    from .config import LLMConfig

    cfg = config or LLMConfig.from_env()
    if not cfg.is_configured:
        return []

    text = raw_text.strip()
    if not text:
        return []

    # 为文本加上行号，方便大模型标注边界
    lines = text.split("\n")
    numbered_text = "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(lines))

    # 截断过长文本，避免超出 token 上限
    max_chars = cfg.max_chars_per_chapter * 5  # 允许更大范围
    if len(numbered_text) > max_chars:
        numbered_text = numbered_text[:max_chars] + "\n…（后续内容已截断）"

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        from .llm_schemas import LLMChapterSegmentList

        llm = ChatOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
            temperature=0.2,
            max_tokens=cfg.max_tokens,
            timeout=60,
            max_retries=1,
        )
        structured_llm = llm.with_structured_output(
            LLMChapterSegmentList, method="function_calling"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", _LLM_SPLIT_SYSTEM),
            ("human", _LLM_SPLIT_USER),
        ])
        chain = prompt | structured_llm
        result: LLMChapterSegmentList = chain.invoke(
            {"numbered_text": numbered_text, "total_lines": len(lines)}
        )

        chapters: list[dict[str, object]] = []
        for idx, seg in enumerate(result.chapters, start=1):
            start = max(1, seg.start_line) - 1  # 转为 0-based index
            end = min(seg.end_line, len(lines))  # 包含 end_line
            body = "\n".join(lines[start:end]).strip()
            if body:
                chapters.append({
                    "chapter_number": idx,
                    "title": seg.title.strip() or f"第{idx}章",
                    "text": body,
                })

        return chapters

    except Exception:
        return []


_LLM_SPLIT_SYSTEM = (
    "你是一位专业的文本结构分析师。你的任务是把一段小说/故事文本切分成多个章节或段落。"
    "判断依据包括但不限于：时间跳跃、地点转换、视角变化、情节转折、"
    "任何形式的分隔标记（空行、符号、编号等）。"
    "即使原文没有明确的章节标题，也请根据叙事节奏合理切分，每个章节应是一个相对完整的叙事单元。"
    "切分结果至少 3 个章节。"
)

_LLM_SPLIT_USER = """请分析以下带行号的文本，将其切分为多个章节。

要求：
1. 每个章节标注起始行号和结束行号（行号从1开始）。
2. 为每个章节起一个简短标题（概括该段内容）。
3. 章节之间不要有遗漏（所有行都应被覆盖）。
4. 切分结果至少 3 个章节，除非文本确实很短。
5. 总行数为 {total_lines} 行。

带行号的文本：
{numbered_text}
"""
