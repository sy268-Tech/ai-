from pathlib import Path

from novel2script.pipeline import RuleBasedGenerator, parse_novel_input
from novel2script.models import ConvertOptions
from novel2script.service import build_novel_from_text, convert_novel, convert_text
from novel2script.renderer import render_readable_script
from novel2script.utils import split_chapters
from novel2script.validators import validate_screenplay
from novel2script.yaml_io import load_yaml_or_json


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "screenplay.schema.yaml"

SAMPLE_TEXT = """第一章 旧站台
夜色落下时，林夏来到废弃的火车站。站台上全是雾。

林夏说：“是谁让我来这里？”

一阵风吹过，候车厅的铁门发出刺耳的响声。

第二章 匿名信
第二天上午，林夏回到办公室。桌上多了一封没有署名的信。

顾言问：“你脸色怎么这么差？”

林夏没有回答。

第三章 夜访
深夜，林夏来到一条狭窄的巷子。巷子尽头有一间亮着灯的旧屋。

顾言低声说：“我们可能被人跟踪了。”
"""


def test_convert_example_and_validate():
    data = load_yaml_or_json(ROOT / "examples" / "novel_input.yaml")
    novel = parse_novel_input(data)
    screenplay = RuleBasedGenerator().generate(novel, ConvertOptions())
    result = validate_screenplay(screenplay, SCHEMA)

    assert result.ok, result.errors
    assert screenplay["schema_version"] == "1.0"
    assert len(screenplay["script"]["source"]["adapted_chapters"]) >= 3
    assert len(screenplay["script"]["scenes"]) >= 1


def test_requires_three_chapters():
    data = {
        "novel": {
            "title": "测试",
            "chapters": [
                {"chapter_number": 1, "title": "一", "text": "第一章内容"},
                {"chapter_number": 2, "title": "二", "text": "第二章内容"},
            ],
        }
    }

    try:
        parse_novel_input(data)
    except ValueError as exc:
        assert "At least 3 chapters" in str(exc)
    else:
        raise AssertionError("Expected ValueError for fewer than 3 chapters")


def test_split_chapters_from_text():
    chapters = split_chapters(SAMPLE_TEXT)
    assert len(chapters) == 3
    assert chapters[0]["chapter_number"] == 1
    assert "旧站台" in chapters[0]["title"]


def test_build_novel_from_text_min_chapters():
    try:
        build_novel_from_text("第一章\n只有一章", title="x")
    except ValueError as exc:
        assert "至少需要" in str(exc)
    else:
        raise AssertionError("Expected ValueError for fewer than 3 chapters")


def test_convert_text_rule_based_validates():
    """无 API Key 时走规则引擎，输出应通过 schema 校验且无占位符。"""
    res = convert_text(SAMPLE_TEXT, title="雾城来信", author="示例作者", prefer_llm=False)
    assert res.used_llm is False
    result = validate_screenplay(res.screenplay, SCHEMA)
    assert result.ok, result.errors

    # 不得出现"待作者确认"类占位标识
    for marker in ("待作者确认", "需作者进一步确认", "待确认"):
        assert marker not in res.yaml_text
        assert marker not in res.readable_text


def test_readable_script_has_labels():
    """可读剧本应标注角色、对话、环境。"""
    res = convert_text(SAMPLE_TEXT, title="雾城来信", prefer_llm=False)
    text = res.readable_text
    assert "【角色表】" in text
    assert "【对话】" in text
    assert "【环境】" in text
    # 对白应正确归属说话人
    assert "林夏：" in text


def test_convert_novel_falls_back_without_key(monkeypatch):
    """prefer_llm=True 但未配置 key 时，应安全回退规则引擎。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    novel = build_novel_from_text(SAMPLE_TEXT, title="x", author="y")
    screenplay, used_llm = convert_novel(novel, prefer_llm=True)
    assert used_llm is False
    assert validate_screenplay(screenplay, SCHEMA).ok
