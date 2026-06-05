from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_yaml_or_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a top-level object")
    return data


def dump_yaml(data: dict[str, Any], path: str | Path | None = None) -> str:
    text = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        width=100,
        default_flow_style=False,
    )
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text
