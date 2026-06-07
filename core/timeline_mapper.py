#!/usr/bin/env python3
"""
Timeline Mapper — 程序化 Timeline 生成器（v1.1 Clip-based + Auto Transition）

核心原则：
1. Single Source of Truth：以 segments.json 为唯一数据源
2. 消除手动映射表：自动对齐 segments.json ↔ prompts.json ↔ scenes/ 目录
3. 三方一致性校验：任何一方缺失或多余 → 立即报错
4. 输出 machine-readable 的 timeline.json，供 concat_engine 消费
5. v1.1 升级：
   - TimelineEntry 升级为 TimelineClip，支持 fade_in/fade_out/transition
   - 自动从 transitions.json 加载转场配置
   - 支持 segment_type 驱动的自动推断
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Tuple


@dataclass
class Transition:
    """段间转场效果"""
    type: str = "fade"
    duration: float = 0.5


@dataclass
class TimelineClip:
    """单段时轴条目（Clip-based）"""
    segment_id: str
    text: str
    duration: float
    media_source: str
    media_path: str
    media_type: str = "video"
    start_time: float = 0.0
    end_time: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    transition: Optional[Dict] = None
    segment_type: str = "unknown"
    notes: str = ""


class TimelineMapper:
    """
    程序化 Timeline 生成器
    """

    def __init__(
        self,
        output_dir: str = "output",
        scenes_dir: str = "scenes",
        prompts_file: str = "prompts.json",
        transitions_file: str = "transitions.json",
    ):
        self.output_dir = Path(output_dir)
        self.scenes_dir = Path(scenes_dir)
        self.prompts_file = Path(prompts_file)
        self.transitions_file = Path(transitions_file)
        self.segments: List[dict] = []
        self.prompts: List[dict] = []
        self.transitions: List[dict] = []
        self.timeline: List[TimelineClip] = []
        self.validation_errors: List[str] = []
        self.validation_warnings: List[str] = []

    def _load_segments(self) -> List[dict]:
        path = self.output_dir / "segments.json"
        if not path.exists():
            raise FileNotFoundError(f"segments.json not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("segments", [])

    def _load_prompts(self) -> List[dict]:
        if not self.prompts_file.exists():
            raise FileNotFoundError(f"prompts.json not found: {self.prompts_file}")
        with open(self.prompts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("scenes", [])

    def _load_transitions(self) -> List[dict]:
        """加载 transitions.json（自动转场配置）"""
        if self.transitions_file.exists():
            with open(self.transitions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _list_scenes(self) -> Dict[str, Path]:
        scenes = {}
        if not self.scenes_dir.exists():
            return scenes
        for f in self.scenes_dir.iterdir():
            if f.suffix.lower() in (".mp4",".mov",".jpg",".jpeg",".png",".gif",".webp"):
                scenes[f.stem] = f
        return scenes

    def validate_triple_consistency(self) -> Tuple[bool, List[str], List[str]]:
        self.segments = self._load_segments()
        self.prompts = self._load_prompts()
        self.transitions = self._load_transitions()
        scenes = self._list_scenes()

        seg_ids = {s["id"] for s in self.segments}
        prompt_ids = {p.get("id", p.get("scene_id", "")) for p in self.prompts}
        scene_ids = set(scenes.keys())

        errors = []
        warnings = []

        missing_in_prompts = seg_ids - prompt_ids
        if missing_in_prompts:
            errors.append(f"[L1-BLOCK] segments 中有 {len(missing_in_prompts)} 个 id 在 prompts.json 中缺失: {missing_in_prompts}")

        missing_in_scenes = prompt_ids - scene_ids
        if missing_in_scenes:
            errors.append(f"[L1-BLOCK] prompts.json 中有 {len(missing_in_scenes)} 个 scene 在 scenes/ 目录中缺失文件: {missing_in_scenes}")

        extra_in_scenes = scene_ids - seg_ids
        if extra_in_scenes:
            warnings.append(f"[L2-WARN] scenes/ 目录中有 {len(extra_in_scenes)} 个文件未在 segments.json 中引用: {extra_in_scenes}")

        if len(seg_ids) != len(prompt_ids):
            errors.append(f"[L1-BLOCK] 数量不一致: segments={len(seg_ids)}, prompts={len(prompt_ids)}")

        self.validation_errors = errors
        self.validation_warnings = warnings
        return (len(errors) == 0, errors, warnings)

    def _resolve_media_path(self, segment_id: str, prompt_entry: dict, scenes: Dict[str, Path]) -> Tuple[str, str]:
        if segment_id in scenes:
            p = scenes[segment_id]
            media_type = "video" if p.suffix.lower() in (".mp4", ".mov") else "image"
            return str(p.relative_to(Path.cwd())), media_type

        explicit_path = prompt_entry.get("media_path", prompt_entry.get("fallback_path", ""))
        if explicit_path and Path(explicit_path).exists():
            p = Path(explicit_path)
            media_type = "video" if p.suffix.lower() in (".mp4", ".mov") else "image"
            return explicit_path, media_type

        rebuild_path = Path("rebuild_animations") / f"{segment_id}.mp4"
        if rebuild_path.exists():
            return str(rebuild_path), "video"

        anim_path = Path("animations") / f"{segment_id}.mp4"
        if anim_path.exists():
            return str(anim_path), "video"

        raise FileNotFoundError(f"[L1-BLOCK] 找不到 segment '{segment_id}' 的素材文件")

    def build_timeline(self, transitions: Optional[List[dict]] = None) -> List[TimelineClip]:
        if self.validation_errors:
            raise RuntimeError(f"Cannot build timeline with L1 errors: {self.validation_errors}")

        scenes = self._list_scenes()
        prompts_map = {p.get("id", p.get("scene_id", "")): p for p in self.prompts}

        # 优先使用传入的 transitions，否则从文件加载
        trans_list = transitions if transitions is not None else self.transitions
        trans_map = {t["index"]: t for t in trans_list}

        timeline = []
        current_time = 0.0

        for idx, seg in enumerate(self.segments):
            seg_id = seg["id"]
            prompt_entry = prompts_map.get(seg_id, {})

            media_path, media_type = self._resolve_media_path(seg_id, prompt_entry, scenes)
            duration = seg.get("duration", 0.0)

            # 获取转场配置
            trans = trans_map.get(idx)

            entry = TimelineClip(
                segment_id=seg_id,
                text=seg.get("text", ""),
                duration=duration,
                media_source=prompt_entry.get("source", "jimeng"),
                media_path=media_path,
                media_type=media_type,
                start_time=current_time,
                end_time=current_time + duration,
                fade_in=seg.get("fade_in", 0.0),
                fade_out=seg.get("fade_out", 0.0),
                transition=trans,
                segment_type=seg.get("segment_type", "unknown"),
                notes=prompt_entry.get("notes", prompt_entry.get("description", "")),
            )
            timeline.append(entry)
            current_time += duration

        self.timeline = timeline
        return timeline

    def save_timeline(self) -> Path:
        timeline_path = self.output_dir / "timeline.json"
        data = {
            "generator": "md2video.timeline_mapper",
            "version": "1.1.0",
            "total_duration": sum(e.duration for e in self.timeline),
            "segment_count": len(self.timeline),
            "has_effects": any(
                e.fade_in > 0 or e.fade_out > 0 or e.transition is not None
                for e in self.timeline
            ),
            "entries": [asdict(e) for e in self.timeline],
            "validation": {
                "errors": self.validation_errors,
                "warnings": self.validation_warnings,
            },
        }
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return timeline_path

    @classmethod
    def load_timeline(cls, output_dir: str) -> List[TimelineClip]:
        path = Path(output_dir) / "timeline.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [TimelineClip(**e) for e in data["entries"]]

    def run(self, transitions: Optional[List[dict]] = None) -> Tuple[Path, List[str], List[str]]:
        ok, errors, warnings = self.validate_triple_consistency()
        if not ok:
            return Path(), errors, warnings

        self.build_timeline(transitions=transitions)
        timeline_path = self.save_timeline()
        return timeline_path, errors, warnings
