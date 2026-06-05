from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .models import ValidationResult


def load_schema(schema_path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(schema_path).read_text(encoding="utf-8"))


def validate_screenplay(data: dict[str, Any], schema_path: str | Path) -> ValidationResult:
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    messages: list[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.path) or "<root>"
        messages.append(f"{loc}: {err.message}")

    messages.extend(validate_cross_references(data))
    return ValidationResult(ok=not messages, errors=messages)


def validate_cross_references(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    script = data.get("script", {})

    character_ids = {c.get("id") for c in script.get("characters", [])}
    location_ids = {l.get("id") for l in script.get("locations", [])}

    previous_scene_no = 0

    for scene in script.get("scenes", []):
        scene_id = scene.get("id", "<unknown_scene>")
        scene_no = scene.get("scene_number")
        if isinstance(scene_no, int) and scene_no <= previous_scene_no:
            errors.append(f"{scene_id}: scene_number should be strictly increasing.")
        if isinstance(scene_no, int):
            previous_scene_no = scene_no

        location_id = scene.get("heading", {}).get("location_id")
        if location_id and location_id not in location_ids:
            errors.append(f"{scene_id}: heading.location_id '{location_id}' not found in locations.")

        for cid in scene.get("characters", []):
            if cid not in character_ids:
                errors.append(f"{scene_id}: character '{cid}' not found in characters.")

        for idx, beat in enumerate(scene.get("beats", [])):
            if beat.get("type") == "dialogue":
                cid = beat.get("character_id")
                if not cid:
                    errors.append(f"{scene_id}.beats[{idx}]: dialogue requires character_id.")
                elif cid not in character_ids:
                    errors.append(f"{scene_id}.beats[{idx}]: character_id '{cid}' not found in characters.")

    return errors
