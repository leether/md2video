#!/usr/bin/env python3
"""Preflight checks for md2video pipeline runs."""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON_FILES = [
    "harness/video-rules.json",
    "rules/segment_types.json",
    "rules/storyboard_rules.json",
    "cta_resources.json",
]


def result(
    check_id: str,
    name: str,
    level: str,
    passed: bool,
    detail: str,
    block_on_fail: bool,
    **extra,
) -> dict:
    data = {
        "id": check_id,
        "name": name,
        "level": level,
        "passed": passed,
        "detail": detail,
        "block_on_fail": block_on_fail,
    }
    data.update(extra)
    return data


def check_required_commands(commands: Iterable[str]) -> dict:
    missing = [cmd for cmd in commands if shutil.which(cmd) is None]
    if missing:
        return result(
            "required_commands",
            "Required command availability",
            "L1",
            False,
            "Missing required command(s): " + ", ".join(missing),
            True,
            missing=missing,
        )
    return result(
        "required_commands",
        "Required command availability",
        "L1",
        True,
        "All required commands are available",
        True,
        missing=[],
    )


def check_json_files(paths: Iterable[str]) -> dict:
    errors = []
    for rel_path in paths:
        path = REPO_ROOT / rel_path
        if not path.exists():
            errors.append(f"{rel_path}: missing")
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as exc:
            errors.append(f"{rel_path}: {exc}")

    if errors:
        return result(
            "json_validity",
            "Governance JSON validity",
            "L1",
            False,
            "; ".join(errors),
            True,
            errors=errors,
        )
    return result(
        "json_validity",
        "Governance JSON validity",
        "L1",
        True,
        "All governance JSON files parse successfully",
        True,
        errors=[],
    )


def check_animation_routing() -> dict:
    sys.path.insert(0, str(REPO_ROOT))
    from extensions.animations.animation_templates import available_animation_types

    rules_path = REPO_ROOT / "rules" / "storyboard_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = json.load(f)

    supported = set(available_animation_types())
    missing = []
    for segment_type, mapping in rules.get("segment_type_mapping", {}).items():
        if mapping.get("visual_type") != "animation":
            continue
        animation_type = mapping.get("animation_type")
        if animation_type not in supported:
            missing.append(f"{segment_type}:{animation_type}")

    if missing:
        return result(
            "animation_routing",
            "Storyboard animation routing",
            "L1",
            False,
            "Unsupported animation type(s): " + ", ".join(missing),
            True,
            missing=missing,
        )
    return result(
        "animation_routing",
        "Storyboard animation routing",
        "L1",
        True,
        "All storyboard animation types resolve",
        True,
        missing=[],
    )


def check_cta_resources() -> dict:
    sys.path.insert(0, str(REPO_ROOT))
    verify = importlib.import_module("scripts.verify_cta_resources")
    errors = verify.validate_registry()
    if errors:
        return result(
            "cta_registry",
            "CTA resource registry",
            "L1",
            False,
            "; ".join(errors),
            True,
            errors=errors,
        )
    return result(
        "cta_registry",
        "CTA resource registry",
        "L1",
        True,
        "CTA resource registry is consistent",
        True,
        errors=[],
    )


def check_input_text(input_path: Optional[Path]) -> dict:
    if not input_path:
        return result(
            "tts_text_sanitization",
            "TTS text sanitization",
            "L2",
            True,
            "Skipped: no input file supplied",
            False,
            findings=[],
        )
    if not input_path.exists():
        return result(
            "tts_text_sanitization",
            "TTS text sanitization",
            "L2",
            False,
            f"Input file does not exist: {input_path}",
            False,
            findings=["missing_input"],
        )

    text = input_path.read_text(encoding="utf-8")
    findings = []
    if "---" in text:
        findings.append("contains '---', which should be normalized before edge-tts")
    if "~" in text:
        findings.append("contains '~', which should be normalized before edge-tts")

    return result(
        "tts_text_sanitization",
        "TTS text sanitization",
        "L2",
        len(findings) == 0,
        "No TTS-sensitive characters found" if not findings else "; ".join(findings),
        False,
        findings=findings,
    )


def check_output_dir(output_dir: Path, allow_dirty_output: bool = False) -> dict:
    known_artifacts = [
        "segments.json",
        "timeline.json",
        "final.mp4",
        "final_with_cta.mp4",
        "compliance_report.json",
        "frame_checks",
        "run-manifest.json",
    ]
    if allow_dirty_output or not output_dir.exists():
        return result(
            "output_dir_state",
            "Output directory state",
            "L2",
            True,
            "Output directory is clean or explicitly allowed",
            False,
            stale_artifacts=[],
        )

    stale = [name for name in known_artifacts if (output_dir / name).exists()]
    return result(
        "output_dir_state",
        "Output directory state",
        "L2",
        len(stale) == 0,
        "No known stale artifacts found" if not stale else "Known output artifacts already exist: " + ", ".join(stale),
        False,
        stale_artifacts=stale,
    )


def summarize(checks: list[dict]) -> dict:
    l1 = [c for c in checks if c["level"] == "L1"]
    l2 = [c for c in checks if c["level"] == "L2"]
    return {
        "l1": {
            "total": len(l1),
            "passed": sum(1 for c in l1 if c["passed"]),
            "failed": sum(1 for c in l1 if not c["passed"]),
        },
        "l2": {
            "total": len(l2),
            "passed": sum(1 for c in l2 if c["passed"]),
            "failed": sum(1 for c in l2 if not c["passed"]),
        },
    }


def run_preflight(
    input_path: Optional[Path] = None,
    output_dir: Path = Path("output"),
    skip_command_checks: bool = False,
    allow_dirty_output: bool = False,
) -> dict:
    checks = []
    if skip_command_checks:
        checks.append(result(
            "required_commands",
            "Required command availability",
            "L1",
            True,
            "Skipped by --skip-command-checks",
            True,
            skipped=True,
            missing=[],
        ))
    else:
        checks.append(check_required_commands(["ffmpeg", "ffprobe"]))

    checks.extend([
        check_json_files(DEFAULT_JSON_FILES),
        check_animation_routing(),
        check_cta_resources(),
        check_input_text(input_path),
        check_output_dir(output_dir, allow_dirty_output=allow_dirty_output),
    ])

    summary = summarize(checks)
    return {
        "preflight": "md2video.pipeline_preflight",
        "ok": summary["l1"]["failed"] == 0,
        "summary": summary,
        "checks": checks,
    }


def format_human(report: dict) -> str:
    lines = ["md2video Preflight"]
    for check in report["checks"]:
        status = "PASS" if check["passed"] else ("FAIL" if check["level"] == "L1" else "WARN")
        lines.append(f"[{check['level']}] {status} {check['id']}: {check['detail']}")
    lines.append(f"Result: {'PASS' if report['ok'] else 'FAIL'}")
    return "\n".join(lines)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="md2video pipeline preflight checks")
    parser.add_argument("--input", help="Source Markdown/text input")
    parser.add_argument("--output-dir", default="output", help="Pipeline output directory")
    parser.add_argument("--skip-command-checks", action="store_true", help="Skip ffmpeg/ffprobe availability checks")
    parser.add_argument("--allow-dirty-output", action="store_true", help="Do not warn about existing output artifacts")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    report = run_preflight(
        input_path=Path(args.input).resolve() if args.input else None,
        output_dir=Path(args.output_dir).resolve(),
        skip_command_checks=args.skip_command_checks,
        allow_dirty_output=args.allow_dirty_output,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_human(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
