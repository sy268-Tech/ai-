from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import LLMConfig
from .models import ConvertOptions
from .pipeline import parse_novel_input
from .service import build_novel_from_text, convert_novel
from .renderer import render_readable_script
from .validators import validate_screenplay
from .yaml_io import dump_yaml, load_yaml_or_json


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "screenplay.schema.yaml"


def convert_command(args: argparse.Namespace) -> int:
    options = ConvertOptions(
        max_paragraphs_per_scene=args.max_paragraphs_per_scene,
        keep_source_refs=not args.no_source_refs,
        default_format=args.default_format,
    )

    # 输入既支持结构化 YAML/JSON，也支持纯文本小说（--text）
    if args.text:
        raw = Path(args.input).read_text(encoding="utf-8")
        novel = build_novel_from_text(
            raw,
            title=args.title or Path(args.input).stem,
            author=args.author or "",
            fmt=args.default_format,
            config=LLMConfig.from_env(),
        )
    else:
        data = load_yaml_or_json(args.input)
        novel = parse_novel_input(data)

    prefer_llm = not args.no_llm
    screenplay, used_llm = convert_novel(novel, options=options, prefer_llm=prefer_llm)

    schema_path = Path(args.schema) if args.schema else DEFAULT_SCHEMA_PATH
    result = validate_screenplay(screenplay, schema_path)
    if not result.ok:
        print("生成的剧本未通过 Schema 校验：", file=sys.stderr)
        for err in result.errors:
            print(f"- {err}", file=sys.stderr)
        return 2

    engine = "大模型 (LangChain+LangGraph)" if used_llm else "规则引擎"
    print(f"[生成引擎] {engine}", file=sys.stderr)

    if args.output:
        dump_yaml(screenplay, args.output)
        print(f"已生成剧本 YAML：{args.output}", file=sys.stderr)
        if args.readable:
            readable_path = Path(args.output).with_suffix(".txt")
            readable_path.write_text(render_readable_script(screenplay), encoding="utf-8")
            print(f"已生成可读剧本：{readable_path}", file=sys.stderr)
    else:
        if args.readable:
            print(render_readable_script(screenplay))
        else:
            print(dump_yaml(screenplay))

    return 0


def validate_command(args: argparse.Namespace) -> int:
    data = load_yaml_or_json(args.input)
    schema_path = Path(args.schema) if args.schema else DEFAULT_SCHEMA_PATH
    result = validate_screenplay(data, schema_path)

    if result.ok:
        print("OK：剧本 YAML 校验通过。")
        return 0

    print("校验失败：")
    for err in result.errors:
        print(f"- {err}")
    return 1


def config_command(args: argparse.Namespace) -> int:
    """打印当前大模型配置状态，便于排查 .env 是否生效。"""
    cfg = LLMConfig.from_env()
    print("当前大模型配置（来自 .env / 环境变量）：")
    print(f"  API Key : {'已配置 ✓' if cfg.is_configured else '未配置 ✗（请在 .env 填写 LLM_API_KEY）'}")
    print(f"  Base URL: {cfg.base_url}")
    print(f"  Model   : {cfg.model}")
    print(f"  温度    : {cfg.temperature}")
    print(f"  最大 token: {cfg.max_tokens}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel2script",
        description="把小说文本自动转换为结构化剧本 YAML（支持 LangChain + LangGraph 大模型）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="把小说转换为剧本 YAML。")
    convert.add_argument("input", help="小说输入文件（YAML/JSON，或配合 --text 的纯文本）。")
    convert.add_argument("-o", "--output", help="输出剧本 YAML 路径。")
    convert.add_argument("--text", action="store_true", help="输入是纯文本小说（按章节标题切分）。")
    convert.add_argument("--title", help="剧本标题（--text 模式下使用）。")
    convert.add_argument("--author", help="原作者（--text 模式下使用）。")
    convert.add_argument("--readable", action="store_true", help="额外输出标注角色/对话/环境的可读剧本。")
    convert.add_argument("--no-llm", action="store_true", help="强制使用规则引擎，不调用大模型。")
    convert.add_argument("--schema", help="Schema 路径，默认 schemas/screenplay.schema.yaml。")
    convert.add_argument("--max-paragraphs-per-scene", type=int, default=6)
    convert.add_argument("--no-source-refs", action="store_true")
    convert.add_argument(
        "--default-format",
        default="web_series",
        choices=[
            "film",
            "web_series",
            "short_drama",
            "animation",
            "audio_drama",
            "stage_play",
            "unknown",
        ],
    )
    convert.set_defaults(func=convert_command)

    validate = sub.add_parser("validate", help="校验剧本 YAML。")
    validate.add_argument("input", help="剧本 YAML 路径。")
    validate.add_argument("--schema", help="Schema 路径，默认 schemas/screenplay.schema.yaml。")
    validate.set_defaults(func=validate_command)

    config = sub.add_parser("config", help="查看当前大模型配置状态。")
    config.set_defaults(func=config_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
