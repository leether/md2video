#!/usr/bin/env python3
"""
Segmented TTS Generator (v1.1 — Semantic Segment Typing)

核心原则：
1. 段落切分基于语义边界（句号/分号/逻辑转折），而非固定字数
2. 每段独立生成TTS，避免长文本edge-tts的截断问题
3. 用 ffprobe 精确测量时长，作为后续时轴拼接的唯一数据源
4. 输出 segments.json，作为 Single Source of Truth
5. v1.1 升级：语义段落类型推断（SegmentType），让下游组件基于语义自动配置

语义类型推断：
    - 基于关键词、句式、段落位置自动推断每段的语义类型
    - 类型信息写入 segments.json，供 timeline_mapper / storyboard_ai 消费
    - 支持自定义规则扩展（rules.json）
"""

import asyncio
import json
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict

import edge_tts


class SegmentType(str, Enum):
    """语义段落类型"""
    HOOK = "hook"                    # 开头 hook
    NARRATIVE = "narrative"          # 叙事/讲述
    DATA_CONTRAST = "data_contrast"  # 数据对比（价格、数量等）
    LIST = "list"                    # 列表/要点
    DATE = "date"                    # 日期/时间/日历
    QUOTE = "quote"                  # 引用/金句
    CTA = "cta"                      # 行动号召/结尾引导
    TRANSITION = "transition"        # 过渡/承接
    UNKNOWN = "unknown"              # 未识别


@dataclass
class NarrationSegment:
    """单段旁白元数据"""
    id: str
    text: str
    duration: float = 0.0
    audio_path: str = ""
    index: int = 0
    segment_type: str = "unknown"    # 语义类型
    segment_type_confidence: float = 0.0  # 类型推断置信度
    notes: str = ""


class SemanticTypeAnalyzer:
    """
    语义段落类型分析器

    基于关键词、句式、段落位置推断语义类型。
    规则可扩展：通过 rules/segment_types.json 自定义。
    """

    DEFAULT_RULES = {
        "position_rules": {
            "first": {"type": "hook", "confidence": 0.7},
            "last": {"type": "cta", "confidence": 0.5},
        },
        "keyword_rules": [
            {"keywords": ["价格", "涨价", "降价", "翻倍", "三倍", "对比", "vs", "versus", "相差"], "type": "data_contrast", "confidence": 0.9},
            {"keywords": ["明细", "列表", "合计", "总和", "第一", "第二", "第三", "步骤"], "type": "list", "confidence": 0.85},
            {"keywords": ["日期", "月", "日", "号", "截止", "到期", "清零", "倒计时"], "type": "date", "confidence": 0.8},
            {"keywords": ["\\\"", "'", "说过", "写道", "名言", "金句"], "type": "quote", "confidence": 0.75},
            {"keywords": ["关注", "点赞", "评论", "转发", "收藏", "订阅", "follow", "like"], "type": "cta", "confidence": 0.95},
            {"keywords": ["接下来", "然后", "其次", "另外", "不仅如此", "更重要的是"], "type": "transition", "confidence": 0.6},
        ],
        "pattern_rules": [
            {"pattern": r"\d+\.\s+.+", "type": "list", "confidence": 0.8},  # 1. xxx
            {"pattern": r"[\d]+[\s]*[\+\-×÷]", "type": "data_contrast", "confidence": 0.7},  # 数字运算
            {"pattern": r"\d{4}年|\d{1,2}月\d{1,2}日", "type": "date", "confidence": 0.85},  # 日期
        ],
    }

    def __init__(self, rules_path: Optional[str] = None):
        self.rules = self._load_rules(rules_path)

    def _load_rules(self, rules_path: Optional[str]) -> dict:
        """加载自定义规则，没有则使用默认规则"""
        if rules_path and Path(rules_path).exists():
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return self.DEFAULT_RULES

    def analyze(self, text: str, index: int, total: int) -> Tuple[str, float]:
        """
        分析段落的语义类型

        Returns:
            (segment_type, confidence)
        """
        candidates = []

        # 1. 位置规则
        pos_rules = self.rules.get("position_rules", {})
        if index == 0 and "first" in pos_rules:
            candidates.append((pos_rules["first"]["type"], pos_rules["first"]["confidence"]))
        if index == total - 1 and "last" in pos_rules:
            # 但最后一段如果有 CTA 关键词，优先级更高
            pass  # 不立即添加，让 keyword 规则竞争

        # 2. 关键词规则
        for rule in self.rules.get("keyword_rules", []):
            if any(kw in text for kw in rule["keywords"]):
                candidates.append((rule["type"], rule["confidence"]))

        # 3. 正则规则
        for rule in self.rules.get("pattern_rules", []):
            if re.search(rule["pattern"], text):
                candidates.append((rule["type"], rule["confidence"]))

        # 位置规则兜底：最后一个 segment 如果没有被关键词/正则覆盖，默认 cta
        if index == total - 1 and not any(t == "cta" for t, _ in candidates):
            pos_rules = self.rules.get("position_rules", {})
            if "last" in pos_rules:
                candidates.append((pos_rules["last"]["type"], pos_rules["last"]["confidence"]))

        if not candidates:
            # 默认：中间段为 narrative
            if 0 < index < total - 1:
                return "narrative", 0.5
            return "unknown", 0.0

        # 选择置信度最高的类型
        best_type, best_conf = max(candidates, key=lambda x: x[1])

        # Guard：非最后一个 segment 不允许被推断为 cta
        # CTA 只能出现在视频结尾，避免中间段被误标为行动号召
        if best_type == "cta" and index < total - 1:
            # 降级为 narrative，置信度中等
            return "narrative", 0.5

        return best_type, best_conf


class SegmentedTTSGenerator:
    """
    分段TTS生成器（v1.1 Semantic Typing）
    """

    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
    OUTPUT_SUBDIR = "narration_segments"

    def __init__(
        self,
        output_dir: str = "output",
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
        volume: str = "+0%",
        type_rules_path: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir)
        self.segments_dir = self.output_dir / self.OUTPUT_SUBDIR
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.type_analyzer = SemanticTypeAnalyzer(rules_path=type_rules_path)
        self.segments: List[NarrationSegment] = []

    def split_by_semantic(self, full_text: str, scene_hints: Optional[List[dict]] = None) -> List[NarrationSegment]:
        """
        按语义边界切分长文本，并推断每段的语义类型。
        """
        segments = []

        if scene_hints:
            for idx, hint in enumerate(scene_hints):
                seg = NarrationSegment(
                    id=hint["id"],
                    text=hint.get("text", "").strip(),
                    index=idx,
                    notes=hint.get("notes", ""),
                )
                # 推断语义类型
                seg_type, conf = self.type_analyzer.analyze(seg.text, idx, len(scene_hints))
                seg.segment_type = seg_type
                seg.segment_type_confidence = conf
                segments.append(seg)
        else:
            # 自动切分
            raw_parts = re.split(r'([。！？\n]+)', full_text.strip())
            parts = []
            current = ""
            for part in raw_parts:
                current += part
                if re.search(r'[。！？\n]+$', part) and len(current) > 10:
                    parts.append(current.strip())
                    current = ""
            if current.strip():
                parts.append(current.strip())

            for idx, text in enumerate(parts):
                seg_id = f"s{idx+1:02d}_auto"
                seg = NarrationSegment(
                    id=seg_id,
                    text=text,
                    index=idx,
                )
                seg_type, conf = self.type_analyzer.analyze(text, idx, len(parts))
                seg.segment_type = seg_type
                seg.segment_type_confidence = conf
                segments.append(seg)

        self.segments = segments
        return segments

    async def _generate_one(self, segment: NarrationSegment) -> NarrationSegment:
        """生成单段TTS并测量时长"""
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.segments_dir / f"{segment.id}.mp3"

        communicate = edge_tts.Communicate(
            segment.text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
        )
        await communicate.save(str(output_path))

        duration = self._probe_duration(str(output_path))
        segment.duration = duration
        segment.audio_path = str(output_path.relative_to(self.output_dir.parent if self.output_dir.name == "output" else self.output_dir))

        return segment

    def _probe_duration(self, audio_path: str) -> float:
        """用 ffprobe 获取音频精确时长"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            raise RuntimeError(f"ffprobe failed for {audio_path}: {e}")

    async def generate_all(self, progress_callback=None) -> List[NarrationSegment]:
        """生成所有段落TTS"""
        if not self.segments:
            raise ValueError("No segments. Call split_by_semantic() first.")

        for i, seg in enumerate(self.segments):
            await self._generate_one(seg)
            if progress_callback:
                progress_callback(seg.id, seg.duration, seg.segment_type)

        return self.segments

    def save_manifest(self) -> Path:
        """保存 segments.json 作为 Single Source of Truth"""
        manifest_path = self.output_dir / "segments.json"
        data = {
            "generator": "md2video.segment_tts",
            "version": "1.1.0",
            "voice": self.voice,
            "rate": self.rate,
            "segments": [asdict(s) for s in self.segments],
            "total_duration": sum(s.duration for s in self.segments),
            "segment_count": len(self.segments),
            "type_distribution": self._type_distribution(),
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return manifest_path

    def _type_distribution(self) -> Dict[str, int]:
        """统计语义类型分布"""
        dist = {}
        for s in self.segments:
            dist[s.segment_type] = dist.get(s.segment_type, 0) + 1
        return dist

    @classmethod
    def load_manifest(cls, output_dir: str) -> List[NarrationSegment]:
        """从 segments.json 加载已生成的段落信息"""
        manifest_path = Path(output_dir) / "segments.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [NarrationSegment(**s) for s in data["segments"]]


def generate_segmented_tts(
    full_text: str,
    output_dir: str = "output",
    scene_hints: Optional[List[dict]] = None,
    voice: str = SegmentedTTSGenerator.DEFAULT_VOICE,
) -> Path:
    """
    便捷入口：一键生成分段TTS（含语义类型）
    """
    gen = SegmentedTTSGenerator(output_dir=output_dir, voice=voice)
    gen.split_by_semantic(full_text, scene_hints=scene_hints)
    asyncio.run(gen.generate_all())
    return gen.save_manifest()
