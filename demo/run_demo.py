"""
Demo 脚本 - 展示 Novel2Script AI 核心功能

运行方式：
    python demo/run_demo.py

本脚本自动执行以下演示：
1. 加载示例小说（3章）
2. 使用规则引擎生成剧本
3. 输出结构化 YAML
4. 输出可读剧本（标注角色/对话/环境）
5. 校验输出是否通过 Schema

如配置了 .env 中的 API Key，还会额外演示大模型生成。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# 强制 UTF-8 输出，避免 Windows GBK 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 确保 src 在路径中
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from novel2script import (
    LLMConfig,
    ConvertOptions,
    build_novel_from_text,
    convert_novel,
    convert_text,
    render_readable_script,
)
from novel2script.validators import validate_screenplay
from novel2script.yaml_io import dump_yaml

SCHEMA_PATH = ROOT / "schemas" / "screenplay.schema.yaml"

# ── 示例小说文本 ──────────────────────────────────────────────────

NOVEL_TEXT = """第一章 旧站台
夜色落下时，林夏来到废弃的火车站。站台上全是雾，远处的灯像被水泡过一样模糊。

林夏说："是谁让我来这里？"

一阵风吹过，候车厅的铁门发出刺耳的响声。她握紧手机，屏幕上只有一条陌生短信：午夜十二点，旧站台见。

第二章 匿名信
第二天上午，林夏回到办公室。桌上多了一封没有署名的信，信纸边缘被雨水泡皱。

顾言问："你脸色怎么这么差？"

林夏没有回答。她打开信，里面只有一张旧照片，照片背面写着：别相信你父亲。

第三章 夜访
深夜，林夏按照照片上的地址来到一条狭窄的巷子。巷子尽头有一间亮着灯的旧屋。

门内传来老人咳嗽的声音。林夏刚要敲门，屋里的灯忽然灭了。

顾言低声说："我们可能被人跟踪了。"
"""


def print_separator(title: str = "", char: str = "═", width: int = 70):
    if title:
        padding = (width - len(title) - 2) // 2
        print(f"\n{char * padding} {title} {char * padding}")
    else:
        print(char * width)


def main():
    print_separator("Novel2Script AI - 功能演示", "═")
    print("本工具将 3 章以上小说文本自动转为结构化剧本（YAML 格式）")
    print("技术栈：LangChain + LangGraph + Pydantic 结构化输出")

    # ── 1. 检查配置 ──
    print_separator("1. 环境配置检测")
    config = LLMConfig.from_env()
    print(f"  API Key  : {'✓ 已配置' if config.is_configured else '✗ 未配置（将使用规则引擎）'}")
    print(f"  Base URL : {config.base_url}")
    print(f"  Model    : {config.model}")

    # ── 2. 解析小说 ──
    print_separator("2. 解析小说文本")
    novel = build_novel_from_text(NOVEL_TEXT, title="雾城来信", author="示例作者")
    print(f"  标题：{novel.title}")
    print(f"  作者：{novel.author}")
    print(f"  章节数：{len(novel.chapters)}")
    for ch in novel.chapters:
        print(f"    第{ch.chapter_number}章《{ch.title}》- {len(ch.text)} 字")

    # ── 3. 规则引擎生成 ──
    print_separator("3. 使用规则引擎生成剧本")
    result = convert_text(NOVEL_TEXT, title="雾城来信", author="示例作者", prefer_llm=False)
    print(f"  生成器：{result.generator_name}")
    print(f"  使用大模型：{result.used_llm}")

    script = result.screenplay.get("script", {})
    print(f"  角色数：{len(script.get('characters', []))}")
    print(f"  地点数：{len(script.get('locations', []))}")
    print(f"  场景数：{len(script.get('scenes', []))}")

    # ── 4. Schema 校验 ──
    print_separator("4. Schema 校验")
    vr = validate_screenplay(result.screenplay, SCHEMA_PATH)
    if vr.ok:
        print("  ✓ 剧本通过 Schema 校验，结构完整、引用一致。")
    else:
        print("  ✗ 校验失败：")
        for err in vr.errors:
            print(f"    - {err}")

    # ── 5. 输出 YAML 片段 ──
    print_separator("5. 结构化 YAML 输出（前 40 行）")
    yaml_lines = result.yaml_text.split("\n")
    for line in yaml_lines[:40]:
        print(f"  {line}")
    if len(yaml_lines) > 40:
        print(f"  ... (共 {len(yaml_lines)} 行)")

    # ── 6. 可读剧本 ──
    print_separator("6. 可读剧本输出（标注角色/对话/环境）")
    readable_lines = result.readable_text.split("\n")
    for line in readable_lines[:50]:
        print(f"  {line}")
    if len(readable_lines) > 50:
        print(f"  ... (共 {len(readable_lines)} 行)")

    # ── 7. 大模型演示（如已配置） ──
    if config.is_configured:
        print_separator("7. 使用大模型 (LangChain+LangGraph) 生成")
        print(f"  调用模型：{config.model}")
        print("  流水线：extract_characters → extract_locations → segment_scenes → extract_beats")
        try:
            llm_result = convert_text(NOVEL_TEXT, title="雾城来信", author="示例作者", prefer_llm=True)
            llm_script = llm_result.screenplay.get("script", {})
            print(f"  生成器：{llm_result.generator_name}")
            print(f"  角色数：{len(llm_script.get('characters', []))}")
            print(f"  场景数：{len(llm_script.get('scenes', []))}")
            vr2 = validate_screenplay(llm_result.screenplay, SCHEMA_PATH)
            print(f"  Schema 校验：{'✓ 通过' if vr2.ok else '✗ 未通过'}")

            # 保存大模型输出
            output_dir = ROOT / "demo" / "output"
            output_dir.mkdir(exist_ok=True)
            (output_dir / "screenplay_llm.yaml").write_text(llm_result.yaml_text, encoding="utf-8")
            (output_dir / "screenplay_llm_readable.txt").write_text(llm_result.readable_text, encoding="utf-8")
            print(f"  已保存到 demo/output/")
        except Exception as e:
            print(f"  大模型调用失败（已回退规则引擎）：{e}")
    else:
        print_separator("7. 大模型演示（跳过）")
        print("  未配置 API Key，跳过大模型演示。")
        print("  如需启用，请在 .env 中填写 LLM_API_KEY。")

    # ── 保存规则引擎输出 ──
    output_dir = ROOT / "demo" / "output"
    output_dir.mkdir(exist_ok=True)
    (output_dir / "screenplay_rule.yaml").write_text(result.yaml_text, encoding="utf-8")
    (output_dir / "screenplay_rule_readable.txt").write_text(result.readable_text, encoding="utf-8")

    print_separator("演示完成", "═")
    print("输出文件保存在 demo/output/ 目录下。")
    print("运行 python main.py 可打开图形界面。")


if __name__ == "__main__":
    main()
