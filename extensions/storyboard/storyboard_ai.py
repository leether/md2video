#!/usr/bin/env python3
"""
Storyboard AI — 文章→分镜拆解器（v1.1 规则驱动）

核心原则：
1. 输入：Markdown 文章或纯文本
2. 输出：结构化的分镜脚本（shots.json），可直接转换为 segments + prompts
3. 每段分镜必须包含：id, text（旁白）, visual_type, duration_hint, notes
4. 旁白总字数与目标视频时长的换算：中文约 250-300 字/分钟
5. v1.1 升级：规则驱动的分镜拆解，规则从 storyboard_rules.json 加载

规则驱动的好处：
    - 发现新的语义模式时，只需更新 rules/storyboard_rules.json，无需改代码
    - SKILL 可以从使用中学习（结构耦合）
    - 增强自创生能力：规则是 SKILL 自我生产网络的一部分

分镜类型（visual_type）：
    - jimeng: 即梦 AI 生成素材
    - animation: Python 动画（数据可视化、表格、对比）
    - static: 静态图片
    - transition: 纯过渡画面
    - endcard: CTA 结尾卡片
"""

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class Shot:
    """单个分镜"""
    id: str
    text: str
    visual_type: str
    duration_hint: float = 5.0
    notes: str = ""
    template_id: Optional[str] = None
    animation_type: Optional[str] = None
    segment_type: str = "unknown"
    vars: Dict[str, str] = field(default_factory=dict)


class StoryboardAI:
    """
    文章→分镜拆解器（规则驱动版）

    支持两种模式：
    1. 规则模式（默认）：基于 rules/storyboard_rules.json 自动拆解
    2. LLM 模式（可选）：调用大模型生成更智能的分镜
    """

    CHARS_PER_SECOND = 4.5
    RULES_PATH = Path(__file__).parent.parent.parent / "rules" / "storyboard_rules.json"

    def __init__(
        self,
        chars_per_second: float = CHARS_PER_SECOND,
        rules_path: Optional[Path] = None,
    ):
        self.chars_per_second = chars_per_second
        self.rules_path = rules_path or self.RULES_PATH
        self.rules = self._load_rules()
        self.shots: List[Shot] = []

    def _load_rules(self) -> dict:
        """加载分镜规则"""
        if self.rules_path.exists():
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _infer_segment_type(self, text: str, index: int, total: int) -> str:
        """
        推断段落语义类型
        优先使用 segment_types.json 的规则，如果没有加载则使用简单启发式
        """
        segment_types_path = self.rules_path.parent / "segment_types.json"
        if segment_types_path.exists():
            with open(segment_types_path, "r", encoding="utf-8") as f:
                type_rules = json.load(f)

            candidates = []

            # 位置规则
            pos_rules = type_rules.get("position_rules", {})
            if index == 0 and "first" in pos_rules:
                candidates.append((pos_rules["first"]["type"], pos_rules["first"]["confidence"]))

            # 关键词规则
            for rule in type_rules.get("keyword_rules", []):
                if any(kw in text for kw in rule["keywords"]):
                    candidates.append((rule["type"], rule["confidence"]))

            # 正则规则
            for rule in type_rules.get("pattern_rules", []):
                if re.search(rule["pattern"], text):
                    candidates.append((rule["type"], rule["confidence"]))

            if candidates:
                return max(candidates, key=lambda x: x[1])[0]

        # 简单回退
        if index == 0:
            return "hook"
        if index == total - 1:
            return "cta"
        return "narrative"

    def _map_to_shot(self, text: str, index: int, total: int) -> Shot:
        """
        根据规则将段落映射为 Shot
        """
        seg_type = self._infer_segment_type(text, index, total)

        # 从规则中查找映射
        type_mapping = self.rules.get("segment_type_mapping", {})
        mapping = type_mapping.get(seg_type, type_mapping.get("unknown", {}))

        shot_id = f"s{index+1:02d}_{seg_type}"

        # 计算预估时长
        duration = len(text) / self.chars_per_second
        duration = max(2.0, min(15.0, duration))

        return Shot(
            id=shot_id,
            text=text,
            visual_type=mapping.get("visual_type", "jimeng"),
            duration_hint=duration,
            notes=mapping.get("notes", ""),
            template_id=mapping.get("template_id"),
            animation_type=mapping.get("animation_type"),
            segment_type=seg_type,
        )

    def parse_markdown(self, md_text: str) -> List[Shot]:
        """
        解析 Markdown 文本，生成分镜列表
        """
        paragraphs = [p.strip() for p in md_text.split("\n\n") if p.strip()]
        shots = []

        for idx, para in enumerate(paragraphs):
            text = self._clean_text(para)
            shot = self._map_to_shot(text, idx, len(paragraphs))
            shots.append(shot)

        self.shots = shots
        return shots

    def _clean_text(self, text: str) -> str:
        """清理文本：移除 Markdown 标记"""
        text = re.sub(r'^#+\s*', '', text)
        text = re.sub(r'\*\*|__', '', text)
        text = re.sub(r'\*|_', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        text = re.sub(r'`[^`]+`', '', text)
        return text.strip()

    def estimate_total_duration(self) -> float:
        """估算总时长"""
        return sum(s.duration_hint for s in self.shots)

    def to_segments_format(self) -> List[dict]:
        """转换为 segments.json 格式"""
        return [
            {
                "id": s.id,
                "text": s.text,
                "duration": 0.0,
                "index": i,
                "segment_type": s.segment_type,
                "notes": s.notes,
            }
            for i, s in enumerate(self.shots)
        ]

    def to_prompts_format(self) -> List[dict]:
        """转换为 prompts.json 格式"""
        prompts = []
        for s in self.shots:
            if s.visual_type == "animation":
                prompts.append({
                    "id": s.id,
                    "source": "python_animation",
                    "animation_type": s.animation_type,
                    "vars": s.vars,
                    "notes": s.notes,
                })
            else:
                prompts.append({
                    "id": s.id,
                    "source": "jimeng",
                    "template_id": s.template_id,
                    "vars": s.vars,
                    "notes": s.notes,
                })
        return prompts

    def _infer_transitions(self) -> List[Dict]:
        """
        根据 shots 的 segment_type 自动推断转场配置

        使用 transition_rules 中的规则匹配相邻段的类型组合。
        """
        transitions = []
        trans_rules = self.rules.get("transition_rules", {})

        for i in range(len(self.shots) - 1):
            type_a = self.shots[i].segment_type
            type_b = self.shots[i + 1].segment_type

            # 尝试精确匹配
            key = f"{type_a}→{type_b}"
            rule = trans_rules.get(key)

            if not rule:
                # 回退到默认
                rule = trans_rules.get("default", {"type": "fade", "duration": 0.5})

            transitions.append({
                "index": i,
                "type": rule["type"],
                "duration": rule["duration"],
            })

        return transitions

    def save(self, output_dir: str = "output"):
        """保存分镜文件和转场配置"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # shots.json
        shots_path = output_dir / "shots.json"
        with open(shots_path, "w", encoding="utf-8") as f:
            json.dump([asdict(s) for s in self.shots], f, ensure_ascii=False, indent=2)

        # transitions.json
        transitions = self._infer_transitions()
        trans_path = output_dir / "transitions.json"
        with open(trans_path, "w", encoding="utf-8") as f:
            json.dump(transitions, f, ensure_ascii=False, indent=2)

        return shots_path, trans_path

    def generate_pipeline_inputs(self, output_dir: str = "."):
        """
        一键生成 pipeline 所需的全部输入文件

        输出：
            - segments_hint.json（供 segment_tts 使用）
            - prompts.json（供 timeline_mapper 使用）
            - transitions.json（供 timeline_mapper 使用）
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # segments_hint.json
        segments_path = output_dir / "segments_hint.json"
        with open(segments_path, "w", encoding="utf-8") as f:
            json.dump(self.to_segments_format(), f, ensure_ascii=False, indent=2)

        # prompts.json
        prompts_path = output_dir / "prompts.json"
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(self.to_prompts_format(), f, ensure_ascii=False, indent=2)

        # transitions.json
        transitions = self._infer_transitions()
        trans_path = output_dir / "transitions.json"
        with open(trans_path, "w", encoding="utf-8") as f:
            json.dump(transitions, f, ensure_ascii=False, indent=2)

        return segments_path, prompts_path, trans_path


# 便捷入口
def storyboard_from_article(
    article_text: str,
    output_dir: str = ".",
    chars_per_second: float = 4.5,
) -> tuple:
    """
    从文章一键生成分镜和 pipeline 输入

    Returns:
        (shots.json 路径, transitions.json 路径)
    """
    ai = StoryboardAI(chars_per_second=chars_per_second)
    ai.parse_markdown(article_text)
    ai.generate_pipeline_inputs(output_dir)
    return ai.save(output_dir)
