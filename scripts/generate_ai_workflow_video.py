#!/usr/bin/env python3
"""Generate the AI workflow demo video with Dreamina-first fallback."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.concat_engine import ConcatEngine
from core.frame_extractor import ExtractConfig, FrameExtractor
from core.segment_tts import SegmentedTTSGenerator
from core.timeline_mapper import TimelineMapper
from extensions.storyboard.storyboard_ai import StoryboardAI
from harness.harness import VideoComplianceHarness

DREAMINA_CLI = Path("/Users/lize/workspace/agent-tools/dreamina/bin/jimeng")
MODEL_ALIASES = {
    "seedance2.0_vipfast": "seedance2.0fast_vip",
    "seedance2.0-fast-vip": "seedance2.0fast_vip",
    "seedance2.0fastvip": "seedance2.0fast_vip",
}
STRUCTURAL_TYPES = {"data_contrast", "list", "date", "quote"}
MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
WIDTH = 1080
HEIGHT = 1920
FPS = 30


@dataclass
class SceneResult:
    segment_id: str
    segment_type: str
    source: str
    media_path: str
    dreamina_submit_id: str = ""
    dreamina_status: str = ""
    fallback_reason: str = ""


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        timeout=timeout,
        check=False,
        capture_output=True,
        text=True,
    )


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_json_maybe(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"items": parsed}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"items": parsed}
        except json.JSONDecodeError:
            return {}
    return {}


def normalize_model_name(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


def discover_env_files() -> dict[str, Any]:
    repo_envs = sorted(str(p.relative_to(REPO_ROOT)) for p in REPO_ROOT.glob(".env*") if p.is_file())
    agent_tools = Path("/Users/lize/workspace/agent-tools")
    tool_envs = []
    if agent_tools.exists():
        tool_envs = sorted(str(p) for p in agent_tools.glob("**/.env*") if p.is_file())
    return {
        "repo_env_files_found": repo_envs,
        "agent_tools_env_files_found": tool_envs,
        "printed_secret_values": False,
    }


def check_dreamina_credit(lock_wait: int) -> dict[str, Any]:
    if not DREAMINA_CLI.exists():
        return {"ok": False, "reason": f"Dreamina CLI not found: {DREAMINA_CLI}"}

    env = os.environ.copy()
    env["DREAMINA_LOCK_WAIT_SECONDS"] = str(lock_wait)
    result = run_cmd([str(DREAMINA_CLI), "user_credit"], env=env, timeout=lock_wait + 30)
    if result.returncode != 0:
        return {
            "ok": False,
            "reason": (result.stderr or result.stdout).strip()[:500],
        }

    data = parse_json_maybe(result.stdout)
    return {
        "ok": True,
        "total_credit": data.get("total_credit"),
        "vip_level": data.get("vip_level"),
    }


def markdown_to_storyboard(input_path: Path, run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = input_path.read_text(encoding="utf-8")
    storyboard = StoryboardAI(chars_per_second=5.2)
    shots = storyboard.parse_markdown(text)
    storyboard.generate_pipeline_inputs(str(run_dir))
    storyboard.save(str(run_dir))

    segments_hint = load_json(run_dir / "segments_hint.json")
    prompts = load_json(run_dir / "prompts.json")

    prompt_map = {p["id"]: p for p in prompts}
    for shot in shots:
        prompt = prompt_map.get(shot.id, {})
        prompt["text"] = shot.text
        prompt["segment_type"] = shot.segment_type
        prompt["prompt"] = build_dreamina_prompt(shot.text, shot.segment_type)
        if shot.segment_type in STRUCTURAL_TYPES:
            prompt["source"] = "python_animation"
        elif shot.visual_type == "static" and shot.segment_type == "cta":
            prompt["source"] = "jimeng"
        else:
            prompt["source"] = "jimeng"
    save_json(run_dir / "prompts.json", prompts)

    return segments_hint, prompts


def generate_tts(run_dir: Path, hints: list[dict[str, Any]]) -> Path:
    generator = SegmentedTTSGenerator(output_dir=str(run_dir), rate="+15%")
    segments = generator.split_by_semantic("", scene_hints=hints)
    for hint, segment in zip(hints, segments):
        if hint.get("segment_type"):
            segment.segment_type = hint["segment_type"]
        if hint.get("notes"):
            segment.notes = hint["notes"]
    asyncio.run(generator.generate_all(progress_callback=lambda sid, dur, typ: print(f"  tts {sid} [{typ}] {dur:.2f}s")))
    return generator.save_manifest()


def build_dreamina_prompt(text: str, segment_type: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if segment_type == "hook":
        return (
            "Vertical 9:16 premium short-video opener, cinematic AI workflow command center, "
            "glass screens, clean Chinese tech aesthetic, dynamic camera move, professional lighting, "
            "no readable text, no logos. Theme: "
            f"{clean[:120]}"
        )
    if segment_type == "cta":
        return (
            "Vertical 9:16 elegant closing scene for a knowledge creator, warm desk light, phone and notebook, "
            "subtle AI interface reflections, calm premium look, no readable text, no logos. Theme: "
            f"{clean[:120]}"
        )
    if segment_type == "quote":
        return (
            "Vertical 9:16 cinematic abstract background for a memorable quote, paper texture, soft light, "
            "minimal premium composition, no readable text, no logos. Theme: "
            f"{clean[:120]}"
        )
    return (
        "Vertical 9:16 cinematic B-roll of an operator turning an AI conversation into a repeatable workflow, "
        "input documents, validation checklist, terminal logs, delivery manifest, clean modern studio, "
        "premium documentary style, no readable text, no logos. Theme: "
        f"{clean[:140]}"
    )


def dreamina_duration(seconds: float) -> int:
    return max(4, min(15, int(round(seconds))))


def find_downloaded_media(download_dir: Path) -> Path | None:
    candidates = [
        p
        for p in download_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES and p.stat().st_size > 1024
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def query_dreamina_result(
    submit_id: str,
    download_dir: Path,
    *,
    lock_wait: int,
    wait_seconds: int,
) -> tuple[str, dict[str, Any], Path | None]:
    env = os.environ.copy()
    env["DREAMINA_LOCK_WAIT_SECONDS"] = str(lock_wait)
    deadline = time.time() + wait_seconds
    last_data: dict[str, Any] = {}
    last_status = "querying"

    while True:
        result = run_cmd(
            [
                str(DREAMINA_CLI),
                "query_result",
                f"--submit_id={submit_id}",
                f"--download_dir={download_dir}",
            ],
            env=env,
            timeout=lock_wait + 60,
        )
        data = parse_json_maybe(result.stdout)
        last_data = data or {"stderr": result.stderr.strip()[:500], "stdout": result.stdout.strip()[:500]}
        status = str(data.get("gen_status") or data.get("status") or "")
        last_status = status or ("command_failed" if result.returncode else "unknown")

        media = find_downloaded_media(download_dir)
        if media:
            return "success", last_data, media
        if result.returncode != 0:
            return "fail", last_data, None
        if status == "success":
            return "success_no_media", last_data, None
        if status == "fail":
            return "fail", last_data, None
        if time.time() >= deadline:
            return last_status or "timeout", last_data, None
        time.sleep(15)


def try_dreamina_scene(
    segment: dict[str, Any],
    prompt: dict[str, Any],
    scenes_dir: Path,
    downloads_dir: Path,
    submissions: list[dict[str, Any]],
    *,
    model: str,
    lock_wait: int,
    submit_poll: int,
    result_wait: int,
) -> tuple[Path | None, str]:
    segment_id = segment["id"]
    download_dir = downloads_dir / segment_id
    download_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DREAMINA_LOCK_WAIT_SECONDS"] = str(lock_wait)
    cmd = [
        str(DREAMINA_CLI),
        "text2video",
        f"--prompt={prompt.get('prompt') or build_dreamina_prompt(segment['text'], segment.get('segment_type', 'narrative'))}",
        "--ratio=9:16",
        f"--duration={dreamina_duration(float(segment.get('duration') or 5.0))}",
        f"--model_version={model}",
        f"--poll={submit_poll}",
    ]

    if model == "seedance2.0_vip":
        cmd.append("--video_resolution=1080p")

    result = run_cmd(cmd, env=env, timeout=lock_wait + submit_poll + 90)
    raw = (result.stdout or result.stderr or "").strip()
    data = parse_json_maybe(raw)
    submit_id = str(data.get("submit_id") or "")
    status = str(data.get("gen_status") or ("command_failed" if result.returncode else "unknown"))

    record = {
        "id": segment_id,
        "model_version": model,
        "submit_id": submit_id,
        "gen_status": status,
        "returncode": result.returncode,
        "credit_count": data.get("credit_count"),
        "fail_reason": data.get("fail_reason", ""),
    }
    submissions.append(record)

    if result.returncode != 0 or status == "fail":
        reason = str(data.get("fail_reason") or raw)[:500]
        record["fallback_reason"] = reason
        return None, reason or "dreamina command failed"

    if not submit_id:
        record["fallback_reason"] = "dreamina submit_id missing"
        return None, "dreamina submit_id missing"

    query_status, query_data, media = query_dreamina_result(
        submit_id,
        download_dir,
        lock_wait=lock_wait,
        wait_seconds=result_wait,
    )
    record["query_status"] = query_status
    record["query_result_status"] = query_data.get("gen_status") or query_data.get("status")
    if media:
        output_path = scenes_dir / f"{segment_id}.mp4"
        shutil.copy2(media, output_path)
        record["downloaded_media"] = str(media.relative_to(REPO_ROOT) if media.is_relative_to(REPO_ROOT) else media)
        record["scene_path"] = str(output_path.relative_to(REPO_ROOT))
        return output_path, ""

    reason = str(query_data.get("fail_reason") or query_status or "dreamina result not ready")[:500]
    record["fallback_reason"] = reason
    return None, reason


def font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=face)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    y: int,
    face: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_gap: int = 18,
) -> int:
    line_h = face.size + line_gap if hasattr(face, "size") else 56
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=face)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, fill=fill, font=face)
        y += line_h
    return y


def base_image(bg: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)
    return img, draw


def save_still_video(image: Image.Image, output_path: Path, duration: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="md2video_scene_") as tmp:
        still = Path(tmp) / "still.png"
        image.save(still)
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-loop",
            "1",
            "-i",
            str(still),
            "-t",
            f"{duration:.3f}",
            "-r",
            str(FPS),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        result = run_cmd(cmd)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"ffmpeg failed for {output_path}")


def draw_footer(draw: ImageDraw.ImageDraw, segment_type: str) -> None:
    face = font(30)
    label = {
        "hook": "AI Workflow",
        "narrative": "Reusable Process",
        "data_contrast": "Before / After",
        "list": "Four Rules",
        "date": "Proof Required",
        "quote": "Core Principle",
        "cta": "Keep Improving",
    }.get(segment_type, "md2video")
    draw.rounded_rectangle([70, HEIGHT - 145, WIDTH - 70, HEIGHT - 85], radius=20, fill=(255, 255, 255), outline=(215, 225, 230), width=2)
    draw.text((96, HEIGHT - 132), label, fill=(28, 48, 58), font=face)


def render_hook(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((10, 25, 33))
    accent = (77, 191, 172)
    for i in range(0, 12):
        y = 260 + i * 95
        color = (20 + i * 4, 53 + i * 3, 64 + i * 2)
        draw.line([(80, y), (WIDTH - 80, y - 80)], fill=color, width=6)
    draw.rounded_rectangle([80, 220, WIDTH - 80, 1180], radius=36, fill=(17, 43, 52), outline=accent, width=3)
    draw.text((116, 280), "md2video", fill=accent, font=font(42))
    title = "三分钟建立可复用的 AI 工作流"
    lines = wrap_text(draw, title, font(86), WIDTH - 220)
    draw_centered_lines(draw, lines, 470, font(86), (245, 249, 250), 26)
    subtitle_lines = wrap_text(draw, "把一次性的聊天，变成可复核、可复用、可改进的流程。", font(48), WIDTH - 260)
    draw_centered_lines(draw, subtitle_lines, 820, font(48), (194, 222, 224), 20)
    for idx, label in enumerate(["输入", "规则", "验证", "交付"]):
        x = 150 + idx * 205
        draw.rounded_rectangle([x, 1030, x + 150, 1115], radius=24, fill=(232, 249, 246), outline=accent, width=2)
        draw.text((x + 37, 1053), label, fill=(10, 55, 54), font=font(36))
    draw_footer(draw, "hook")
    save_still_video(img, output_path, float(segment["duration"]))


def render_narrative(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((244, 247, 246))
    draw.rounded_rectangle([72, 120, WIDTH - 72, 340], radius=28, fill=(20, 57, 69))
    draw.text((112, 170), "从零散提问到稳定流程", fill=(255, 255, 255), font=font(58))
    body = segment["text"]
    lines = wrap_text(draw, body, font(48), WIDTH - 180)
    y = 460
    for line in lines[:9]:
        draw.text((90, y), line, fill=(33, 51, 59), font=font(48))
        y += 68
    cards = [
        ("Input", "输入边界"),
        ("Rules", "执行规则"),
        ("Verify", "验证命令"),
        ("Proof", "交付证据"),
    ]
    y0 = 1180
    for i, (en, cn) in enumerate(cards):
        x = 90 + (i % 2) * 455
        y = y0 + (i // 2) * 180
        draw.rounded_rectangle([x, y, x + 395, y + 135], radius=22, fill=(255, 255, 255), outline=(204, 217, 219), width=2)
        draw.text((x + 30, y + 25), en, fill=(39, 122, 121), font=font(34))
        draw.text((x + 30, y + 73), cn, fill=(31, 45, 53), font=font(42))
    draw_footer(draw, "narrative")
    save_still_video(img, output_path, float(segment["duration"]))


def render_data(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((250, 251, 249))
    draw.text((80, 130), "流程化之前 / 之后", fill=(30, 48, 56), font=font(66))
    data = [("临时提问", 10, "分钟准备"), ("流程化", 2, "分钟准备"), ("复用率", 80, "%")]
    max_val = 100
    x0 = 140
    y_base = 1380
    for i, (label, value, unit) in enumerate(data):
        x = x0 + i * 300
        h = int((value / max_val) * 760)
        color = [(223, 93, 78), (63, 157, 135), (45, 103, 155)][i]
        draw.rounded_rectangle([x, y_base - h, x + 190, y_base], radius=24, fill=color)
        draw.text((x + 35, y_base - h - 90), str(value), fill=(30, 48, 56), font=font(64))
        draw.text((x + 30, y_base + 35), label, fill=(30, 48, 56), font=font(38))
        draw.text((x + 32, y_base + 88), unit, fill=(95, 108, 113), font=font(30))
    draw.line([(100, y_base), (WIDTH - 100, y_base)], fill=(185, 198, 202), width=4)
    note = "差别不在模型，而在输入、规则、验证和交付是否固定。"
    lines = wrap_text(draw, note, font(44), WIDTH - 170)
    draw_centered_lines(draw, lines, 1510, font(44), (30, 48, 56), 16)
    draw_footer(draw, "data_contrast")
    save_still_video(img, output_path, float(segment["duration"]))


def render_list(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((238, 244, 243))
    draw.text((80, 130), "四个固定动作", fill=(28, 48, 58), font=font(70))
    items = ["写清楚输入", "写清楚输出", "列出失败检查", "留下验证命令"]
    for idx, item in enumerate(items):
        y = 350 + idx * 275
        draw.rounded_rectangle([95, y, WIDTH - 95, y + 190], radius=28, fill=(255, 255, 255), outline=(198, 214, 216), width=2)
        draw.ellipse([140, y + 48, 230, y + 138], fill=(42, 139, 126))
        draw.text((166, y + 60), str(idx + 1), fill=(255, 255, 255), font=font(44))
        draw.text((270, y + 58), item, fill=(30, 48, 56), font=font(58))
    draw_footer(draw, "list")
    save_still_video(img, output_path, float(segment["duration"]))


def render_date(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((247, 248, 244))
    draw.text((90, 120), "2026 年 6 月 8 日", fill=(28, 48, 58), font=font(68))
    draw.rounded_rectangle([100, 270, WIDTH - 100, 1220], radius=30, fill=(255, 255, 255), outline=(205, 216, 220), width=2)
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    cell_w = 120
    start_x = 140
    start_y = 380
    for i, wd in enumerate(weekdays):
        draw.text((start_x + i * cell_w + 42, start_y), wd, fill=(94, 108, 113), font=font(34))
    day = 1
    for row in range(5):
        for col in range(7):
            if day > 30:
                break
            x = start_x + col * cell_w
            y = start_y + 95 + row * 120
            if day == 8:
                draw.ellipse([x + 16, y - 16, x + 100, y + 68], fill=(42, 139, 126))
                fill = (255, 255, 255)
            else:
                fill = (34, 53, 60)
            draw.text((x + 42 if day < 10 else x + 28, y), str(day), fill=fill, font=font(44))
            day += 1
    proof = "每次交付前必须留下运行证明：日志、清单、检查报告和最终文件路径。"
    lines = wrap_text(draw, proof, font(46), WIDTH - 190)
    draw_centered_lines(draw, lines, 1350, font(46), (28, 48, 58), 18)
    draw_footer(draw, "date")
    save_still_video(img, output_path, float(segment["duration"]))


def render_quote(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((19, 33, 39))
    draw.rounded_rectangle([90, 280, WIDTH - 90, 1360], radius=36, fill=(247, 246, 239))
    quote = "好提示词不是让 AI 显得聪明，而是让结果可以被复核、被复用、被改进。"
    draw.text((145, 360), '"', fill=(42, 139, 126), font=font(120))
    lines = wrap_text(draw, quote, font(60), WIDTH - 260)
    draw_centered_lines(draw, lines, 570, font(60), (28, 48, 58), 24)
    draw.text((WIDTH - 390, 1170), "- AI 工作流原则", fill=(95, 108, 113), font=font(40))
    draw_footer(draw, "quote")
    save_still_video(img, output_path, float(segment["duration"]))


def render_cta(segment: dict[str, Any], output_path: Path) -> None:
    img, draw = base_image((12, 25, 30))
    draw.text((110, 220), "把经验变成稳定流程", fill=(245, 249, 248), font=font(64))
    lines = wrap_text(draw, "收藏这条视频，在评论区告诉我你的工作流卡在哪一步。", font(48), WIDTH - 220)
    draw_centered_lines(draw, lines, 390, font(48), (194, 222, 224), 18)

    qr_path = REPO_ROOT / "assets/qr.png"
    if qr_path.exists():
        qr = Image.open(qr_path).convert("RGB").resize((410, 410), Image.Resampling.LANCZOS)
        draw.rounded_rectangle([WIDTH // 2 - 245, 710, WIDTH // 2 + 245, 1200], radius=36, fill=(255, 255, 255))
        img.paste(qr, (WIDTH // 2 - 205, 750))
        draw.text((WIDTH // 2 - 145, 1245), "扫码加入交流", fill=(245, 249, 248), font=font(44))
    else:
        draw.text((190, 860), "继续拆解 AI 工作流", fill=(245, 249, 248), font=font(58))

    draw.rounded_rectangle([140, 1450, WIDTH - 140, 1570], radius=28, fill=(42, 139, 126))
    draw.text((268, 1482), "复核 · 复用 · 改进", fill=(255, 255, 255), font=font(52))
    draw_footer(draw, "cta")
    save_still_video(img, output_path, float(segment["duration"]))


def render_local_scene(segment: dict[str, Any], output_path: Path) -> None:
    segment_type = segment.get("segment_type", "narrative")
    renderers = {
        "hook": render_hook,
        "narrative": render_narrative,
        "data_contrast": render_data,
        "list": render_list,
        "date": render_date,
        "quote": render_quote,
        "cta": render_cta,
    }
    renderer = renderers.get(segment_type, render_narrative)
    renderer(segment, output_path)


def build_scenes(
    run_dir: Path,
    scenes_dir: Path,
    prompts: list[dict[str, Any]],
    *,
    model: str,
    lock_wait: int,
    submit_poll: int,
    result_wait: int,
    max_dreamina_scenes: int,
    force_local: bool,
) -> list[SceneResult]:
    segments = load_json(run_dir / "segments.json")["segments"]
    prompt_map = {p["id"]: p for p in prompts}
    scenes_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = run_dir / "dreamina_downloads"
    submissions: list[dict[str, Any]] = []
    scene_results: list[SceneResult] = []
    dreamina_attempts = 0
    dreamina_disabled_reason = ""

    for segment in segments:
        segment_id = segment["id"]
        segment_type = segment.get("segment_type", "narrative")
        prompt = prompt_map.get(segment_id, {})
        output_path = scenes_dir / f"{segment_id}.mp4"
        should_try_dreamina = (
            not force_local
            and not dreamina_disabled_reason
            and prompt.get("source") == "jimeng"
            and dreamina_attempts < max_dreamina_scenes
        )

        fallback_reason = ""
        source = "python_animation"
        if should_try_dreamina:
            dreamina_attempts += 1
            print(f"  dreamina {segment_id} model={model}")
            media, reason = try_dreamina_scene(
                segment,
                prompt,
                scenes_dir,
                downloads_dir,
                submissions,
                model=model,
                lock_wait=lock_wait,
                submit_poll=submit_poll,
                result_wait=result_wait,
            )
            if media:
                source = "jimeng"
                output_path = media
            else:
                fallback_reason = reason
                if "ExceedConcurrencyLimit" in reason or "concurrency" in reason.lower():
                    dreamina_disabled_reason = reason

        if source != "jimeng":
            if fallback_reason:
                print(f"  local fallback {segment_id}: {fallback_reason[:120]}")
                if not dreamina_disabled_reason:
                    dreamina_disabled_reason = fallback_reason
            else:
                print(f"  local scene {segment_id}")
            render_local_scene(segment, output_path)

        prompt["source"] = source
        prompt["media_path"] = str(output_path.relative_to(REPO_ROOT))
        scene_results.append(
            SceneResult(
                segment_id=segment_id,
                segment_type=segment_type,
                source=source,
                media_path=str(output_path.relative_to(REPO_ROOT)),
                fallback_reason=fallback_reason,
            )
        )

    save_json(run_dir / "prompts.json", prompts)
    save_json(run_dir / "dreamina_submissions.json", submissions)
    save_json(run_dir / "scene_results.json", [asdict(r) for r in scene_results])
    return scene_results


def build_timeline(run_dir: Path, scenes_dir: Path) -> Path:
    save_json(run_dir / "transitions.json", [])
    mapper = TimelineMapper(
        output_dir=str(run_dir),
        scenes_dir=str(scenes_dir),
        prompts_file=str(run_dir / "prompts.json"),
        transitions_file=str(run_dir / "transitions.json"),
    )
    timeline_path, errors, warnings = mapper.run()
    if errors:
        raise RuntimeError("; ".join(errors))
    if warnings:
        print(f"  timeline warnings: {warnings}")
    return timeline_path


def concat_video(run_dir: Path, final_path: Path) -> Path:
    engine = ConcatEngine()
    return engine.concat(
        timeline_path=str(run_dir / "timeline.json"),
        segments_audio_dir=str(run_dir / "narration_segments"),
        output_video=str(final_path),
    )


def sync_for_harness(run_dir: Path, final_path: Path) -> dict[str, Any]:
    output_root = REPO_ROOT / "output"
    output_root.mkdir(exist_ok=True)
    shutil.copy2(run_dir / "segments.json", output_root / "segments.json")
    shutil.copy2(run_dir / "timeline.json", output_root / "timeline.json")
    shutil.copy2(final_path, output_root / "final.mp4")
    shutil.copytree(run_dir / "narration_segments", output_root / "narration_segments", dirs_exist_ok=True)

    root_prompts = REPO_ROOT / "prompts.json"
    backup = None
    if root_prompts.exists():
        backup = run_dir / "prompts.root.backup.json"
        shutil.copy2(root_prompts, backup)
    shutil.copy2(run_dir / "prompts.json", root_prompts)
    return {"root_prompts": root_prompts, "backup": backup}


def restore_after_harness(sync_state: dict[str, Any]) -> None:
    root_prompts: Path = sync_state["root_prompts"]
    backup: Path | None = sync_state["backup"]
    if backup and backup.exists():
        shutil.copy2(backup, root_prompts)
    elif root_prompts.exists():
        root_prompts.unlink()


def run_checks(run_dir: Path, final_path: Path, keep_root_prompts: bool) -> dict[str, Any]:
    sync_state = sync_for_harness(run_dir, final_path)
    try:
        frame_dir = REPO_ROOT / "output/frame_checks"
        extractor = FrameExtractor(ExtractConfig(frames_per_segment=2, output_dir=str(frame_dir)))
        extractor.extract_and_check(str(final_path), str(run_dir / "timeline.json"))
        frame_report = extractor.generate_report()
        shutil.copy2(frame_report, run_dir / "frame_check_report.json")

        harness = VideoComplianceHarness()
        harness.DEFAULT_REPORT_PATH = run_dir / "compliance_report.json"
        harness.DEFAULT_SUMMARY_PATH = run_dir / "compliance_summary.txt"
        harness.run(str(final_path))
        l1_failed = harness.has_l1_failures()
        l2_failed = any(r.level == "L2" and not r.passed for r in harness.results)
        return {
            "frame_report": str((run_dir / "frame_check_report.json").relative_to(REPO_ROOT)),
            "compliance_report": str((run_dir / "compliance_report.json").relative_to(REPO_ROOT)),
            "l1_failed": l1_failed,
            "l2_failed": l2_failed,
            "result_count": len(harness.results),
        }
    finally:
        if not keep_root_prompts:
            restore_after_harness(sync_state)


def ffprobe_summary(video_path: Path) -> dict[str, Any]:
    result = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(video_path),
        ]
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}
    data = parse_json_maybe(result.stdout)
    return {
        "ok": True,
        "duration": data.get("format", {}).get("duration"),
        "streams": data.get("streams", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="examples/ai_workflow_video_script.md")
    parser.add_argument("--output-dir", default="output/ai_workflow_demo")
    parser.add_argument("--dreamina-model", default="seedance2.0_vipfast")
    parser.add_argument("--dreamina-lock-wait", type=int, default=30)
    parser.add_argument("--dreamina-submit-poll", type=int, default=90)
    parser.add_argument("--dreamina-result-wait", type=int, default=45)
    parser.add_argument("--max-dreamina-scenes", type=int, default=4)
    parser.add_argument("--force-local", action="store_true")
    parser.add_argument("--keep-root-prompts", action="store_true")
    args = parser.parse_args()

    input_path = (REPO_ROOT / args.input).resolve()
    run_dir = (REPO_ROOT / args.output_dir).resolve()
    scenes_dir = run_dir / "scenes"
    final_path = run_dir / "ai_workflow_demo.mp4"
    model = normalize_model_name(args.dreamina_model)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    run_dir.mkdir(parents=True, exist_ok=True)

    env_report = discover_env_files()
    credit_report = check_dreamina_credit(args.dreamina_lock_wait) if not args.force_local else {"ok": False, "reason": "force_local"}
    print(f"env repo_files={env_report['repo_env_files_found']} agent_tools_env_count={len(env_report['agent_tools_env_files_found'])}")
    if credit_report.get("ok"):
        print(f"dreamina credit total={credit_report.get('total_credit')} vip={credit_report.get('vip_level')} model={model}")
    else:
        print(f"dreamina unavailable: {credit_report.get('reason')}")

    hints, prompts = markdown_to_storyboard(input_path, run_dir)
    generate_tts(run_dir, hints)
    scene_results = build_scenes(
        run_dir,
        scenes_dir,
        prompts,
        model=model,
        lock_wait=args.dreamina_lock_wait,
        submit_poll=args.dreamina_submit_poll,
        result_wait=args.dreamina_result_wait,
        max_dreamina_scenes=args.max_dreamina_scenes,
        force_local=args.force_local or not credit_report.get("ok"),
    )
    build_timeline(run_dir, scenes_dir)
    concat_video(run_dir, final_path)
    checks = run_checks(run_dir, final_path, args.keep_root_prompts)
    probe = ffprobe_summary(final_path)

    run_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path.relative_to(REPO_ROOT)),
        "output_video": str(final_path.relative_to(REPO_ROOT)),
        "env_report": env_report,
        "dreamina": {
            "requested_model": args.dreamina_model,
            "used_model": model,
            "cli": str(DREAMINA_CLI),
            "credit_report": credit_report,
        },
        "scene_results": [asdict(r) for r in scene_results],
        "checks": checks,
        "ffprobe": probe,
    }
    save_json(run_dir / "run_manifest.json", run_manifest)

    if checks.get("l1_failed"):
        print(f"L1 checks failed. See {run_dir / 'compliance_report.json'}")
        return 2

    print(f"video={final_path}")
    print(f"manifest={run_dir / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
