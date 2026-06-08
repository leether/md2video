#!/usr/bin/env python3
"""Import and routing smoke checks for md2video CI."""

import importlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

MODULES = [
    "core.segment_tts",
    "core.timeline_mapper",
    "core.concat_engine",
    "core.frame_extractor",
    "core.cta_resource",
    "extensions.storyboard.storyboard_ai",
    "extensions.animations.animation_templates",
    "extensions.animation_templates.base",
    "harness.harness",
    "harness.memory_loader",
    "harness.self_report",
    "scripts.lint_narration_style",
    "scripts.preflight",
    "scripts.orchestrator",
]


def check_imports() -> None:
    for module in MODULES:
        importlib.import_module(module)
        print(f"IMPORT_OK {module}")


def check_animation_routing() -> None:
    rules_path = Path("rules/storyboard_rules.json")
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = json.load(f)

    from extensions.animations.animation_templates import available_animation_types

    supported = set(available_animation_types())
    missing = []
    for segment_type, mapping in rules.get("segment_type_mapping", {}).items():
        if mapping.get("visual_type") != "animation":
            continue
        animation_type = mapping.get("animation_type")
        if animation_type not in supported:
            missing.append(f"{segment_type}:{animation_type}")

    if missing:
        raise SystemExit(
            "Unsupported animation_type values in rules/storyboard_rules.json: "
            + ", ".join(missing)
        )

    print("ANIMATION_ROUTING_OK")


def main() -> None:
    check_imports()
    check_animation_routing()


if __name__ == "__main__":
    main()
