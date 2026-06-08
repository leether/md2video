#!/usr/bin/env python3
"""Governed md2video pipeline orchestrator.

The current orchestrator provides the stable governance envelope: preflight,
smoke validation, no-write self-reporting, JSONL logs, and a run manifest. It
does not call paid or external generation services unless a future explicit
pipeline command is added.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.1.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command_first_line(command: list[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else None


def git_value(args: list[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def artifact_entry(path: Path) -> dict:
    exists = path.exists()
    entry = {
        "path": str(path),
        "exists": exists,
    }
    if exists and path.is_file():
        entry["size_bytes"] = path.stat().st_size
        entry["sha256"] = sha256_file(path)
    return entry


class PipelineLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.entries: list[dict] = []
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")

    def record(self, step: str, status: str, **meta) -> dict:
        entry = {
            "t": datetime.now().isoformat(),
            "step": step,
            "status": status,
            **meta,
        }
        self.entries.append(entry)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry


def run_command(step: str, command: list[str], logger: PipelineLogger) -> int:
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = int((time.time() - started) * 1000)
    logger.record(
        step,
        "success" if completed.returncode == 0 else "failed",
        command=command,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        stdout_preview=(completed.stdout or "")[:1000],
        stderr_preview=(completed.stderr or "")[:1000],
    )
    return completed.returncode


def build_run_manifest(
    input_path: Optional[Path],
    input_display_path: Optional[Path],
    output_dir: Path,
    log_path: Path,
    mode: str,
    steps: list[dict],
) -> dict:
    artifacts = {
        "segments": artifact_entry(output_dir / "segments.json"),
        "prompts": artifact_entry(REPO_ROOT / "prompts.json"),
        "timeline": artifact_entry(output_dir / "timeline.json"),
        "final": artifact_entry(output_dir / "final.mp4"),
        "final_with_cta": artifact_entry(output_dir / "final_with_cta.mp4"),
        "frame_report": artifact_entry(output_dir / "frame_checks" / "frame_check_report.json"),
        "compliance_report": artifact_entry(output_dir / "compliance_report.json"),
        "cta_registry": artifact_entry(REPO_ROOT / "cta_resources.json"),
        "pipeline_log": artifact_entry(log_path),
    }

    return {
        "generator": "md2video.orchestrator",
        "version": VERSION,
        "created_at": datetime.now().isoformat(),
        "mode": mode,
        "repo": {
            "branch": git_value(["branch", "--show-current"]),
            "commit": git_value(["rev-parse", "HEAD"]),
            "status_short": git_value(["status", "--short"]),
        },
        "environment": {
            "python": sys.version.split()[0],
            "ffmpeg": command_first_line(["ffmpeg", "-version"]),
            "ffprobe": command_first_line(["ffprobe", "-version"]),
        },
        "input": {
            "path": str(input_display_path) if input_display_path else None,
            "resolved_path": str(input_path) if input_path else None,
            "exists": bool(input_path and input_path.exists()),
            "sha256": sha256_file(input_path) if input_path and input_path.exists() else None,
        },
        "output_dir": str(output_dir),
        "artifacts": artifacts,
        "steps": steps,
    }


def write_manifest(manifest: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "run-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="md2video governed pipeline orchestrator")
    parser.add_argument("--input", help="Source Markdown/text input")
    parser.add_argument("--output-dir", default="output", help="Pipeline output directory")
    parser.add_argument("--log", default=".md2video-pipeline.jsonl", help="JSONL pipeline log path")
    parser.add_argument("--dry-run", action="store_true", help="Run governance checks without video generation")
    parser.add_argument("--skip-command-checks", action="store_true", help="Skip ffmpeg/ffprobe preflight command checks")
    parser.add_argument("--allow-dirty-output", action="store_true", help="Do not warn about existing output artifacts")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    log_path = Path(args.log).resolve()
    input_display_path = Path(args.input) if args.input else None
    input_path = input_display_path.resolve() if input_display_path else None

    logger = PipelineLogger(log_path)
    mode = "dry-run" if args.dry_run else "governance"

    preflight_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "preflight.py"),
        "--output-dir",
        str(output_dir),
        "--json",
    ]
    if input_path:
        preflight_cmd.extend(["--input", str(input_path)])
    if args.skip_command_checks:
        preflight_cmd.append("--skip-command-checks")
    if args.allow_dirty_output:
        preflight_cmd.append("--allow-dirty-output")

    commands = [
        ("preflight", preflight_cmd),
        ("cta_resources", [sys.executable, str(REPO_ROOT / "scripts" / "verify_cta_resources.py")]),
        ("smoke_imports", [sys.executable, str(REPO_ROOT / "scripts" / "smoke_imports.py")]),
        ("self_report_no_write", [
            sys.executable,
            str(REPO_ROOT / "harness" / "self_report.py"),
            "--project-dir",
            str(REPO_ROOT),
            "--no-write",
            "--json",
        ]),
    ]

    exit_code = 0
    for step, command in commands:
        code = run_command(step, command, logger)
        if code != 0 and exit_code == 0:
            exit_code = code

    manifest = build_run_manifest(input_path, input_display_path, output_dir, log_path, mode, logger.entries)
    manifest_path = write_manifest(manifest, output_dir)
    logger.record("run_manifest", "success", path=str(manifest_path))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
