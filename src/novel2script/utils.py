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

    支持中文「第X章/节/回」、英文「Chapter N」标题；
    若没有任何章节标题，则按连续空行粗略切分。
    返回形如 ``[{"chapter_number": 1, "title": "第一章 ...", "text": "..."}]``。
    """
    text = raw_text.strip()
    if not text:
        return []

    pattern = re.compile(
        r"(?m)^\s*("
        r"(?:第\s*[0-9一二三四五六七八九十百千两]+\s*[章节回幕])"
        r"|(?:Chapter\s+\d+)|(?:CHAPTER\s+\d+)"
        r")\s*(.*)$"
    )
    matches = list(pattern.finditer(text))

    chapters: list[dict[str, object]] = []
    if matches:
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            title_prefix = match.group(1).strip()
            title_rest = match.group(2).strip()
            title = f"{title_prefix} {title_rest}".strip()
            body = text[start:end].strip()
            number = idx + 1
            if body:
                chapters.append(
                    {"chapter_number": number, "title": title or f"第{number}章", "text": body}
                )
    else:
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
